"""Room pages, messages, timed sessions and the pure helpers."""
from datetime import timedelta
from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.testing import make_onboarded_user, seed_reference_data
from apps.matching.services import requests as req
from apps.matching.services import safety

from .consumers import RateLimiter
from .models import ExchangeSession, Message
from .services import rooms
from .starters import GENERAL, starters_for


def make_partners():
    asha = make_onboarded_user("asha", native="bn", learning="en", level="B1")
    tom = make_onboarded_user("tom", native="en", learning="bn", level="B2")
    match = req.accept_request(req.send_request(asha, tom).request, tom)
    return asha, tom, match.room


class PureHelperTests(SimpleTestCase):
    def test_session_state_moves_through_both_languages(self):
        start = timezone.now()
        session = SimpleNamespace(started_at=start, minutes_per_language=10, first_language_id=1, second_language_id=2)
        at = lambda minutes: rooms.session_state(session, start + timedelta(minutes=minutes))
        self.assertEqual((at(0).phase, at(0).language_id, at(0).remaining_seconds), ("first", 1, 600))
        self.assertEqual((at(9.5).phase, at(9.5).remaining_seconds), ("first", 30))
        self.assertEqual((at(10).phase, at(10).language_id), ("second", 2))
        self.assertEqual((at(25).phase, at(25).remaining_seconds), ("overtime", 0))

    def test_rate_limiter_uses_a_sliding_window(self):
        now = [0.0]
        limiter = RateLimiter(2, 10, clock=lambda: now[0])
        self.assertEqual([limiter.allow(), limiter.allow(), limiter.allow()], [True, True, False])
        now[0] = 10.1
        self.assertTrue(limiter.allow())

    def test_starters_prefer_shared_interests(self):
        ideas = starters_for(["music"], seed=1)
        self.assertEqual(len(ideas), 4)
        self.assertTrue(any("song" in idea or "musician" in idea for idea in ideas[:2]))
        self.assertTrue(set(starters_for([], seed=1)) <= set(GENERAL))


class RoomPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_reference_data()

    def setUp(self):
        self.asha, self.tom, self.room = make_partners()
        self.client.force_login(self.asha)
        self.url = reverse("exchange:room", kwargs={"room_id": self.room.pk})

    def test_partner_sees_the_room(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Tom")
        self.assertContains(response, "You practise English; Tom practises Bengali.")
        self.assertContains(response, "Start a session")
        self.assertContains(response, f"/ws/rooms/{self.room.pk}/")
        self.assertContains(response, "Conversation idea")

    def test_outsiders_and_anonymous_are_kept_out(self):
        self.client.force_login(make_onboarded_user("eve", native="hi", learning="en"))
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.client.logout()
        self.assertIn(reverse("accounts:login"), self.client.get(self.url).headers["Location"])

    def test_blocking_closes_the_room_for_both(self):
        safety.block_user(self.tom, self.asha)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_partner_pages_link_to_the_room(self):
        self.assertContains(self.client.get(reverse("partners:list")), self.url)

    def test_fallback_message_post(self):
        post = reverse("exchange:post_message", kwargs={"room_id": self.room.pk})
        self.assertRedirects(self.client.post(post, {"body": "  Hello Tom!  "}), self.url)
        message = Message.objects.get()
        self.assertEqual((message.sender, message.body, message.language), (self.asha, "Hello Tom!", None))
        self.assertContains(self.client.post(post, {"body": "   "}, follow=True), "Write a message first")
        self.assertContains(self.client.post(post, {"body": "x" * 2001}, follow=True), "up to 2000 characters")
        self.assertEqual(Message.objects.count(), 1)

    def test_messages_are_escaped(self):
        rooms.post_message(self.tom, self.room.pk, "<script>alert(1)</script>")
        response = self.client.get(self.url)
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;")

    def test_outsider_cannot_post(self):
        self.client.force_login(make_onboarded_user("eve", native="hi", learning="en"))
        post = reverse("exchange:post_message", kwargs={"room_id": self.room.pk})
        self.assertEqual(self.client.post(post, {"body": "hi"}).status_code, 404)
        self.assertFalse(Message.objects.exists())


class SessionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_reference_data()

    def setUp(self):
        self.asha, self.tom, self.room = make_partners()
        self.client.force_login(self.asha)
        self.start_url = reverse("exchange:start_session", kwargs={"room_id": self.room.pk})
        self.end_url = reverse("exchange:end_session", kwargs={"room_id": self.room.pk})
        self.en = self.room.match.user_a_learning_language if self.room.match.user_a == self.asha \
            else self.room.match.user_b_learning_language

    def test_start_and_end_a_session(self):
        self.client.post(self.start_url, {"first_language": self.en.pk, "minutes": 10})
        session = ExchangeSession.objects.get()
        self.assertEqual((session.status, session.first_language, session.minutes_per_language), ("active", self.en, 10))
        self.assertEqual(session.second_language.code, "bn")
        page = self.client.get(reverse("exchange:room", kwargs={"room_id": self.room.pk}))
        self.assertContains(page, "Now practising")
        self.assertContains(page, "End session")
        response = self.client.post(self.end_url, follow=True)
        session.refresh_from_db()
        self.assertEqual(session.status, "completed")
        self.assertIsNotNone(session.ended_at)
        self.assertContains(response, "Session ended after")

    def test_messages_during_a_session_record_the_language(self):
        rooms.start_session(self.asha, self.room.pk, first_language_id=self.en.pk, minutes=10)
        message = rooms.post_message(self.tom, self.room.pk, "Hello!")
        self.assertEqual(message.language, self.en)

    def test_invalid_session_settings(self):
        from apps.languages.models import Language
        hindi = Language.objects.get(code="hi")
        for data in ({"first_language": hindi.pk, "minutes": 10}, {"first_language": self.en.pk, "minutes": 7}):
            with self.subTest(data=data):
                self.client.post(self.start_url, data)
        self.assertFalse(ExchangeSession.objects.exists())

    def test_one_session_at_a_time(self):
        rooms.start_session(self.asha, self.room.pk, first_language_id=self.en.pk, minutes=10)
        with self.assertRaisesMessage(rooms.RoomError, "already running"):
            rooms.start_session(self.tom, self.room.pk, first_language_id=self.en.pk, minutes=5)

    def test_end_without_session(self):
        self.assertContains(self.client.post(self.end_url, follow=True), "no session running")

    def test_session_actions_are_post_only_and_partner_only(self):
        self.assertEqual(self.client.get(self.start_url).status_code, 405)
        self.client.force_login(make_onboarded_user("eve", native="hi", learning="en"))
        self.assertEqual(self.client.post(self.start_url, {"first_language": self.en.pk, "minutes": 10}).status_code, 404)
        self.assertEqual(self.client.post(self.end_url).status_code, 404)
