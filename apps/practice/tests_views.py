from django.test import TestCase
from django.utils.html import escape
from django.urls import reverse

from apps.core.testing import make_onboarded_user, seed_reference_data
from apps.languages.models import Language

from .models import PracticeSession, UserProgress
from .services import sessions as svc


class PracticeViewTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_reference_data(questions=True)
        cls.en = Language.objects.get(code="en")

    def setUp(self):
        self.user = make_onboarded_user("asha", native="bn", learning="en", level="A1")
        self.client.force_login(self.user)

    def start(self):
        response = self.client.post(reverse("practice:start"), {"language": "en"})
        session = PracticeSession.objects.get(user=self.user, status="in_progress")
        self.assertRedirects(response, reverse("practice:session", kwargs={"pk": session.pk}))
        return session

    def answer_current(self, session, *, correct=True, extra=None):
        row = svc.next_answer(session)
        option = row.question.correct_option if correct else next(k for k in "ABCD" if k != row.question.correct_option)
        data = {"answer_id": row.pk, "option": option, **(extra or {})}
        return row, self.client.post(reverse("practice:answer", kwargs={"pk": session.pk}), data)


class PracticeHomeTests(PracticeViewTestCase):
    def test_lists_learning_languages_with_start_button(self):
        response = self.client.get(reverse("practice:home"))
        self.assertContains(response, "Start practice")
        self.assertContains(response, "Level 1")  # A1 learner starts at Level 1

    def test_requires_login_and_onboarding(self):
        self.client.logout()
        self.assertIn(reverse("accounts:login"), self.client.get(reverse("practice:home")).headers["Location"])

    def test_header_has_practice_link(self):
        self.assertContains(self.client.get(reverse("core:home")), reverse("practice:home"))

    def test_cannot_start_unknown_or_non_learning_language(self):
        for code in ("bn", "xx"):
            response = self.client.post(reverse("practice:start"), {"language": code}, follow=True)
            self.assertRedirects(response, reverse("practice:home"))
        self.assertFalse(PracticeSession.objects.exists())

    def test_start_requires_post(self):
        self.assertEqual(self.client.get(reverse("practice:start")).status_code, 405)


class QuestionFlowTests(PracticeViewTestCase):
    def test_question_page_never_contains_the_answer(self):
        session = self.start()
        response = self.client.get(reverse("practice:session", kwargs={"pk": session.pk}))
        row = svc.next_answer(session)
        self.assertContains(response, "Question 1 of 10")
        # No explanation, and nothing that marks which option is right.
        # (The English meaning isn't checked: for some beginner questions it is
        # the same text as an option, which the page must show.)
        self.assertNotContains(response, escape(row.question.english_explanation))
        for marker in ("is-correct", "Correct answer", "correct_option", "data-correct"):
            self.assertNotContains(response, marker)
        self.assertEqual(response.context["question"].keys(), {"id", "language", "difficulty", "category", "text", "options"})

    def test_answer_then_feedback_then_next_question(self):
        session = self.start()
        row, response = self.answer_current(session)
        feedback_url = reverse("practice:feedback", kwargs={"pk": session.pk, "position": 1})
        self.assertRedirects(response, feedback_url)
        page = self.client.get(feedback_url)
        self.assertContains(page, "Correct")
        self.assertContains(page, "+10 XP")
        # Compare with the text escaped the way the template renders it (e.g. ' -> &#x27;).
        self.assertContains(page, escape(row.question.english_explanation))
        self.assertContains(self.client.get(reverse("practice:session", kwargs={"pk": session.pk})), "Question 2 of 10")

    def test_wrong_answer_feedback_shows_correct_option(self):
        session = self.start()
        row, _ = self.answer_current(session, correct=False)
        page = self.client.get(reverse("practice:feedback", kwargs={"pk": session.pk, "position": 1}))
        self.assertContains(page, "Not quite")
        self.assertContains(page, "No XP this time")
        self.assertContains(page, "Correct answer")

    def test_xp_sent_by_the_browser_is_ignored(self):
        session = self.start()
        self.answer_current(session, correct=False, extra={"xp_awarded": 9999, "is_correct": "true", "xp": 9999})
        self.assertEqual(UserProgress.objects.get(user=self.user).total_xp, 0)

    def test_resubmitting_does_not_double_count(self):
        session = self.start()
        row, _ = self.answer_current(session)
        self.client.post(reverse("practice:answer", kwargs={"pk": session.pk}),
                         {"answer_id": row.pk, "option": row.question.correct_option})
        self.assertEqual(UserProgress.objects.get(user=self.user).questions_answered, 1)

    def test_missing_choice_shows_message(self):
        session = self.start()
        row = svc.next_answer(session)
        response = self.client.post(reverse("practice:answer", kwargs={"pk": session.pk}),
                                    {"answer_id": row.pk}, follow=True)
        self.assertContains(response, "Choose an answer first")

    def test_feedback_is_hidden_until_answered(self):
        session = self.start()
        response = self.client.get(reverse("practice:feedback", kwargs={"pk": session.pk, "position": 2}))
        self.assertRedirects(response, reverse("practice:session", kwargs={"pk": session.pk}))

    def test_full_session_leads_to_results(self):
        session = self.start()
        for _ in range(10):
            self.answer_current(session)
            session.refresh_from_db()
        response = self.client.get(reverse("practice:session", kwargs={"pk": session.pk}))
        self.assertRedirects(response, reverse("practice:results", kwargs={"pk": session.pk}))
        results = self.client.get(reverse("practice:results", kwargs={"pk": session.pk}))
        self.assertContains(results, "10/10")
        self.assertContains(results, "100%")
        self.assertContains(results, "Suggested for next time")
        self.assertContains(results, "Level 2")
        self.assertContains(results, "not CEFR levels")

    def test_results_hidden_until_finished(self):
        session = self.start()
        self.assertEqual(self.client.get(reverse("practice:results", kwargs={"pk": session.pk})).status_code, 404)

    def test_quit_ends_session(self):
        session = self.start()
        self.client.post(reverse("practice:quit", kwargs={"pk": session.pk}))
        session.refresh_from_db()
        self.assertEqual(session.status, "abandoned")


class PrivacyTests(PracticeViewTestCase):
    def test_other_users_sessions_are_404(self):
        other = make_onboarded_user("rahul", native="bn", learning="en")
        theirs = svc.start_session(other, self.en)
        urls = [
            ("get", reverse("practice:session", kwargs={"pk": theirs.pk})),
            ("get", reverse("practice:feedback", kwargs={"pk": theirs.pk, "position": 1})),
            ("get", reverse("practice:results", kwargs={"pk": theirs.pk})),
            ("post", reverse("practice:answer", kwargs={"pk": theirs.pk})),
            ("post", reverse("practice:quit", kwargs={"pk": theirs.pk})),
        ]
        for method, url in urls:
            with self.subTest(url=url):
                self.assertEqual(getattr(self.client, method)(url).status_code, 404)
        theirs.refresh_from_db()
        self.assertEqual(theirs.status, "in_progress")


class ProgressDisplayTests(PracticeViewTestCase):
    def test_profile_shows_learning_progress(self):
        response = self.client.get(reverse("profiles:detail"))
        self.assertContains(response, "Learning progress")
        self.assertContains(response, "No practice yet")
        session = self.start()
        self.answer_current(session)
        response = self.client.get(reverse("profiles:detail"))
        self.assertContains(response, "100%")
