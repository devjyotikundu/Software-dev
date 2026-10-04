import random
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.testing import make_onboarded_user, seed_reference_data
from apps.languages.models import Language

from .models import DifficultyLevel, PracticeAnswer, PracticeQuestion, PracticeSession, UserCategoryStat, UserProgress
from .services import sessions as svc
from .services.answers import InvalidAnswer


def answer_all(session, *, correct=True, count=None):
    """Answer the session's questions in order, right or wrong."""
    results = []
    for _ in range(count or session.question_count):
        row = svc.next_answer(session)
        wrong = next(k for k in "ABCD" if k != row.question.correct_option)
        results.append(svc.submit_answer(session, row.pk, row.question.correct_option if correct else wrong))
        session.refresh_from_db()
    return results


class SessionTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_reference_data(questions=True)
        cls.en = Language.objects.get(code="en")
        cls.bn = Language.objects.get(code="bn")

    def setUp(self):
        # Native Bengali, learning English at B1 -> starts at Level 4.
        self.user = make_onboarded_user("asha", native="bn", learning="en", level="B1")

    def start(self, **kwargs):
        return svc.start_session(self.user, self.en, rng=random.Random(3), **kwargs)


class StartSessionTests(SessionTestCase):
    def test_creates_ten_distinct_questions_around_the_mapped_level(self):
        session = self.start()
        answers = list(session.answers.select_related("difficulty"))
        self.assertEqual(len(answers), 10)
        self.assertEqual({a.difficulty.rank for a in answers}, {3, 4, 5})  # B1 -> Level 4, mixed
        self.assertEqual(len({a.question_id for a in answers}), 10)
        self.assertEqual([a.position for a in answers], list(range(1, 11)))
        self.assertTrue(all(a.question.language_id == self.en.pk for a in answers))

    def test_resumes_unfinished_session(self):
        first = self.start()
        self.assertEqual(self.start().pk, first.pk)
        self.assertEqual(PracticeSession.objects.filter(user=self.user).count(), 1)

    def test_only_learning_languages(self):
        with self.assertRaises(svc.NotLearningLanguage):
            svc.start_session(self.user, self.bn)

    def test_no_questions_available(self):
        PracticeQuestion.objects.filter(language=self.en).update(is_active=False)
        with self.assertRaises(svc.NoQuestionsAvailable):
            self.start()

    def test_short_bank_gives_a_shorter_session(self):
        keep = list(PracticeQuestion.objects.filter(language=self.en).values_list("pk", flat=True)[:4])
        PracticeQuestion.objects.filter(language=self.en).exclude(pk__in=keep).update(is_active=False)
        self.assertEqual(self.start().question_count, 4)

    @override_settings(PRACTICE={"QUESTIONS_PER_SESSION": 5})
    def test_session_length_is_configurable(self):
        self.assertEqual(self.start().answers.count(), 5)


