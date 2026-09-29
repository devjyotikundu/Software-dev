import json
import tempfile
from pathlib import Path

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.utils import timezone

from apps.core.testing import make_user, seed_reference_data
from apps.languages.models import Language

from .models import (
    DifficultyLevel, PracticeAnswer, PracticeQuestion, PracticeSession,
    QuestionCategory, UserProgress,
)
from .question_loader import QuestionFileError, load_question_file


def valid_item(**overrides):
    item = {
        "difficulty": "A1",
        "category": "vocabulary",
        "question_text": "What does “জল” mean?",
        "options": {"A": "Fire", "B": "Water", "C": "Air", "D": "Earth"},
        "correct_option": "B",
        "english_meaning": "What does “jol” mean?",
        "english_explanation": "জল (jol) means water.",
        "verified": True,
    }
    item.update(overrides)
    return item


class QuestionTestMixin:
    @classmethod
    def setUpTestData(cls):
        seed_reference_data()
        cls.bn = Language.objects.get(code="bn")
        cls.level1 = DifficultyLevel.objects.get(code="A1")
        cls.vocab = QuestionCategory.objects.get(slug="vocabulary")

    def make_question(self, text="Question?", options=("w", "x", "y", "z"), **extra):
        a, b, c, d = options
        return PracticeQuestion.objects.create(
            language=self.bn, difficulty=self.level1, category=self.vocab,
            question_text=text, option_a=a, option_b=b, option_c=c, option_d=d,
            correct_option="A", english_meaning="m", english_explanation="e", **extra,
        )


class PracticeQuestionTests(QuestionTestMixin, TestCase):
    def test_duplicate_content_rejected(self):
        self.make_question()
        with self.assertRaises(IntegrityError), transaction.atomic():
            # Same content, different spacing and option order.
            self.make_question(text="  question? ", options=("z", "y", "x", "w"))

    def test_invalid_correct_option_rejected(self):
        question = self.make_question()
        with self.assertRaises(IntegrityError), transaction.atomic():
            PracticeQuestion.objects.filter(pk=question.pk).update(correct_option="E")

    def test_duplicate_options_fail_validation(self):
        question = PracticeQuestion(
            language=self.bn, difficulty=self.level1, category=self.vocab,
            question_text="Q", option_a="same", option_b="Same", option_c="x", option_d="y",
            correct_option="A", english_meaning="m", english_explanation="e",
        )
        with self.assertRaisesMessage(ValidationError, "must be different"):
            question.full_clean()


class PracticeSessionTests(QuestionTestMixin, TestCase):
    def setUp(self):
        self.user = make_user("rahul")

    def test_one_in_progress_session_per_language(self):
        PracticeSession.objects.create(user=self.user, language=self.bn)
        with self.assertRaises(IntegrityError), transaction.atomic():
            PracticeSession.objects.create(user=self.user, language=self.bn)

    def test_completed_sessions_do_not_block_new_ones(self):
        PracticeSession.objects.create(user=self.user, language=self.bn, status="completed")
        PracticeSession.objects.create(user=self.user, language=self.bn)

    def test_answer_must_be_fully_recorded(self):
        session = PracticeSession.objects.create(user=self.user, language=self.bn)
        question = self.make_question()
        with self.assertRaises(IntegrityError), transaction.atomic():
            # Answered time set but no selected option: inconsistent.
            PracticeAnswer.objects.create(
                session=session, question=question, difficulty=self.level1,
                position=1, answered_at=timezone.now(), is_correct=True,
            )

    def test_valid_unanswered_then_answered(self):
        session = PracticeSession.objects.create(user=self.user, language=self.bn)
        answer = PracticeAnswer.objects.create(
            session=session, question=self.make_question(), difficulty=self.level1, position=1
        )
        answer.selected_option = "A"
        answer.is_correct = True
        answer.xp_awarded = 10
        answer.answered_at = timezone.now()
        answer.save()

    def test_same_question_twice_in_a_session_rejected(self):
        session = PracticeSession.objects.create(user=self.user, language=self.bn)
        question = self.make_question()
        PracticeAnswer.objects.create(
            session=session, question=question, difficulty=self.level1, position=1
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            PracticeAnswer.objects.create(
                session=session, question=question, difficulty=self.level1, position=2
            )

    def test_answered_question_cannot_be_deleted(self):
        session = PracticeSession.objects.create(user=self.user, language=self.bn)
        question = self.make_question()
        PracticeAnswer.objects.create(
            session=session, question=question, difficulty=self.level1, position=1
        )
        with self.assertRaises(ProtectedError):
            question.delete()


class UserProgressTests(QuestionTestMixin, TestCase):
    def test_accuracy(self):
        progress = UserProgress(questions_answered=0, correct_answers=0)
        self.assertIsNone(progress.accuracy)
        progress.questions_answered, progress.correct_answers = 8, 6
        self.assertEqual(progress.accuracy, 0.75)

    def test_correct_cannot_exceed_answered(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            UserProgress.objects.create(
                user=make_user("x"), language=self.bn, questions_answered=1, correct_answers=2
            )


class QuestionLoaderTests(QuestionTestMixin, TestCase):
    def write(self, payload):
        directory = tempfile.mkdtemp()
        path = Path(directory) / "bn.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def test_loads_valid_file_and_skips_repeats(self):
        path = self.write({"language": "bn", "questions": [valid_item()]})
        self.assertEqual(load_question_file(path), {"created": 1, "skipped": 0})
        self.assertEqual(load_question_file(path), {"created": 0, "skipped": 1})
        question = PracticeQuestion.objects.get()
        self.assertTrue(question.is_verified)
        self.assertEqual(question.correct_option, "B")

    def test_invalid_question_loads_nothing(self):
        path = self.write({"language": "bn", "questions": [
            valid_item(),
            valid_item(question_text="Other", correct_option="E"),
        ]})
        with self.assertRaisesMessage(QuestionFileError, "question 2"):
            load_question_file(path)
        self.assertFalse(PracticeQuestion.objects.exists())

    def test_rejects_unknown_language_difficulty_and_category(self):
        for payload, message in [
            ({"language": "xx", "questions": [valid_item()]}, "unknown language"),
            ({"language": "bn", "questions": [valid_item(difficulty="A11")]}, "unknown difficulty"),
            ({"language": "bn", "questions": [valid_item(category="poetry")]}, "unknown category"),
        ]:
            with self.subTest(message=message), self.assertRaisesMessage(QuestionFileError, message):
                load_question_file(self.write(payload))

    def test_rejects_duplicate_or_missing_options(self):
        bad_options = [
            {"A": "x", "B": "x", "C": "y", "D": "z"},
            {"A": "x", "B": "y", "C": "z"},
        ]
        for options in bad_options:
            with self.subTest(options=options), self.assertRaises(QuestionFileError):
                load_question_file(
                    self.write({"language": "bn", "questions": [valid_item(options=options)]})
                )
