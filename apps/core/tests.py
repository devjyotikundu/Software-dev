from unittest import mock

from django.db import DatabaseError
from django.test import TestCase
from django.urls import reverse


class HomePageTests(TestCase):
    def test_home_page_renders(self):
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/home.html")
        self.assertTemplateUsed(response, "base.html")

    def test_home_page_shows_greetings_with_language_tags(self):
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, 'lang="bn"')
        self.assertContains(response, 'lang="hi"')

    def test_home_page_has_no_dead_links(self):
        """Every internal link on the page must resolve (no placeholder '#')."""
        response = self.client.get(reverse("core:home"))
        self.assertNotContains(response, 'href="#"')


class HealthCheckTests(TestCase):
    def test_health_ok(self):
        response = self.client.get(reverse("core:health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "database": "ok"})

    def test_health_reports_database_failure_without_details(self):
        with mock.patch("apps.core.views.connection") as fake_connection:
            fake_connection.ensure_connection.side_effect = DatabaseError(
                "secret connection string"
            )
            with self.assertLogs("apps.core.views", level="ERROR"):
                response = self.client.get(reverse("core:health"))
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("secret", response.content.decode())

    def test_health_rejects_post(self):
        response = self.client.post(reverse("core:health"))
        self.assertEqual(response.status_code, 405)

    def test_health_is_not_cached(self):
        response = self.client.get(reverse("core:health"))
        self.assertIn("no-cache", response.headers.get("Cache-Control", ""))


class ErrorPageTests(TestCase):
    def test_unknown_url_uses_friendly_404(self):
        response = self.client.get("/this-page-does-not-exist/")
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "404.html")
        self.assertContains(response, "Page not found", status_code=404)


class SecurityHeaderTests(TestCase):
    def test_baseline_security_headers(self):
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(response.headers.get("Referrer-Policy"), "same-origin")


class HomePageAccountLinkTests(TestCase):
    def test_visitors_see_sign_up_and_log_in(self):
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, reverse("accounts:register"))
        self.assertContains(response, reverse("accounts:login"))


class LandingPageTests(TestCase):
    def test_landing_page_pieces_are_wired_up(self):
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, 'class="lx-landing')            # dark landing styles
        self.assertContains(response, "js/landing.js")                # sphere and scroll story
        self.assertContains(response, "img/people.webp")              # the photo, served as a static file
        self.assertContains(response, "data-sphere")
        self.assertContains(response, "Find a partner")
        self.assertContains(response, reverse("accounts:register"))

    def test_signed_in_users_still_get_their_dashboard(self):
        from apps.core.testing import make_onboarded_user, seed_reference_data
        seed_reference_data()
        self.client.force_login(make_onboarded_user("asha"))
        response = self.client.get(reverse("core:home"))
        self.assertTemplateUsed(response, "core/welcome.html")
        self.assertNotContains(response, "lx-landing")
