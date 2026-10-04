from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.core.testing import make_user, seed_reference_data
from apps.languages.models import Language

from .models import Match, MatchRequest, MatchSuggestion


class MatchingModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_reference_data()
        cls.en = Language.objects.get(code="en")
        cls.bn = Language.objects.get(code="bn")

    def setUp(self):
        self.a = make_user("a")
        self.b = make_user("b")

    def request(self, **extra):
        values = {
            "sender": self.a, "receiver": self.b,
            "sender_learning_language": self.en, "receiver_learning_language": self.bn,
        }
        values.update(extra)
        return MatchRequest.objects.create(**values)

    def test_cannot_request_self(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.request(receiver=self.a)

    def test_only_one_pending_request_per_pair(self):
        self.request()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.request()

    def test_new_request_allowed_after_decline(self):
        self.request(status="declined")
        self.request()

    def test_match_pair_must_be_ordered(self):
        low, high = Match.ordered_pair(self.b, self.a)
        self.assertLess(low.pk, high.pk)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Match.objects.create(
                user_a=high, user_b=low,
                user_a_learning_language=self.en, user_b_learning_language=self.bn,
            )

    def test_one_active_match_per_pair(self):
        low, high = Match.ordered_pair(self.a, self.b)
        kwargs = {"user_a": low, "user_b": high,
                  "user_a_learning_language": self.en, "user_b_learning_language": self.bn}
        match = Match.objects.create(**kwargs)
        self.assertTrue(match.includes(self.a))
        with self.assertRaises(IntegrityError), transaction.atomic():
            Match.objects.create(**kwargs)

    def test_suggestion_score_range(self):
        from django.utils import timezone
        with self.assertRaises(IntegrityError), transaction.atomic():
            MatchSuggestion.objects.create(
                user=self.a, candidate=self.b, score=120, computed_at=timezone.now()
            )
