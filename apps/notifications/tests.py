"""Notifications: the five events, email in the background, reminders, pages."""
from datetime import datetime, timezone as dt_timezone
from unittest import mock

from django.core import mail
from django.test import TestCase
from django.urls import reverse

from apps.core.testing import make_onboarded_user, seed_reference_data
from apps.exchange import presence
from apps.exchange.services import rooms
from apps.matching.models import MatchSuggestion
from apps.matching.services import requests as req

from . import services
from .models import Notification
from .tasks import send_notification_email

# A Monday: 11:20 UTC is 16:50 in Kolkata, ten minutes before the test
# users' shared Monday 17:00–21:00 availability.
TEN_MINUTES_BEFORE = datetime(2026, 9, 28, 11, 20, tzinfo=dt_timezone.utc)


class NotificationTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_reference_data()

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.asha = make_onboarded_user("asha", native="bn", learning="en", level="B1")
        self.tom = make_onboarded_user("tom", native="en", learning="bn", level="B2")

    def send(self):
        with self.captureOnCommitCallbacks(execute=True):
            return req.send_request(self.asha, self.tom, "Hi Tom!").request

    def partner_up(self):
        request = self.send()
        with self.captureOnCommitCallbacks(execute=True):
            return req.accept_request(request, self.tom)


class EventTests(NotificationTestCase):
    def test_request_notifies_receiver_by_app_and_email(self):
        request = self.send()
        note = Notification.objects.get(recipient=self.tom)
        self.assertEqual((note.kind, note.actor, note.title), ("match_request", self.asha, "Asha wants to practise with you"))
        self.assertEqual(note.link, reverse("partners:request_detail", kwargs={"pk": request.pk}))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["tom@example.com"])
        self.assertIn(f"https://testserver{note.link}", mail.outbox[0].body)

    def test_accept_notifies_sender(self):
        match = self.partner_up()
        note = Notification.objects.get(recipient=self.asha, kind="match_accepted")
        self.assertEqual(note.link, reverse("exchange:room", kwargs={"room_id": match.room.pk}))
        self.assertEqual(len(mail.outbox), 2)

    def test_messages_collapse_into_one_note_and_skip_email(self):
        room = self.partner_up().room
        mail.outbox.clear()
        for text in ("Hello", "Are you there?", "Shall we start?"):
            rooms.post_message(self.asha, room.pk, text)
        note = Notification.objects.get(recipient=self.tom, kind="new_message")
        self.assertEqual(note.body, "Asha sent you 3 messages.")
        self.assertEqual(mail.outbox, [])

    def test_count_restarts_after_a_reply(self):
        room = self.partner_up().room
        rooms.post_message(self.asha, room.pk, "One")
        rooms.post_message(self.asha, room.pk, "Two")
        rooms.post_message(self.tom, room.pk, "Reply")
        rooms.post_message(self.asha, room.pk, "Three")
        self.assertEqual(Notification.objects.get(recipient=self.tom, kind="new_message").body,
                         "Asha sent you a message.")

    def test_no_message_note_while_the_room_is_open(self):
        room = self.partner_up().room
        presence.mark_present(room.pk, self.tom.pk)
        rooms.post_message(self.asha, room.pk, "Hello")
        self.assertFalse(Notification.objects.filter(recipient=self.tom, kind="new_message").exists())

    def test_ending_a_session_asks_the_partner_for_feedback(self):
        room = self.partner_up().room
        en = room.match.user_a_learning_language_id
        rooms.start_session(self.asha, room.pk, first_language_id=en, minutes=10)
        session = rooms.end_session(self.asha, room.pk)
        note = Notification.objects.get(recipient=self.tom, kind="feedback_request")
        self.assertEqual(note.link, reverse("feedback:session", kwargs={"session_id": session.pk}))
        self.assertFalse(Notification.objects.filter(recipient=self.asha, kind="feedback_request").exists())


