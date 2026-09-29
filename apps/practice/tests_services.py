import random

from django.test import TestCase

from apps.core.testing import make_user, seed_reference_data
from apps.languages.models import Language

from .models import DifficultyLevel, PracticeAnswer, PracticeQuestion, PracticeSession, QuestionCategory
from .services.answers import InvalidAnswer, check_answer, public_question
from .services.questions import pick_questions, ranks_by_distance


class BankMixin:
    @classmethod
    def setUpTestData(cls):
        seed_reference_data()
        cls.bn = Language.objects.get(code="bn")
        cls.levels = {d.rank: d for d in DifficultyLevel.objects.all()}
        cls.vocab = QuestionCategory.objects.get(slug="vocabulary")

    @classmethod
    def add_questions(cls, rank, n, **extra):
        made = []
        for i in range(n):
            made.append(PracticeQuestion.objects.create(
                language=cls.bn, difficulty=cls.levels[rank], category=cls.vocab,
                question_text=f"Level {rank} question {i} {extra}", option_a="a", option_b="b",
                option_c="c", option_d="d", correct_option="B",
                english_meaning="m", english_explanation="e", **extra,
            ))
        return made


class ServableTests(BankMixin, TestCase):
    def test_inactive_questions_are_not_served(self):
        q, = self.add_questions(1, 1)
        PracticeQuestion.objects.filter(pk=q.pk).update(is_active=False)
        self.assertFalse(PracticeQuestion.objects.servable().filter(pk=q.pk).exists())

    def test_disabled_difficulty_hides_its_questions(self):
        q, = self.add_questions(4, 1)
        DifficultyLevel.objects.filter(rank=4).update(is_active=False)
        self.assertFalse(PracticeQuestion.objects.servable().filter(pk=q.pk).exists())

    def test_unreviewed_ai_questions_are_not_served(self):
        q, = self.add_questions(2, 1, source=PracticeQuestion.Source.AI)
        self.assertFalse(PracticeQuestion.objects.servable().filter(pk=q.pk).exists())
        PracticeQuestion.objects.filter(pk=q.pk).update(is_verified=True)
        self.assertTrue(PracticeQuestion.objects.servable().filter(pk=q.pk).exists())

    def test_bank_questions_are_served_before_review(self):
        q, = self.add_questions(2, 1)
        self.assertFalse(q.is_verified)
        self.assertTrue(PracticeQuestion.objects.servable().filter(pk=q.pk).exists())


class PickQuestionsTests(BankMixin, TestCase):
    def setUp(self):
        self.rng = random.Random(7)

    def test_ranks_by_distance(self):
        self.assertEqual(ranks_by_distance(5, [1, 3, 4, 5, 6, 7, 10]), [5, 4, 6, 3, 7, 1, 10])

    def test_returns_requested_level_first(self):
        self.add_questions(3, 12)
        self.add_questions(4, 12)
        picked = pick_questions(language=self.bn, difficulty=self.levels[3], count=10, rng=self.rng)
        self.assertEqual(len(picked), 10)
        self.assertTrue(all(q.difficulty.rank == 3 for q in picked))
        self.assertEqual(len({q.pk for q in picked}), 10)

    def test_widens_to_nearest_levels_when_short(self):
        self.add_questions(5, 4)
        self.add_questions(4, 3)
        self.add_questions(6, 3)
        self.add_questions(9, 5)
        picked = pick_questions(language=self.bn, difficulty=self.levels[5], count=10, rng=self.rng)
        self.assertEqual(sorted(q.difficulty.rank for q in picked), [4, 4, 4, 5, 5, 5, 5, 6, 6, 6])

    def test_avoids_recently_answered_questions(self):
        questions = self.add_questions(2, 15)
        user = make_user("learner")
        session = PracticeSession.objects.create(user=user, language=self.bn, status="completed")
        seen = questions[:10]
        for position, q in enumerate(seen, 1):
            PracticeAnswer.objects.create(session=session, question=q, difficulty=q.difficulty, position=position)
        picked = pick_questions(language=self.bn, difficulty=self.levels[2], count=5, user=user, rng=self.rng)
        self.assertEqual({q.pk for q in picked}, {q.pk for q in questions[10:]})

    def test_reuses_recent_questions_only_when_bank_runs_out(self):
        questions = self.add_questions(2, 6)
        user = make_user("learner")
        session = PracticeSession.objects.create(user=user, language=self.bn, status="completed")
        for position, q in enumerate(questions[:4], 1):
            PracticeAnswer.objects.create(session=session, question=q, difficulty=q.difficulty, position=position)
        picked = pick_questions(language=self.bn, difficulty=self.levels[2], count=6, user=user, rng=self.rng)
        self.assertEqual(len(picked), 6)
        self.assertEqual({q.pk for q in picked[:2]}, {q.pk for q in questions[4:]})  # fresh ones first

    def test_respects_exclusions_and_language(self):
        mine = self.add_questions(1, 5)
        en = Language.objects.get(code="en")
        PracticeQuestion.objects.create(
            language=en, difficulty=self.levels[1], category=self.vocab, question_text="English one",
            option_a="a", option_b="b", option_c="c", option_d="d", correct_option="A",
            english_meaning="m", english_explanation="e",
        )
        picked = pick_questions(language=self.bn, difficulty=self.levels[1], count=10,
                                exclude_ids=[mine[0].pk], rng=self.rng)
        self.assertEqual({q.pk for q in picked}, {q.pk for q in mine[1:]})
        self.assertTrue(all(q.language_id == self.bn.pk for q in picked))

    def test_same_seed_gives_same_selection(self):
        self.add_questions(3, 20)
        first = pick_questions(language=self.bn, difficulty=self.levels[3], count=10, rng=random.Random(1))
        second = pick_questions(language=self.bn, difficulty=self.levels[3], count=10, rng=random.Random(1))
        self.assertEqual([q.pk for q in first], [q.pk for q in second])

    def test_query_count_is_constant(self):
        self.add_questions(3, 20)
        with self.assertNumQueries(2):  # candidate ids, then the chosen questions
            picked = pick_questions(language=self.bn, difficulty=self.levels[3], count=10, rng=self.rng)
            [q.category.name for q in picked]


class CheckAnswerTests(BankMixin, TestCase):
    def setUp(self):
        self.question, = self.add_questions(1, 1)

    def test_correct_answer(self):
        result = check_answer(self.question, "B")
        self.assertTrue(result.is_correct)
        self.assertEqual((result.correct_option, result.correct_text), ("B", "b"))

    def test_incorrect_answer_still_reveals_correct_one(self):
        result = check_answer(self.question, "C")
        self.assertFalse(result.is_correct)
        self.assertEqual(result.correct_option, "B")
        self.assertEqual(result.english_explanation, "e")

    def test_input_is_normalised(self):
        self.assertTrue(check_answer(self.question, " b ").is_correct)

    def test_invalid_options_rejected(self):
        for bad in ("E", "", None, "AB", "1"):
            with self.subTest(value=bad), self.assertRaises(InvalidAnswer):
                check_answer(self.question, bad)

    def test_public_question_hides_the_answer(self):
        data = public_question(self.question)
        flat = repr(data)
        self.assertEqual([o["key"] for o in data["options"]], ["A", "B", "C", "D"])
        for secret in ("correct", "explanation", "meaning"):
            self.assertNotIn(secret, flat)
        self.assertEqual(data["difficulty"]["label"], "Level 1")
