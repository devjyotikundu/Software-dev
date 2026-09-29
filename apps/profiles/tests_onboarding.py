from datetime import time

from django.test import TestCase
from django.urls import reverse

from apps.core.testing import make_user, seed_reference_data
from apps.languages.models import Language, ProficiencyLevel

from .models import AvailabilitySlot, CommunicationMode, Interest, LearningGoal, Profile


def step_url(slug):
    return reverse("onboarding:step", kwargs={"step": slug})


class OnboardingTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_reference_data()
        cls.en = Language.objects.get(code="en")
        cls.bn = Language.objects.get(code="bn")
        cls.b1 = ProficiencyLevel.objects.get(code="B1")

    def setUp(self):
        self.user = make_user("asha")
        Profile.objects.create(user=self.user, display_name="Asha")
        self.client.force_login(self.user)

    def pks(self, model, slugs):
        return [str(pk) for pk in model.objects.filter(slug__in=slugs).values_list("pk", flat=True)]

    def complete_all(self):
        self.client.post(step_url("languages"), {
            "native_language": self.bn.pk, "learning_language": self.en.pk, "level": self.b1.pk})
        self.client.post(step_url("goals"), {"goals": self.pks(LearningGoal, ["speaking"])})
        self.client.post(step_url("interests"), {"interests": self.pks(Interest, ["music", "movies"])})
        self.client.post(step_url("availability"), {
            "timezone": "Asia/Kolkata", "days": ["0", "2"], "times": ["evening"]})
        return self.client.post(step_url("communication"), {
            "communication_modes": self.pks(CommunicationMode, ["text"])})


