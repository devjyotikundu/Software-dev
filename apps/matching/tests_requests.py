"""Match requests, partners, blocking and reporting."""
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import BlockedUser, Report
from apps.core.testing import make_onboarded_user, seed_reference_data
from apps.exchange.models import ExchangeRoom

from .models import Match, MatchRequest
from .services import requests as req
from .services import safety
from .services.candidates import candidate_ids


class RequestTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_reference_data()

    def setUp(self):
        self.asha = make_onboarded_user("asha", native="bn", learning="en", level="B1")
        self.tom = make_onboarded_user("tom", native="en", learning="bn", level="B2")

    def send(self, sender=None, receiver=None, message="Hello!"):
        return req.send_request(sender or self.asha, receiver or self.tom, message)


class SendTests(RequestTestCase):
    def test_send_copies_language_pair_and_score(self):
        result = self.send()
        r = result.request
        self.assertFalse(result.matched)
        self.assertEqual((r.sender, r.receiver, r.status, r.message), (self.asha, self.tom, "pending", "Hello!"))
        self.assertEqual(r.sender_learning_language.code, "en")
        self.assertEqual(r.receiver_learning_language.code, "bn")
        self.assertGreater(r.score_at_request, 0)

    def test_only_to_current_suggestions(self):
        stranger = make_onboarded_user("rahul", native="en", learning="hi")
        with self.assertRaisesMessage(req.RequestError, "suggested to you"):
            self.send(receiver=stranger)
        with self.assertRaises(req.RequestError):
            self.send(receiver=self.asha)

    def test_no_duplicate_pending_request(self):
        self.send()
        with self.assertRaises(req.RequestError):
            self.send()
        self.assertEqual(MatchRequest.objects.count(), 1)

    def test_message_length_limit(self):
        with self.assertRaises(req.RequestError):
            self.send(message="x" * 301)

    @override_settings(MATCHING={"MAX_PENDING_SENT": 1})
    def test_cap_on_open_requests(self):
        self.send()
        other = make_onboarded_user("sam", native="en", learning="bn")
        with self.assertRaisesMessage(req.RequestError, "Cancel some"):
            self.send(receiver=other)

    def test_pending_people_leave_each_others_suggestions(self):
        self.send()
        self.assertNotIn(self.tom.pk, candidate_ids(self.asha))
        self.assertNotIn(self.asha.pk, candidate_ids(self.tom))

    def test_requesting_back_is_mutual_acceptance(self):
        self.send()
        result = self.send(sender=self.tom, receiver=self.asha)
        self.assertTrue(result.matched)
        self.assertEqual(Match.objects.filter(status="active").count(), 1)
        self.assertEqual(MatchRequest.objects.count(), 1)


class RespondTests(RequestTestCase):
    def test_accept_creates_ordered_match_and_room(self):
        r = self.send().request
        match = req.accept_request(r, self.tom)
        r.refresh_from_db()
        self.assertEqual(r.status, "accepted")
        self.assertIsNotNone(r.responded_at)
        self.assertLess(match.user_a_id, match.user_b_id)
        self.assertEqual(match.request, r)
        languages = {match.user_a_id: match.user_a_learning_language.code,
                     match.user_b_id: match.user_b_learning_language.code}
        self.assertEqual(languages, {self.asha.pk: "en", self.tom.pk: "bn"})
        room = ExchangeRoom.objects.get(match=match)
        self.assertTrue(room.has_participant(self.asha) and room.has_participant(self.tom))

    def test_only_the_receiver_can_accept_or_decline(self):
        r = self.send().request
        for action in (req.accept_request, req.decline_request):
            with self.subTest(action=action.__name__), self.assertRaisesMessage(req.RequestError, "isn't yours"):
                action(r, self.asha)

    def test_only_the_sender_can_cancel(self):
        r = self.send().request
        with self.assertRaises(req.RequestError):
            req.cancel_request(r, self.tom)
        req.cancel_request(r, self.asha)
        r.refresh_from_db()
        self.assertEqual(r.status, "cancelled")

    def test_answered_requests_cannot_be_answered_again(self):
        r = self.send().request
        req.decline_request(r, self.tom)
        with self.assertRaisesMessage(req.RequestError, "already been answered"):
            req.accept_request(r, self.tom)
        self.assertFalse(Match.objects.exists())

    def test_decline_starts_cooldown(self):
        r = self.send().request
        req.decline_request(r, self.tom)
        self.assertNotIn(self.tom.pk, candidate_ids(self.asha))

    def test_cancel_returns_both_to_suggestions(self):
        r = self.send().request
        req.cancel_request(r, self.asha)
        self.assertIn(self.tom.pk, candidate_ids(self.asha))