class ReminderTests(NotificationTestCase):
    def test_both_partners_are_reminded_once(self):
        self.partner_up()
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(services.session_reminders(now=TEN_MINUTES_BEFORE), 2)
        for user, partner in ((self.asha, "Tom"), (self.tom, "Asha")):
            note = Notification.objects.get(recipient=user, kind="session_reminder")
            self.assertEqual(note.title, f"Practice time with {partner} soon")
            self.assertIn("from 17:00 (Monday, your time)", note.body)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(services.session_reminders(now=TEN_MINUTES_BEFORE), 0)  # no duplicates

    def test_no_reminder_outside_the_window_or_without_a_partner(self):
        self.assertEqual(services.session_reminders(now=TEN_MINUTES_BEFORE), 0)  # not partners yet
        self.partner_up()
        an_hour_before = TEN_MINUTES_BEFORE.replace(hour=10, minute=20)
        self.assertEqual(services.session_reminders(now=an_hour_before), 0)


class EmailTaskTests(NotificationTestCase):
    def test_email_failure_is_logged_not_raised(self):
        note = services.notify(self.tom, "match_request", "Test")
        with mock.patch("apps.notifications.tasks.send_mail", side_effect=OSError("smtp down")), \
                self.assertLogs("apps.notifications.tasks", level="ERROR"):
            self.assertFalse(send_notification_email(note.pk))

    def test_no_email_for_users_without_an_address(self):
        type(self.tom).objects.filter(pk=self.tom.pk).update(email="")
        self.tom.refresh_from_db()
        with self.captureOnCommitCallbacks(execute=True):
            services.notify(self.tom, "match_request", "Test")
        self.assertEqual(mail.outbox, [])

    def test_hourly_suggestion_refresh_task(self):
        from apps.matching.tasks import refresh_all_suggestions
        refresh_all_suggestions()
        self.assertTrue(MatchSuggestion.objects.filter(user=self.asha, candidate=self.tom).exists())

    def test_celery_app_is_configured(self):
        from config import celery_app
        self.assertEqual(celery_app.main, "language_exchange")


class PageTests(NotificationTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.tom)

    def test_bell_list_open_and_mark_read(self):
        request = self.send()
        home = self.client.get(reverse("core:home"))
        self.assertContains(home, "Notifications, 1 unread")
        page = self.client.get(reverse("notifications:list"))
        self.assertContains(page, "Asha wants to practise with you")
        note = Notification.objects.get(recipient=self.tom)
        response = self.client.get(reverse("notifications:open", kwargs={"pk": note.pk}))
        self.assertRedirects(response, reverse("partners:request_detail", kwargs={"pk": request.pk}))
        note.refresh_from_db()
        self.assertTrue(note.is_read)
        self.assertNotContains(self.client.get(reverse("core:home")), "unread")

    def test_mark_all_read(self):
        services.notify(self.tom, "match_request", "One")
        services.notify(self.tom, "match_request", "Two")
        self.assertEqual(self.client.get(reverse("notifications:read_all")).status_code, 405)
        self.client.post(reverse("notifications:read_all"))
        self.assertEqual(services.unread_count(self.tom), 0)

    def test_links_can_only_point_inside_the_site(self):
        for bad in ("https://evil.example/", "//evil.example/", "javascript:alert(1)"):
            self.assertEqual(services.safe_link(bad), "")
        note = Notification.objects.create(recipient=self.tom, kind="match_request", title="x",
                                           link="https://evil.example/")
        response = self.client.get(reverse("notifications:open", kwargs={"pk": note.pk}))
        self.assertRedirects(response, reverse("notifications:list"))

    def test_other_peoples_notifications_are_private(self):
        note = services.notify(self.asha, "match_request", "Private")
        self.assertEqual(self.client.get(reverse("notifications:open", kwargs={"pk": note.pk})).status_code, 404)
        self.assertNotContains(self.client.get(reverse("notifications:list")), "Private")
