"""Checks on the curated question bank itself (the seeded JSON files)."""
from collections import Counter

from django.test import TestCase

from apps.core.testing import seed_reference_data

from .models import PracticeQuestion, QuestionCategory


class QuestionBankTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_reference_data(questions=True)

    def test_ten_servable_questions_per_level_per_language(self):
        counts = Counter(
            PracticeQuestion.objects.servable().values_list("language__code", "difficulty__rank")
        )
        for code in ("en", "bn", "hi"):
            for rank in range(1, 11):
                with self.subTest(language=code, level=rank):
                    self.assertEqual(counts[(code, rank)], 10)

    def test_every_level_covers_every_category(self):
        all_categories = set(QuestionCategory.objects.values_list("slug", flat=True))
        seen = {}
        for code, rank, slug in PracticeQuestion.objects.values_list(
            "language__code", "difficulty__rank", "category__slug"
        ):
            seen.setdefault((code, rank), set()).add(slug)
        for key, slugs in seen.items():
            with self.subTest(language_level=key):
                self.assertEqual(slugs, all_categories)

    def test_correct_answers_are_evenly_spread(self):
        for code in ("en", "bn", "hi"):
            letters = Counter(
                PracticeQuestion.objects.filter(language__code=code)
                .values_list("correct_option", flat=True)
            )
            with self.subTest(language=code):
                self.assertEqual(letters, {"A": 25, "B": 25, "C": 25, "D": 25})

    def test_every_question_is_complete_and_valid(self):
        for question in PracticeQuestion.objects.all():
            with self.subTest(pk=question.pk):
                question.full_clean()  # four distinct options, valid answer, required text
                self.assertTrue(question.english_meaning.strip())
                self.assertTrue(question.english_explanation.strip())

    def test_review_status(self):
        """English is marked reviewed; Bengali and Hindi await a fluent reviewer but are served."""
        self.assertEqual(PracticeQuestion.objects.filter(language__code="en", is_verified=True).count(), 100)
        self.assertFalse(
            PracticeQuestion.objects.filter(language__code__in=["bn", "hi"], is_verified=True).exists()
        )
        self.assertEqual(PracticeQuestion.objects.servable().filter(language__code="bn").count(), 100)

    def test_bengali_and_hindi_use_their_own_scripts(self):
        ranges = {"bn": ("\u0980", "\u09FF"), "hi": ("\u0900", "\u097F")}
        for code, (low, high) in ranges.items():
            texts = PracticeQuestion.objects.filter(language__code=code).values_list("question_text", flat=True)
            with self.subTest(language=code):
                self.assertTrue(all(any(low <= ch <= high for ch in text) for text in texts))