class SubmitAnswerTests(SessionTestCase):
    def test_correct_answer_awards_level_xp_and_updates_everything(self):
        session = self.start()
        row = svc.next_answer(session)
        result = svc.submit_answer(session, row.pk, row.question.correct_option)
        self.assertTrue(result.check.is_correct)
        xp = row.difficulty.xp_reward  # from the admin-editable level table
        self.assertEqual(result.xp.total, xp)
        row.refresh_from_db(); session.refresh_from_db()
        self.assertEqual((row.is_correct, row.xp_awarded), (True, xp))
        self.assertEqual((session.correct_count, session.xp_earned), (1, xp))
        progress = UserProgress.objects.get(user=self.user, language=self.en)
        self.assertEqual((progress.total_xp, progress.questions_answered, progress.correct_answers), (xp, 1, 1))
        self.assertEqual(UserCategoryStat.objects.get(user=self.user, category=row.question.category).correct_answers, 1)

    def test_wrong_answer_earns_nothing(self):
        session = self.start()
        result, = answer_all(session, correct=False, count=1)
        self.assertEqual(result.xp.total, 0)
        self.assertEqual(UserProgress.objects.get(user=self.user).correct_answers, 0)

    def test_answers_must_be_given_in_order(self):
        session = self.start()
        later = session.answers.get(position=3)
        with self.assertRaises(svc.AnswerOutOfOrder):
            svc.submit_answer(session, later.pk, "A")

    def test_same_question_cannot_be_answered_twice(self):
        session = self.start()
        row = svc.next_answer(session)
        svc.submit_answer(session, row.pk, row.question.correct_option)
        with self.assertRaises(svc.AnswerOutOfOrder):
            svc.submit_answer(session, row.pk, row.question.correct_option)
        self.assertEqual(UserProgress.objects.get(user=self.user).questions_answered, 1)

    def test_invalid_option_changes_nothing(self):
        session = self.start()
        row = svc.next_answer(session)
        with self.assertRaises(InvalidAnswer):
            svc.submit_answer(session, row.pk, "Z")
        row.refresh_from_db()
        self.assertIsNone(row.answered_at)

    def test_cannot_answer_another_sessions_question(self):
        session = self.start()
        other = make_onboarded_user("rahul", native="bn", learning="en")
        other_session = svc.start_session(other, self.en)
        foreign = svc.next_answer(other_session)
        with self.assertRaises(svc.AnswerOutOfOrder):
            svc.submit_answer(session, foreign.pk, "A")

    def test_streak_bonus_on_third_correct_answer(self):
        session = self.start()
        results = answer_all(session, count=3)
        self.assertEqual([r.xp.streak_bonus for r in results], [0, 0, 5])


class FinishSessionTests(SessionTestCase):
    def test_last_answer_completes_session(self):
        session = self.start()
        results = answer_all(session)
        self.assertTrue(results[-1].session_complete)
        self.assertFalse(any(r.session_complete for r in results[:-1]))
        session.refresh_from_db()
        self.assertEqual(session.status, "completed")
        self.assertIsNotNone(session.completed_at)
        progress = UserProgress.objects.get(user=self.user)
        self.assertEqual((progress.sessions_completed, progress.questions_answered), (1, 10))
        # Sum of each question's level XP, plus 3 streak bonuses (3rd, 6th, 9th) × 5.
        expected = sum(session.answers.values_list("difficulty__xp_reward", flat=True)) + 15
        self.assertEqual(session.xp_earned, expected)
        self.assertEqual(progress.total_xp, expected)

    def test_completed_session_rejects_answers(self):
        session = self.start()
        answer_all(session)
        with self.assertRaises(svc.SessionNotActive):
            svc.submit_answer(session, session.answers.first().pk, "A")

    def test_strong_session_suggests_next_level_and_next_session_uses_it(self):
        session = self.start()
        answer_all(session)
        self.assertEqual(svc.recommended_rank(session), 5)
        self.assertEqual(svc.starting_rank(self.user, self.en), 5)
        new = self.start()
        self.assertEqual(svc.main_rank(new), 5)

    def test_weak_session_suggests_easier_level(self):
        session = self.start()
        answer_all(session, correct=False)
        self.assertEqual(svc.recommended_rank(session), 3)
        self.assertEqual(svc.performance_summary(session)["band"], "Building up")

    def test_abandon_keeps_xp_but_ends_session(self):
        session = self.start()
        answer_all(session, count=2)
        self.assertTrue(svc.abandon_session(session))
        session.refresh_from_db()
        self.assertEqual(session.status, "abandoned")
        self.assertEqual(UserProgress.objects.get(user=self.user).questions_answered, 2)
        self.assertNotEqual(self.start().pk, session.pk)

    def test_recent_questions_are_not_repeated_next_session(self):
        first = self.start()
        answer_all(first)
        # Force the next session to the same level so repeats would be possible.
        PracticeSession.objects.filter(pk=first.pk).update(completed_at=timezone.now() - timedelta(days=1))
        with override_settings(PRACTICE={"ADAPTIVE": {"STEP_RULES": []}}):
            second = self.start()
        overlap = set(first.answers.values_list("question_id", flat=True)) & set(
            second.answers.values_list("question_id", flat=True))
        self.assertEqual(overlap, set())