class OnboardingAccessTests(OnboardingTestCase):
    def test_anonymous_user_is_sent_to_login(self):
        self.client.logout()
        response = self.client.get(step_url("languages"))
        self.assertIn(reverse("accounts:login"), response.headers["Location"])

    def test_unfinished_user_is_redirected_from_home(self):
        response = self.client.get(reverse("core:home"))
        self.assertRedirects(response, reverse("onboarding:start"), fetch_redirect_response=False)

    def test_start_goes_to_first_step(self):
        self.assertRedirects(self.client.get(reverse("onboarding:start")), step_url("languages"))

    def test_cannot_skip_ahead(self):
        self.assertRedirects(self.client.get(step_url("availability")), step_url("languages"))

    def test_unknown_step_is_404(self):
        self.assertEqual(self.client.get(step_url("nonsense")).status_code, 404)

    def test_account_pages_and_logout_stay_reachable(self):
        self.assertEqual(self.client.get(reverse("accounts:password_change")).status_code, 200)
        self.assertEqual(self.client.get(reverse("core:health")).status_code, 200)
        self.client.post(reverse("accounts:logout"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_account_without_profile_gets_one(self):
        admin = make_user("admin", first_name="Site", last_name="Admin")
        self.client.force_login(admin)
        self.client.get(reverse("onboarding:start"))
        self.assertEqual(Profile.objects.get(user=admin).display_name, "Site Admin")


class OnboardingStepTests(OnboardingTestCase):
    def test_step_shows_progress(self):
        response = self.client.get(step_url("languages"))
        self.assertContains(response, "Step 1 of 5")

    def test_languages_must_differ(self):
        response = self.client.post(step_url("languages"), {
            "native_language": self.en.pk, "learning_language": self.en.pk, "level": self.b1.pk})
        self.assertContains(response, "different from the one you speak")
        self.assertFalse(self.user.languages.exists())

    def test_languages_saved_and_next_step_shown(self):
        response = self.client.post(step_url("languages"), {
            "native_language": self.bn.pk, "learning_language": self.en.pk, "level": self.b1.pk})
        self.assertRedirects(response, step_url("goals"))
        rows = {ul.role: ul for ul in self.user.languages.all()}
        self.assertEqual(rows["native"].language, self.bn)
        self.assertEqual(rows["learning"].self_declared_level, self.b1)
        self.assertIsNone(rows["native"].self_declared_level)

    def test_going_back_prefills_and_resaving_replaces(self):
        data = {"native_language": self.bn.pk, "learning_language": self.en.pk, "level": self.b1.pk}
        self.client.post(step_url("languages"), data)
        response = self.client.get(step_url("languages"))
        self.assertEqual(response.context["form"].initial["level"], self.b1.pk)
        self.client.post(step_url("languages"), data)
        self.assertEqual(self.user.languages.count(), 2)

    def test_goal_required(self):
        self.client.post(step_url("languages"), {
            "native_language": self.bn.pk, "learning_language": self.en.pk, "level": self.b1.pk})
        response = self.client.post(step_url("goals"), {})
        self.assertContains(response, "Choose at least one goal")

    def test_availability_creates_one_slot_per_day_and_time(self):
        self.client.post(step_url("languages"), {
            "native_language": self.bn.pk, "learning_language": self.en.pk, "level": self.b1.pk})
        self.client.post(step_url("goals"), {"goals": self.pks(LearningGoal, ["travel"])})
        self.client.post(step_url("interests"), {"interests": self.pks(Interest, ["food"])})
        self.client.post(step_url("availability"), {
            "timezone": "Asia/Kolkata", "days": ["5", "6"], "times": ["morning", "night"]})
        profile = Profile.objects.get(user=self.user)
        self.assertEqual(profile.timezone, "Asia/Kolkata")
        slots = set(AvailabilitySlot.objects.filter(profile=profile)
                    .values_list("weekday", "start_time", "end_time"))
        self.assertEqual(slots, {
            (5, time(6), time(12)), (6, time(6), time(12)),
            (5, time(21), time(23, 59)), (6, time(21), time(23, 59)),
        })

    def test_invalid_timezone_rejected(self):
        self.client.post(step_url("languages"), {
            "native_language": self.bn.pk, "learning_language": self.en.pk, "level": self.b1.pk})
        self.client.post(step_url("goals"), {"goals": self.pks(LearningGoal, ["travel"])})
        self.client.post(step_url("interests"), {"interests": self.pks(Interest, ["food"])})
        response = self.client.post(step_url("availability"), {
            "timezone": "Mars/Base", "days": ["1"], "times": ["morning"]})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(AvailabilitySlot.objects.exists())


class OnboardingCompletionTests(OnboardingTestCase):
    def test_full_flow_completes_and_shows_welcome(self):
        response = self.complete_all()
        self.assertRedirects(response, reverse("core:home"))
        profile = Profile.objects.get(user=self.user)
        self.assertTrue(profile.is_onboarded)
        home = self.client.get(reverse("core:home"))
        self.assertTemplateUsed(home, "core/welcome.html")
        self.assertContains(home, "Welcome, Asha.")
        self.assertContains(home, "self-declared")

    def test_finished_user_cannot_reenter_onboarding(self):
        self.complete_all()
        self.assertRedirects(self.client.get(step_url("languages")), reverse("core:home"))
        self.assertRedirects(self.client.get(reverse("onboarding:start")), reverse("core:home"))


class OnboardingPresentationTests(OnboardingTestCase):
    def test_stepper_marks_done_and_current_steps(self):
        self.client.post(step_url("languages"), {
            "native_language": self.bn.pk, "learning_language": self.en.pk, "level": self.b1.pk})
        response = self.client.get(step_url("goals"))
        states = [item["state"] for item in response.context["stepper"]]
        self.assertEqual(states, ["done", "current", "todo", "todo", "todo"])
        self.assertContains(response, 'aria-current="step"')

    def test_level_options_show_descriptions(self):
        response = self.client.get(step_url("languages"))
        self.assertContains(response, self.b1.description)

    def test_profile_page_summarises_real_onboarding_data(self):
        self.complete_all()
        response = self.client.get(reverse("profiles:detail"))
        for text in ("Speaking practice", "Music", "Mon, Wed", "17:00–21:00", "Asia/Kolkata", "Text"):
            self.assertContains(response, text)
