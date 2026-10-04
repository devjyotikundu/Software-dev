from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.core.testing import make_user, seed_reference_data
from apps.languages.models import Language
from apps.matching.models import Match

from .models import ExchangeRoom, ExchangeSession


class ExchangeModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_reference_data()
        cls.en = Language.objects.get(code="en")
        cls.bn = Language.objects.get(code="bn")

    def setUp(self):
        self.a, self.b, self.outsider = make_user("a"), make_user("b"), make_user("c")
        low, high = Match.ordered_pair(self.a, self.b)
        self.match = Match.objects.create(
            user_a=low, user_b=high,
            user_a_learning_language=self.en, user_b_learning_language=self.bn,
        )
        self.room = ExchangeRoom.objects.create(match=self.match)

    def session(self, **extra):
        values = {"room": self.room, "first_language": self.en, "second_language": self.bn}
        values.update(extra)
        return ExchangeSession.objects.create(**values)

    def test_room_participants_come_from_match(self):
        self.assertTrue(self.room.has_participant(self.a))
        self.assertTrue(self.room.has_participant(self.b))
        self.assertFalse(self.room.has_participant(self.outsider))

    def test_one_active_session_per_room(self):
        self.session()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.session()

    def test_minutes_per_language_range(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.session(minutes_per_language=0)

    def test_duration(self):
        session = self.session()
        self.assertIsNone(session.duration)
        session.ended_at = session.started_at + timedelta(minutes=20)
        self.assertEqual(session.duration, timedelta(minutes=20))

    def test_session_cannot_end_before_start(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            now = timezone.now()
            self.session(started_at=now, ended_at=now - timedelta(minutes=1), status="completed")
