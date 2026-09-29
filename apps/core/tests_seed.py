from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.languages.models import Language, ProficiencyLevel
from apps.practice.models import DifficultyLevel, QuestionCategory
from apps.profiles.models import CommunicationMode, Interest, LearningGoal


def run_seed(*args):
    out = StringIO()
    call_command("seed_data", *args, stdout=out)
    return out.getvalue()


class SeedDataCommandTests(TestCase):
    def test_seeds_all_reference_data(self):
        run_seed()
        self.assertEqual(
            set(Language.objects.values_list("code", flat=True)), {"en", "bn", "hi"}
        )
        self.assertEqual(
            list(ProficiencyLevel.objects.values_list("code", flat=True)),
            ["A1", "A2", "B1", "B2", "C1", "C2"],
        )
        self.assertEqual(DifficultyLevel.objects.count(), 10)
        self.assertEqual(QuestionCategory.objects.count(), 6)
        self.assertEqual(LearningGoal.objects.count(), 8)
        self.assertEqual(CommunicationMode.objects.count(), 3)
        self.assertTrue(Interest.objects.exists())

    def test_xp_configuration_matches_brief(self):
        run_seed()
        xp = dict(DifficultyLevel.objects.values_list("code", "xp_reward"))
        self.assertEqual(xp["A1"], 10)
        self.assertEqual(xp["A5"], 20)
        self.assertEqual(xp["A10"], 35)
        self.assertEqual(DifficultyLevel.objects.get(code="A3").label, "Level 3")

    def test_running_twice_creates_no_duplicates(self):
        run_seed()
        output = run_seed()
        self.assertEqual(Language.objects.count(), 3)
        self.assertEqual(DifficultyLevel.objects.count(), 10)
        self.assertIn("Languages: 0 created", output)

    def test_rerun_keeps_admin_edits(self):
        run_seed()
        DifficultyLevel.objects.filter(code="A1").update(xp_reward=99)
        run_seed()
        self.assertEqual(DifficultyLevel.objects.get(code="A1").xp_reward, 99)

    def test_update_flag_restores_seed_values(self):
        run_seed()
        DifficultyLevel.objects.filter(code="A1").update(xp_reward=99)
        run_seed("--update")
        self.assertEqual(DifficultyLevel.objects.get(code="A1").xp_reward, 10)


class SeedQuestionBankTests(TestCase):
    def test_loads_the_bank_once(self):
        from apps.practice.models import PracticeQuestion

        first = run_seed()
        self.assertEqual(PracticeQuestion.objects.count(), 300)
        self.assertIn("Practice questions: 300 created", first)
        second = run_seed()
        self.assertEqual(PracticeQuestion.objects.count(), 300)
        self.assertIn("Practice questions: 0 created, 300 skipped", second)

    def test_skip_questions_flag(self):
        from apps.practice.models import PracticeQuestion

        run_seed("--skip-questions")
        self.assertFalse(PracticeQuestion.objects.exists())
        self.assertEqual(Language.objects.count(), 3)
