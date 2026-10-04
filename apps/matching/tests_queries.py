"""The OR-free pair lookups that replace `a = X OR b = X` queries.

Some SQLite releases (e.g. the one bundled with Python 3.14) fail such ORs
on tables with partial unique indexes with "internal query planner error".
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase

from apps.core.testing import make_onboarded_user, seed_reference_data
from apps.languages.models import Language

from .models import Match, MatchRequest


class PairLookupTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_reference_data()
        cls.en, cls.bn = Language.objects.get(code="en"), Language.objects.get(code="bn")
        cls.a, cls.b, cls.c = (make_onboarded_user(n) for n in ("a", "b", "c"))

    def request(self, sender, receiver, status="pending"):
        return MatchRequest.objects.create(sender=sender, receiver=receiver, status=status,
                                           sender_learning_language=self.en, receiver_learning_language=self.bn)

    def match(self, x, y, status="active"):
        low, high = Match.ordered_pair(x, y)
        return Match.objects.create(user_a=low, user_b=high, status=status,
                                    user_a_learning_language=self.en, user_b_learning_language=self.bn)

    def test_involving_finds_both_sides_only(self):
        sent, received, other = self.request(self.a, self.b), self.request(self.c, self.a), self.request(self.b, self.c)
        self.assertEqual(set(MatchRequest.objects.involving(self.a)), {sent, received})
        self.assertNotIn(other, MatchRequest.objects.involving(self.a))

    def test_between_is_symmetric_and_respects_earlier_filters(self):
        first = self.request(self.a, self.b, status="declined")
        second = self.request(self.b, self.a)
        self.request(self.a, self.c)
        self.assertEqual(set(MatchRequest.objects.between(self.a, self.b)), {first, second})
        self.assertEqual(list(MatchRequest.objects.filter(status="pending").between(self.b, self.a)), [second])

    def test_match_lookups(self):
        ab, ac_ended = self.match(self.a, self.b), self.match(self.a, self.c, status="ended")
        self.assertEqual(set(Match.objects.involving(self.a)), {ab, ac_ended})
        self.assertEqual(list(Match.objects.filter(status="active").involving(self.a)), [ab])
        self.assertTrue(Match.objects.between(self.b, self.a).exists())
        self.assertFalse(Match.objects.between(self.b, self.c).exists())


class NoRiskyOrQueriesTests(TestCase):
    """Guard: don't reintroduce `Q(user_a=…) | Q(user_b=…)`-style ORs on these tables."""

    def test_source_uses_the_helpers(self):
        pattern = re.compile(r"Q\((?:room__)?(?:match__)?(?:user_a|sender)=")
        offenders = []
        for path in Path(settings.BASE_DIR, "apps").rglob("*.py"):
            if path.name.startswith("tests") or "migrations" in path.parts:
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if pattern.search(line) and "|" in line:   # an OR, not e.g. a ~Q(...) constraint
                    offenders.append(f"{path.relative_to(settings.BASE_DIR)}:{number}")
        self.assertEqual(offenders, [], "Use .involving(user) / .between(a, b) instead of an OR")
