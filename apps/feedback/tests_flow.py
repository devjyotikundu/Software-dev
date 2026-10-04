"""Feedback after sessions, and how it shapes future recommendations."""
from datetime import timedelta

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.testing import make_onboarded_user, seed_reference_data
from apps.exchange.models import ExchangeSession
from apps.exchange.services import rooms
from apps.matching.models import Match
from apps.matching.services import feedback as signals
from apps.matching.services import requests as req
from apps.matching.services.candidates import candidate_ids
from apps.matching.services.scoring import explain
from apps.matching.services.suggestions import refresh_suggestions

from . import services
from .models import SessionFeedback


def partner_up(a, b):
    return req.accept_request(req.send_request(a, b).request, b)


def finished_session(match, *, minutes=20):
    start = timezone.now() - timedelta(minutes=minutes)
    return ExchangeSession.objects.create(
        room=match.room, first_language=match.user_a_learning_language,
        second_language=match.user_b_learning_language, status="completed",
        started_at=start, ended_at=timezone.now(),
    )


GOOD = {"usefulness": 5, "would_practice_again": "yes", "difficulty": "comfortable", "comment": "Great!"}


class FeedbackFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_reference_data()

    def setUp(self):
        self.asha = make_onboarded_user("asha", native="bn", learning="en", level="B1")
        self.tom = make_onboarded_user("tom", native="en", learning="bn", level="B2")
        self.match = partner_up(self.asha, self.tom)
        self.client.force_login(self.asha)

    def test_ending_a_session_opens_feedback_with_a_summary(self):
        en = self.match.user_a_learning_language_id if self.match.user_a == self.asha else self.match.user_b_learning_language_id
        rooms.start_session(self.asha, self.match.room.pk, first_language_id=en, minutes=10)
        rooms.post_message(self.tom, self.match.room.pk, "Hello!")
        response = self.client.post(reverse("exchange:end_session", kwargs={"room_id": self.match.room.pk}), follow=True)
        session = ExchangeSession.objects.get()
        self.assertRedirects(response, reverse("feedback:session", kwargs={"session_id": session.pk}))
        self.assertContains(response, "How was your session with Tom?")
        self.assertContains(response, "English, then Bengali")
        self.assertContains(response, "1 in English")

    def test_submitting_stores_feedback_about_the_partner(self):
        session = finished_session(self.match)
        url = reverse("feedback:session", kwargs={"session_id": session.pk})
        response = self.client.post(url, GOOD)
        self.assertRedirects(response, reverse("exchange:room", kwargs={"room_id": self.match.room.pk}))
        fb = SessionFeedback.objects.get()
        self.assertEqual((fb.reviewer, fb.reviewee, fb.usefulness, fb.would_practice_again, fb.difficulty, fb.comment),
                         (self.asha, self.tom, 5, True, "comfortable", "Great!"))

    def test_only_once_per_person_per_session(self):
        session = finished_session(self.match)
        url = reverse("feedback:session", kwargs={"session_id": session.pk})
        self.client.post(url, GOOD)
        response = self.client.post(url, GOOD, follow=True)
        self.assertContains(response, "already given feedback")
        self.assertEqual(SessionFeedback.objects.count(), 1)
        with self.assertRaises(services.FeedbackError):
            services.submit_feedback(self.asha, session, usefulness=4, would_practice_again=True, difficulty="too_easy")

    def test_both_partners_can_give_feedback(self):
        session = finished_session(self.match)
        self.client.post(reverse("feedback:session", kwargs={"session_id": session.pk}), GOOD)
        self.client.force_login(self.tom)
        self.client.post(reverse("feedback:session", kwargs={"session_id": session.pk}),
                         {**GOOD, "usefulness": 4, "difficulty": "too_difficult"})
        self.assertEqual(SessionFeedback.objects.filter(reviewee=self.asha).get().difficulty, "too_difficult")

    def test_every_answer_is_required_except_the_comment(self):
        session = finished_session(self.match)
        url = reverse("feedback:session", kwargs={"session_id": session.pk})
        for missing in ("usefulness", "would_practice_again", "difficulty"):
            with self.subTest(missing=missing):
                data = {k: v for k, v in GOOD.items() if k != missing}
                self.assertEqual(self.client.post(url, data).status_code, 200)
        self.client.post(url, {**GOOD, "usefulness": 9})
        self.assertFalse(SessionFeedback.objects.exists())
        self.client.post(url, {**GOOD, "comment": ""})
        self.assertTrue(SessionFeedback.objects.exists())

    def test_room_prompts_until_feedback_is_given(self):
        session = finished_session(self.match)
        room_url = reverse("exchange:room", kwargs={"room_id": self.match.room.pk})
        self.client.force_login(self.tom)
        self.assertContains(self.client.get(room_url), "How did it go?")
        self.client.post(reverse("feedback:session", kwargs={"session_id": session.pk}), GOOD)
        self.assertNotContains(self.client.get(room_url), "How did it go?")

    def test_outsiders_and_unfinished_sessions_are_404(self):
        active = ExchangeSession.objects.create(room=self.match.room, first_language=self.match.user_a_learning_language,
                                                second_language=self.match.user_b_learning_language)
        self.assertEqual(self.client.get(reverse("feedback:session", kwargs={"session_id": active.pk})).status_code, 404)
        active.status, active.ended_at = "completed", timezone.now()
        active.save()
        self.client.force_login(make_onboarded_user("eve", native="hi", learning="en"))
        self.assertEqual(self.client.get(reverse("feedback:session", kwargs={"session_id": active.pk})).status_code, 404)

    def test_partner_never_sees_the_comment(self):
        session = finished_session(self.match)
        self.client.post(reverse("feedback:session", kwargs={"session_id": session.pk}), {**GOOD, "comment": "Secret note"})
        self.client.force_login(self.tom)
        for url in (reverse("exchange:room", kwargs={"room_id": self.match.room.pk}),
                    reverse("partners:detail", kwargs={"match_id": self.match.pk})):
            self.assertNotContains(self.client.get(url), "Secret note")


