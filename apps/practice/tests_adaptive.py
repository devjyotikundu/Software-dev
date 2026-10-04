"""Adaptive difficulty: pure rules (no database) and integration with sessions."""
import random

from django.test import SimpleTestCase, TestCase, override_settings

from apps.core.testing import make_onboarded_user, seed_reference_data
from apps.languages.models import Language

from .models import QuestionCategory, UserCategoryStat
from .services import sessions as svc
from .services.adaptive import CategoryResult, Evidence, decide, gather_evidence, spread, xp_ceiling

RANKS = list(range(1, 11))


def evidence(prior="B1", prior_rank=4, last=None, right=0, wrong=0, rank=4, xp=5000, earlier=(), categories=()):
    recent = tuple([(True, rank)] * right + [(False, rank)] * wrong) + tuple(earlier)
    return Evidence(prior, prior_rank, last, recent, xp, tuple(categories))


def mean(distribution):
    return sum(r * c for r, c in distribution.items()) / sum(distribution.values())


class DecideRuleTests(SimpleTestCase):
    def test_first_session_starts_from_self_declared_level(self):
        plan = decide(evidence(), RANKS)
        self.assertEqual((plan.center, plan.distribution), (4, {3: 2, 4: 6, 5: 2}))
        self.assertIn("B1", plan.reasons[0])

    def test_strong_results_step_up_one_level(self):
        plan = decide(evidence(last=4.0, right=10), RANKS)
        self.assertEqual(plan.center, 5)
        self.assertEqual(plan.mode, "stretch")
        self.assertAlmostEqual(mean(plan.distribution), 5.0)

    def test_struggling_steps_down_and_leans_easier(self):
        plan = decide(evidence(last=4.0, wrong=10), RANKS)
        self.assertEqual((plan.center, plan.mode), (3, "support"))
        self.assertIn("easing off", " ".join(plan.reasons))

    def test_middling_results_hold(self):
        plan = decide(evidence(last=4.0, right=6, wrong=4), RANKS)
        self.assertEqual((plan.target, plan.center, plan.mode), (4.0, 4, "steady"))

    def test_half_steps_accumulate_gradually(self):
        base, centers = 4.0, []
        for _ in range(4):  # 70% every session
            plan = decide(evidence(last=base, right=7, wrong=3, rank=round(base)), RANKS)
            base = mean(plan.distribution)
            centers.append(plan.center)
        self.assertEqual(centers, [4, 5, 5, 6])  # half a level per session, never a jump
        self.assertAlmostEqual(base, 6.0)

    def test_change_is_capped_even_with_a_strong_trend(self):
        earlier = [(False, 5)] * 10
        plan = decide(evidence(last=5.0, right=10, rank=5, earlier=earlier), RANKS)
        self.assertEqual(plan.target, 6.0)  # +1 step +0.25 trend, capped at 1
        self.assertIn("Trend", " ".join(plan.reasons))

    def test_declining_trend_nudges_down(self):
        earlier = [(True, 5)] * 10
        plan = decide(evidence(last=5.0, right=6, wrong=4, rank=5, earlier=earlier), RANKS)
        self.assertEqual(plan.target, 4.75)
        self.assertIn("lower", " ".join(plan.reasons))

    def test_too_few_answers_holds_the_level(self):
        plan = decide(evidence(prior="A2", prior_rank=2, last=2.0, right=3, rank=2), RANKS)
        self.assertEqual(plan.target, 2.0)
        self.assertIn("Only 3 answers", plan.reasons[0])

    def test_xp_unlocks_top_levels_gradually(self):
        self.assertEqual([xp_ceiling(xp) for xp in (0, 299, 300, 800, 1500, 2500, 9999)], [6, 6, 7, 8, 9, 10, 10])
        plan = decide(evidence(prior="C2", prior_rank=9, xp=120), RANKS)
        self.assertEqual(plan.center, 6)
        self.assertIn("120 XP", " ".join(plan.reasons))

    def test_never_below_level_one(self):
        plan = decide(evidence(prior="A1", prior_rank=1, last=1.0, wrong=10, rank=1), RANKS)
        self.assertEqual(plan.center, 1)
        self.assertTrue(all(rank >= 1 for rank in plan.distribution))

    def test_weak_categories_get_extra_questions(self):
        cats = [CategoryResult(1, "Grammar", 10, 4), CategoryResult(2, "Vocabulary", 10, 10),
                CategoryResult(3, "Context", 3, 0)]  # too few answers to judge
        plan = decide(evidence(last=4.0, right=7, wrong=3, categories=cats), RANKS)
        self.assertEqual([c.name for c in plan.weak_categories], ["Grammar"])
        self.assertEqual([c.name for c in plan.strong_categories], ["Vocabulary"])
        self.assertEqual(plan.weak_question_count, 3)
        self.assertIn("grammar (40%)", " ".join(plan.reasons))

    @override_settings(PRACTICE={"ADAPTIVE": {"MAX_STEP": 0.5}})
    def test_rules_are_configurable(self):
        plan = decide(evidence(last=4.0, right=10), RANKS)
        self.assertEqual(plan.target, 4.5)


