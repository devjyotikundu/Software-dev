from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.core.testing import make_user, seed_reference_data
from apps.exchange.models import ExchangeRoom, ExchangeSession
from apps.languages.models import Language
from apps.matching.models import Match

from .models import SessionFeedback


class FeedbackModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_reference_data()
        en, bn = Language.objects.get(code="en"), Language.objects.get(code="bn")
        cls.a, cls.b = make_user("a"), make_user("b")
        low, high = Match.ordered_pair(cls.a, cls.b)
        room = ExchangeRoom.objects.create(match=Match.objects.create(
            user_a=low, user_b=high, user_a_learning_language=en, user_b_learning_language=bn,
        ))
        cls.session = ExchangeSession.objects.create(
            room=room, first_language=en, second_language=bn, status="completed"
        )

    def feedback(self, **extra):
        values = {"session": self.session, "reviewer": self.a, "reviewee": self.b,
                  "usefulness": 4, "would_practice_again": True, "difficulty": "comfortable"}
        values.update(extra)
        return SessionFeedback.objects.create(**values)

    def test_one_feedback_per_reviewer_per_session(self):
        self.feedback()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.feedback()

    def test_usefulness_range(self):
        for value in (0, 6):
            with self.subTest(value=value):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    self.feedback(usefulness=value)

    def test_cannot_review_self(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.feedback(reviewee=self.a)
