"""Proficiency estimation: the pure model, stored assessments and how they're shown."""
import random

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.core.testing import make_onboarded_user, seed_reference_data
from apps.languages.models import Language, ProficiencyLevel
from apps.profiles.models import UserLanguage

from .services import proficiency
from .services import sessions as svc


def history(sessions, accuracy, rank, seed=4):
    """Newest-first (is_correct, rank) rows for ``sessions`` sessions of 10 answers."""
    rng, rows = random.Random(seed), []
    for _ in range(sessions):
        block = [(True, rank)] * round(accuracy * 10) + [(False, rank)] * (10 - round(accuracy * 10))
        rng.shuffle(block)
        rows = block + rows
    return rows


class ModelTests(SimpleTestCase):
    def test_success_probability_is_target_at_own_level(self):
        self.assertAlmostEqual(proficiency.success_probability(4, 4), 0.7)
        self.assertGreater(proficiency.success_probability(6, 4), 0.7)
        self.assertLess(proficiency.success_probability(2, 4), 0.7)

    def test_no_estimate_before_minimum_answers(self):
        self.assertIsNone(proficiency.estimate(history(1, 0.7, 4)[:19], prior_rank=4))

    def test_seventy_percent_at_a_level_means_that_level(self):
        result = proficiency.estimate(history(12, 0.7, 6), prior_rank=6)
        self.assertAlmostEqual(result.ability, 6.0, delta=0.2)
        self.assertEqual(result.level_code, "B2")
        self.assertGreater(result.confidence, 0.9)

    def test_harder_questions_answered_well_raise_the_estimate(self):
        easy = proficiency.estimate(history(3, 0.9, 3), prior_rank=4)
        hard = proficiency.estimate(history(3, 0.9, 7), prior_rank=4)
        self.assertGreater(hard.ability, easy.ability)

    def test_underclaiming_learner_is_lifted(self):
        result = proficiency.estimate(history(2, 1.0, 3), prior_rank=2)  # said A2, aces Level 3
        self.assertIn(result.level_code, ("B1", "B2"))

    def test_struggling_learner_is_lowered(self):
        result = proficiency.estimate(history(3, 0.2, 1), prior_rank=1)
        self.assertEqual(result.level_code, "A1")

    def test_confidence_grows_with_evidence(self):
        few = proficiency.estimate(history(2, 0.7, 4), prior_rank=4).confidence
        many = proficiency.estimate(history(10, 0.7, 4), prior_rank=4).confidence
        self.assertLess(few, many)

    def test_inconsistent_recent_answers_lower_confidence(self):
        steady = proficiency.estimate(history(6, 0.7, 5), prior_rank=4)
        shifting = proficiency.estimate(history(3, 0.9, 7, seed=1) + history(3, 0.3, 4, seed=2), prior_rank=4)
        self.assertLess(shifting.confidence, steady.confidence)
        self.assertIn("point higher", " ".join(shifting.reasons))

    def test_levels_map_consistently_with_starting_levels(self):
        self.assertEqual([proficiency.level_code_for(r) for r in (1, 2, 4, 6, 8, 9)],
                         ["A1", "A2", "B1", "B2", "C1", "C2"])

    @override_settings(PRACTICE={"PROFICIENCY": {"MIN_ANSWERS": 5}})
    def test_settings_are_configurable(self):
        self.assertIsNotNone(proficiency.estimate(history(1, 0.7, 4)[:5], prior_rank=4))


class CurrentLevelBlendTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_reference_data()
        cls.levels = {lvl.code: lvl for lvl in ProficiencyLevel.objects.all()}

    def row(self, declared, assessed=None, confidence=0.0):
        return UserLanguage(role="learning", self_declared_level=self.levels[declared],
                            assessed_level=self.levels.get(assessed), assessment_confidence=confidence)

    def test_self_declared_until_assessed(self):
        row = self.row("B1")
        self.assertEqual((row.current_level.code, row.level_source), ("B1", "self-declared"))

    def test_assessed_level_gains_weight_with_confidence(self):
        self.assertEqual(self.row("A2", "B2", 0.2).current_level.code, "A2")   # 2.4 -> A2
        self.assertEqual(self.row("A2", "B2", 0.5).current_level.code, "B1")   # 3.0 -> B1
        self.assertEqual(self.row("A2", "B2", 0.8).current_level.code, "B2")   # 3.6 -> B2
        self.assertEqual(self.row("A2", "B2", 1.0).level_source, "practice")
        self.assertEqual(self.row("A2", "B2", 0.5).level_source, "both")


class StoredAssessmentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_reference_data(questions=True)
        cls.en = Language.objects.get(code="en")

    def setUp(self):
        self.user = make_onboarded_user("asha", native="bn", learning="en", level="B1")
        self.row = self.user.languages.get(role="learning")

    def play(self, *, correct):
        session = svc.start_session(self.user, self.en, rng=random.Random(9))
        result = None
        for _ in range(session.question_count):
            answer = svc.next_answer(session)
            option = answer.question.correct_option if correct else next(
                k for k in "ABCD" if k != answer.question.correct_option)
            result = svc.submit_answer(session, answer.pk, option)
        return session, result

    def test_first_session_is_too_early_to_assess(self):
        self.play(correct=True)
        self.row.refresh_from_db()
        self.assertIsNone(self.row.assessed_level)

    def test_second_session_creates_an_assessment_and_reports_it(self):
        self.play(correct=True)
        _, result = self.play(correct=True)
        self.row.refresh_from_db()
        self.assertIsNotNone(self.row.assessed_level)
        self.assertGreater(self.row.assessment_confidence, 0)
        self.assertIsNotNone(self.row.assessed_at)
        self.assertEqual(result.level_change, (None, self.row.assessed_level.code))

    def test_results_page_shows_estimate_and_reasons(self):
        self.play(correct=True)
        session, _ = self.play(correct=True)
        self.client.force_login(self.user)
        response = self.client.get(reverse("practice:results", kwargs={"pk": session.pk}))
        self.assertContains(response, "Estimated proficiency in English")
        self.assertContains(response, "% confidence")
        self.assertContains(response, "Your comfortable level is about Level")

    def test_results_page_before_enough_answers(self):
        session, _ = self.play(correct=True)
        self.client.force_login(self.user)
        response = self.client.get(reverse("practice:results", kwargs={"pk": session.pk}))
        self.assertContains(response, "After 20 practice answers")

    def test_completion_message_via_the_view(self):
        self.play(correct=True)
        self.client.force_login(self.user)
        session = svc.start_session(self.user, self.en, rng=random.Random(2))
        for _ in range(session.question_count):
            answer = svc.next_answer(session)
            response = self.client.post(reverse("practice:answer", kwargs={"pk": session.pk}),
                                        {"answer_id": answer.pk, "option": answer.question.correct_option},
                                        follow=True)
        self.assertContains(response, "estimated proficiency from practice")

    def test_recalculate_command(self):
        from io import StringIO

        from django.core.management import call_command
        self.play(correct=True)
        self.play(correct=False)
        UserLanguage.objects.filter(pk=self.row.pk).update(assessed_level=None, assessment_confidence=0)
        out = StringIO()
        call_command("recalculate_proficiency", stdout=out)
        self.row.refresh_from_db()
        self.assertIsNotNone(self.row.assessed_level)
        self.assertIn("1 estimates changed", out.getvalue())
