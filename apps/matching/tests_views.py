"""Discovery pages, match detail and the dashboard."""
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import reverse

from apps.accounts.models import BlockedUser
from apps.core.testing import make_onboarded_user, seed_reference_data
from apps.profiles.models import CommunicationMode, LearningGoal, Profile

from .services.suggestions import refresh_suggestions


class DiscoveryTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_reference_data()

    def setUp(self):
        self.asha = make_onboarded_user("asha", native="bn", learning="en", level="B1")
        self.tom = make_onboarded_user("tom", native="en", learning="bn", level="B2")
        self.client.force_login(self.asha)

    def discover(self, **params):
        return self.client.get(reverse("matching:discover"), params)


class DiscoverPageTests(DiscoveryTestCase):
    def test_requires_login(self):
        self.client.logout()
        self.assertIn(reverse("accounts:login"), self.discover().headers["Location"])

    def test_shows_reciprocal_partner_card(self):
        response = self.discover()
        self.assertContains(response, "Tom")
        self.assertContains(response, "Speaks English")
        self.assertContains(response, "Learning Bengali, B2")
        self.assertContains(response, "% match")
        self.assertContains(response, "View match")
        self.assertContains(response, reverse("matching:detail", kwargs={"user_id": self.tom.pk}))

    def test_card_shows_common_interests_and_goal(self):
        response = self.discover()
        self.assertContains(response, "Music")
        self.assertContains(response, "Speaking practice")

    def test_private_details_are_never_shown(self):
        for response in (self.discover(), self.client.get(reverse("matching:detail", kwargs={"user_id": self.tom.pk}))):
            body = response.content.decode()
            self.assertNotIn(self.tom.email, body)
            # The viewer's own address appears once, in their account menu; nobody else's does.
            self.assertEqual(body.count("@example.com"), 1)

    def test_empty_state(self):
        Profile.objects.filter(user=self.tom).update(is_discoverable=False)
        response = self.discover()
        self.assertContains(response, "No partners to suggest yet")

    def test_hidden_user_sees_a_notice(self):
        Profile.objects.filter(user=self.asha).update(is_discoverable=False)
        self.assertContains(self.discover(), "You're hidden from partner suggestions")

    def test_header_links_to_discover(self):
        self.assertContains(self.client.get(reverse("core:home")), reverse("matching:discover"))


class FilterTests(DiscoveryTestCase):
    def test_goal_filter(self):
        grammar = LearningGoal.objects.get(slug="grammar")
        response = self.discover(goal=grammar.pk)
        self.assertContains(response, "No one matches these filters")
        self.tom.profile.goals.add(grammar)
        self.assertContains(self.discover(goal=grammar.pk), "Showing 1 of 1")

    def test_mode_filter(self):
        video = CommunicationMode.objects.get(slug="video")
        self.assertContains(self.discover(mode=video.pk), "No one matches these filters")
        text = CommunicationMode.objects.get(slug="text")
        self.assertContains(self.discover(mode=text.pk), "Tom")

    def test_availability_filter(self):
        from datetime import time
        self.assertContains(self.discover(overlap="on"), "Tom")  # both Monday 17:00–21:00 Kolkata
        slot = self.tom.profile.availability_slots.get()
        slot.weekday, slot.start_time, slot.end_time = 3, time(6), time(7)
        slot.save()
        refresh_suggestions(self.asha)
        self.assertContains(self.discover(overlap="on"), "No one matches these filters")

    def test_invalid_filter_values_are_ignored_safely(self):
        response = self.discover(goal="999999", mode="abc", language="x")
        self.assertEqual(response.status_code, 200)

    def test_pagination_keeps_filters(self):
        for i in range(13):
            make_onboarded_user(f"p{i}", native="en", learning="bn")
        text = CommunicationMode.objects.get(slug="text")
        response = self.discover(mode=text.pk)
        self.assertContains(response, "Page 1 of 2")
        self.assertContains(response, f"mode={text.pk}&amp;page=2")


class MatchDetailTests(DiscoveryTestCase):
    def detail(self, user):
        return self.client.get(reverse("matching:detail", kwargs={"user_id": user.pk}))

    def test_explains_the_match_with_real_data(self):
        response = self.detail(self.tom)
        self.assertContains(response, "Why this match?")
        # Django autoescapes the apostrophe (&#x27;), so compare against the escaped HTML.
        self.assertContains(response, "You&#x27;re learning English, which they speak natively")
        self.assertContains(response, "one level apart")
        self.assertContains(response, "Shared interests: Music and Movies.")
        self.assertContains(response, "Monday 17:00–21:00 your time")
        self.assertContains(response, "How the")
        suggestion = response.context["card"].suggestion
        self.assertContains(response, str(suggestion.score))

    def test_factor_points_add_up_to_score(self):
        response = self.detail(self.tom)
        total = sum(f["points"] for f in response.context["factors"])
        self.assertAlmostEqual(total, float(response.context["card"].suggestion.score), places=1)

    def test_only_current_suggestions_can_be_opened(self):
        stranger = make_onboarded_user("rahul", native="en", learning="hi")  # not reciprocal
        self.assertEqual(self.detail(stranger).status_code, 404)
        self.assertEqual(self.detail(self.asha).status_code, 404)

    def test_blocked_people_cannot_be_opened(self):
        self.detail(self.tom)
        BlockedUser.objects.create(blocker=self.tom, blocked=self.asha)
        self.assertEqual(self.detail(self.tom).status_code, 404)

    def test_detail_has_request_form_and_safety_menu(self):
        response = self.detail(self.tom)
        self.assertContains(response, "Send request")
        self.assertContains(response, reverse("matching:request", kwargs={"user_id": self.tom.pk}))
        self.assertContains(response, reverse("partners:block", kwargs={"user_id": self.tom.pk}))


class DashboardTests(DiscoveryTestCase):
    def test_dashboard_shows_learning_level_partners_and_actions(self):
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "Welcome, Asha.")
        self.assertContains(response, "Estimated B1")
        self.assertContains(response, "Suggested partners")
        self.assertContains(response, "Tom")
        self.assertContains(response, "Discover partners")
        self.assertContains(response, "No practice yet")

    def test_dashboard_shows_at_most_two_partners(self):
        for i in range(3):
            make_onboarded_user(f"x{i}", native="en", learning="bn")
        response = self.client.get(reverse("core:home"))
        self.assertEqual(len(response.context["partners"]), 2)


class QueryCountTests(DiscoveryTestCase):
    def test_discover_page_queries_do_not_grow_with_partners(self):
        def count():
            refresh_suggestions(self.asha)
            with CaptureQueriesContext(connection) as ctx:
                self.discover()
            return len(ctx.captured_queries)

        few = count()
        for i in range(5):
            make_onboarded_user(f"q{i}", native="en", learning="bn")
        self.assertEqual(count(), few)