class SafetyTests(RequestTestCase):
    def test_block_ends_partnership_room_and_requests(self):
        match = req.accept_request(self.send().request, self.tom)
        safety.block_user(self.asha, self.tom)
        match.refresh_from_db()
        self.assertEqual(match.status, "ended")
        self.assertFalse(match.room.is_active)
        self.assertTrue(BlockedUser.objects.filter(blocker=self.asha, blocked=self.tom).exists())
        self.assertNotIn(self.asha.pk, candidate_ids(self.tom))

    def test_block_cancels_pending_requests(self):
        r = self.send().request
        safety.block_user(self.tom, self.asha)
        r.refresh_from_db()
        self.assertEqual(r.status, "cancelled")

    def test_unblock(self):
        safety.block_user(self.asha, self.tom)
        self.assertTrue(safety.unblock_user(self.asha, self.tom))
        self.assertIn(self.tom.pk, candidate_ids(self.asha))

    def test_report_with_optional_block(self):
        report = safety.report_user(self.asha, self.tom, "spam", " Sent links ", also_block=True)
        self.assertEqual((report.reason, report.details, report.status), ("spam", "Sent links", "open"))
        self.assertTrue(BlockedUser.objects.filter(blocker=self.asha, blocked=self.tom).exists())

    def test_relationship_required_for_block_and_report(self):
        stranger = make_onboarded_user("zed", native="hi", learning="bn")  # never suggested to Asha
        self.assertFalse(safety.has_relationship(self.asha, stranger))
        self.assertTrue(safety.has_relationship(self.asha, self.tom))


class RequestViewTests(RequestTestCase):
    def login(self, user):
        self.client.force_login(user)

    def test_full_flow_through_the_pages(self):
        self.login(self.asha)
        response = self.client.post(reverse("matching:request", kwargs={"user_id": self.tom.pk}),
                                    {"message": "Shall we practise?"}, follow=True)
        self.assertRedirects(response, reverse("partners:requests"))
        self.assertContains(response, "Request sent to Tom")
        self.assertContains(response, "Waiting for a reply")

        self.login(self.tom)
        inbox = self.client.get(reverse("partners:requests"))
        self.assertContains(inbox, "Shall we practise?")
        self.assertContains(self.client.get(reverse("core:home")), 'class="lx-count"')  # header badge
        r = MatchRequest.objects.get()
        response = self.client.post(reverse("partners:accept", kwargs={"pk": r.pk}), follow=True)
        match = Match.objects.get()
        self.assertRedirects(response, reverse("partners:detail", kwargs={"match_id": match.pk}))
        self.assertContains(response, "You and Asha are now partners")
        self.assertContains(response, "Your private exchange room is set up")

        self.login(self.asha)
        self.assertContains(self.client.get(reverse("partners:list")), "Tom")

    def test_request_detail_explains_the_match(self):
        r = self.send().request
        self.login(self.tom)
        response = self.client.get(reverse("partners:request_detail", kwargs={"pk": r.pk}))
        self.assertContains(response, "Why this match?")
        self.assertContains(response, "would like to practise with you")
        self.assertContains(response, "Accept")

    def test_action_is_fixed_by_url_and_post_only(self):
        r = self.send().request
        self.login(self.tom)
        self.assertEqual(self.client.get(reverse("partners:accept", kwargs={"pk": r.pk})).status_code, 405)
        self.client.post(reverse("partners:decline", kwargs={"pk": r.pk}), {"action": "accept"})
        r.refresh_from_db()
        self.assertEqual(r.status, "declined")

    def test_strangers_get_404_everywhere(self):
        r = self.send().request
        match_request = r
        outsider = make_onboarded_user("eve", native="hi", learning="en")
        self.login(outsider)
        for name in ("request_detail", "accept", "decline", "cancel"):
            method = self.client.get if name == "request_detail" else self.client.post
            with self.subTest(name):
                self.assertEqual(method(reverse(f"partners:{name}", kwargs={"pk": match_request.pk})).status_code, 404)
        match = req.accept_request(r, self.tom)
        self.assertEqual(self.client.get(reverse("partners:detail", kwargs={"match_id": match.pk})).status_code, 404)
        self.assertEqual(self.client.get(reverse("partners:block", kwargs={"user_id": self.asha.pk})).status_code, 404)

    def test_block_and_report_pages(self):
        self.login(self.asha)
        block_url = reverse("partners:block", kwargs={"user_id": self.tom.pk})
        self.assertContains(self.client.get(block_url), "Block Tom?")
        response = self.client.post(block_url, follow=True)
        self.assertRedirects(response, reverse("partners:blocked"))
        self.assertContains(response, "Unblock")
        report_url = reverse("partners:report", kwargs={"user_id": self.tom.pk})
        self.client.post(report_url, {"reason": "harassment", "details": "Rude messages"})
        self.assertTrue(Report.objects.filter(reporter=self.asha, reported=self.tom, reason="harassment").exists())

    def test_report_requires_a_reason(self):
        self.login(self.asha)
        response = self.client.post(reverse("partners:report", kwargs={"user_id": self.tom.pk}), {})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Report.objects.exists())