class SpreadTests(SimpleTestCase):
    def test_always_exactly_the_session_length(self):
        for mode in ("support", "steady", "stretch"):
            for target in (1, 1.5, 4.25, 9.75, 10):
                with self.subTest(mode=mode, target=target):
                    self.assertEqual(sum(spread(target, mode, RANKS, 10).values()), 10)

    def test_session_average_matches_target_away_from_the_edges(self):
        # With 10 questions the average moves in steps of 0.1, so allow 0.2.
        for mode in ("support", "steady", "stretch"):
            for target in (3, 4.5, 6.25):
                with self.subTest(mode=mode, target=target):
                    self.assertAlmostEqual(mean(spread(target, mode, RANKS, 10)), target, delta=0.2)

    def test_edges_fold_into_valid_levels(self):
        self.assertEqual(spread(1, "steady", RANKS, 10), {1: 8, 2: 2})
        self.assertEqual(set(spread(10, "stretch", RANKS, 10)) <= set(RANKS), True)


class AdaptiveSessionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_reference_data(questions=True)
        cls.en = Language.objects.get(code="en")

    def setUp(self):
        self.user = make_onboarded_user("asha", native="bn", learning="en", level="B1")

    def play(self, *, correct):
        session = svc.start_session(self.user, self.en, rng=random.Random(5))
        for _ in range(session.question_count):
            row = svc.next_answer(session)
            wrong = next(k for k in "ABCD" if k != row.question.correct_option)
            svc.submit_answer(session, row.pk, row.question.correct_option if correct else wrong)
        session.refresh_from_db()
        return session

    def test_first_session_uses_mixed_levels_easiest_first(self):
        session = svc.start_session(self.user, self.en, rng=random.Random(1))
        ranks = list(session.answers.order_by("position").values_list("difficulty__rank", flat=True))
        self.assertEqual(sorted(ranks), ranks)
        self.assertEqual({r: ranks.count(r) for r in set(ranks)}, {3: 2, 4: 6, 5: 2})

    def test_evidence_reflects_real_history(self):
        self.play(correct=True)
        ev = gather_evidence(self.user, self.en)
        self.assertEqual(ev.prior_code, "B1")
        self.assertAlmostEqual(ev.last_session_rank, 4.0)
        self.assertEqual(len(ev.recent), 10)
        self.assertTrue(all(correct for correct, _ in ev.recent))
        self.assertGreater(ev.total_xp, 0)

    def test_strong_session_moves_next_session_up(self):
        first = self.play(correct=True)
        self.assertEqual(svc.recommended_rank(first), 5)
        second = svc.start_session(self.user, self.en, rng=random.Random(2))
        self.assertEqual(svc.main_rank(second), 5)

    def test_weak_category_is_practised_more(self):
        grammar = QuestionCategory.objects.get(slug="grammar")
        UserCategoryStat.objects.create(user=self.user, language=self.en, category=grammar,
                                        questions_answered=10, correct_answers=3)
        session = svc.start_session(self.user, self.en, rng=random.Random(3))
        grammar_questions = session.answers.filter(question__category=grammar).count()
        self.assertGreaterEqual(grammar_questions, 3)  # the bank has 2 grammar questions per level

    def test_practice_home_explains_the_level(self):
        self.client.force_login(self.user)
        from django.urls import reverse
        response = self.client.get(reverse("practice:home"))
        self.assertContains(response, "Next session: mostly Level 4")
        self.assertContains(response, "Why this level?")
        self.assertContains(response, "First session: starting from your B1 estimate.")
        self.assertContains(response, "Level 4 × 6")