class ReputationMathTests(SimpleTestCase):
    def test_points_scale_around_three_stars(self):
        self.assertEqual([signals.reputation_points(avg, 5) for avg in (5, 4, 3, 2, 1)], [5, 2.5, 0, -2.5, -5])

    def test_needs_enough_reviews(self):
        self.assertEqual(signals.reputation_points(5, 2), 0)

    @override_settings(MATCHING={"FEEDBACK_MAX_POINTS": 10, "FEEDBACK_MIN_REVIEWS": 1})
    def test_configurable(self):
        self.assertEqual(signals.reputation_points(5, 1), 10)

    def test_score_stays_within_bounds(self):
        score, breakdown = signals.apply(98.0, {}, (5.0, 10))
        self.assertEqual((score, breakdown["feedback"]["points"]), (100.0, 2.0))
        self.assertEqual(signals.apply(50.0, {"x": 1}, None), (50.0, {"x": 1}))


class RecommendationTests(TestCase):
    """Feedback changes who is suggested and in what order."""

    @classmethod
    def setUpTestData(cls):
        seed_reference_data()

    def setUp(self):
        self.asha = make_onboarded_user("asha", native="bn", learning="en", level="B1")
        # A1 vs Asha's B1 gives a base score of 94, leaving room for +5 below the 100 cap.
        self.tom = make_onboarded_user("tom", native="en", learning="bn", level="A1")
        self.sam = make_onboarded_user("sam", native="en", learning="bn", level="A1")  # identical to Tom

    def review(self, reviewee, usefulness, n=3):
        """n different people practise with ``reviewee`` and rate the session."""
        for i in range(n):
            reviewer = make_onboarded_user(f"r{reviewee.pk}x{i}", native="bn", learning="en")
            match = partner_up(reviewer, reviewee)
            services.submit_feedback(reviewer, finished_session(match), usefulness=usefulness,
                                     would_practice_again=True, difficulty="comfortable")

    def scores(self):
        refresh_suggestions(self.asha)
        return {s.candidate_id: s for s in self.asha.match_suggestions.all()}

    def test_well_rated_partner_ranks_higher(self):
        before = self.scores()
        self.assertEqual(before[self.tom.pk].score, before[self.sam.pk].score)
        self.review(self.tom, 5)
        after = self.scores()
        self.assertEqual(float(after[self.tom.pk].score) - float(after[self.sam.pk].score), 5.0)
        text = dict(explain(after[self.tom.pk].breakdown))["feedback"]
        self.assertEqual(text, "Partners rated sessions with them 5/5 on average (3 reviews), which adds 5 points.")

    def test_poorly_rated_partner_ranks_lower(self):
        self.review(self.sam, 1)
        after = self.scores()
        self.assertLess(after[self.sam.pk].score, after[self.tom.pk].score)

    def test_two_reviews_are_not_enough(self):
        self.review(self.tom, 5, n=2)
        self.assertNotIn("feedback", self.scores()[self.tom.pk].breakdown)

    def test_never_again_hides_both_people_after_the_partnership_ends(self):
        match = partner_up(self.asha, self.tom)
        services.submit_feedback(self.tom, finished_session(match), usefulness=2,
                                 would_practice_again=False, difficulty="too_easy")
        Match.objects.filter(pk=match.pk).update(status="ended", ended_at=timezone.now())
        self.assertNotIn(self.tom.pk, candidate_ids(self.asha))
        self.assertNotIn(self.asha.pk, candidate_ids(self.tom))
        self.assertIn(self.sam.pk, candidate_ids(self.asha))

    def test_detail_page_shows_the_adjustment_and_still_adds_up(self):
        self.review(self.tom, 5)
        self.client.force_login(self.asha)
        response = self.client.get(reverse("matching:detail", kwargs={"user_id": self.tom.pk}))
        self.assertContains(response, "Partner feedback")
        self.assertContains(response, "+5.0")
        total = sum(f["points"] for f in response.context["factors"])
        self.assertAlmostEqual(total, float(response.context["card"].suggestion.score), places=1)
