"""Security hardening: rate limits, login lockout, client IP, headers, templates."""
import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.core import ratelimit
from apps.core.secrets import weak_secret_key
from apps.core.testing import PASSWORD, make_onboarded_user, make_user, seed_reference_data

LOW = {"login_failures": (3, 900), "register": (2, 3600), "password_reset": (2, 3600),
       "match_request": (1, 3600), "report": (1, 3600), "room_message_post": (2, 60)}


class ClientIpTests(TestCase):
    def request(self, xff=None, remote="10.0.0.9"):
        meta = {"REMOTE_ADDR": remote}
        if xff:
            meta["HTTP_X_FORWARDED_FOR"] = xff
        return RequestFactory().get("/", **meta)

    def test_without_a_proxy_uses_the_connection_address(self):
        self.assertEqual(ratelimit.client_ip(self.request(xff="1.2.3.4")), "10.0.0.9")

    @override_settings(NUM_PROXIES=1)
    def test_behind_one_proxy_ignores_spoofed_entries(self):
        self.assertEqual(ratelimit.client_ip(self.request(xff="6.6.6.6, 203.0.113.7")), "203.0.113.7")
        self.assertEqual(ratelimit.client_ip(self.request()), "10.0.0.9")


@override_settings(RATE_LIMITS=LOW)
class LoginLockoutTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_user("rahul")  # rahul@example.com

    def login(self, password, email="rahul@example.com", ip="198.51.100.1"):
        return self.client.post(reverse("accounts:login"), {"username": email, "password": password}, REMOTE_ADDR=ip)

    def test_locks_after_repeated_failures_even_with_the_right_password(self):
        for _ in range(3):
            self.assertContains(self.login("wrong"), "Email or password is incorrect")
        response = self.login(PASSWORD)
        self.assertContains(response, "Too many unsuccessful attempts")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_lock_is_per_account_and_ip(self):
        for _ in range(3):
            self.login("wrong")
        self.assertEqual(self.login(PASSWORD, ip="198.51.100.2").status_code, 302)   # other network
        self.client.logout()
        make_user("meera")
        self.assertEqual(self.login(PASSWORD, email="meera@example.com").status_code, 302)  # other account

    def test_success_resets_the_counter(self):
        self.login("wrong"); self.login("wrong")
        self.assertEqual(self.login(PASSWORD).status_code, 302)
        self.client.logout()
        self.login("wrong"); self.login("wrong")
        self.assertEqual(self.login(PASSWORD).status_code, 302)

    def test_admin_login_is_protected_too(self):
        get_user_model().objects.create_superuser("boss", "boss@example.com", PASSWORD)
        url = reverse("admin:login")
        for _ in range(3):
            self.client.post(url, {"username": "boss", "password": "wrong"}, REMOTE_ADDR="198.51.100.1")
        self.client.post(url, {"username": "boss", "password": PASSWORD}, REMOTE_ADDR="198.51.100.1")
        self.assertNotIn("_auth_user_id", self.client.session)


@override_settings(RATE_LIMITS=LOW)
class EndpointLimitTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_reference_data()

    def setUp(self):
        cache.clear()

    def test_registration(self):
        url = reverse("accounts:register")
        for i in range(2):
            self.client.post(url, {"display_name": "X", "email": f"x{i}@example.com",
                                   "password1": PASSWORD, "password2": PASSWORD})
            self.client.logout()
        response = self.client.post(url, {"display_name": "X", "email": "x9@example.com",
                                          "password1": PASSWORD, "password2": PASSWORD}, follow=True)
        self.assertContains(response, "Too many sign-ups")
        self.assertFalse(get_user_model().objects.filter(email="x9@example.com").exists())

    def test_password_reset(self):
        url = reverse("accounts:password_reset")
        for _ in range(2):
            self.client.post(url, {"email": "someone@example.com"})
        self.assertContains(self.client.post(url, {"email": "someone@example.com"}, follow=True),
                            "Too many reset requests")

    def test_match_requests_and_reports_per_user(self):
        asha = make_onboarded_user("asha", native="bn", learning="en")
        tom = make_onboarded_user("tom", native="en", learning="bn")
        sam = make_onboarded_user("sam", native="en", learning="bn")
        self.client.force_login(asha)
        self.client.post(reverse("matching:request", kwargs={"user_id": tom.pk}))
        response = self.client.post(reverse("matching:request", kwargs={"user_id": sam.pk}), follow=True)
        self.assertContains(response, "sent a lot of requests")
        report = reverse("partners:report", kwargs={"user_id": sam.pk})
        self.client.post(report, {"reason": "spam"})
        self.assertEqual(self.client.post(report, {"reason": "spam"}).status_code, 429)

    def test_limits_only_count_posts(self):
        for _ in range(5):
            self.assertEqual(self.client.get(reverse("accounts:register")).status_code, 200)


class HeaderTests(TestCase):
    def test_content_security_policy(self):
        response = self.client.get(reverse("core:home"))
        csp = response.headers["Content-Security-Policy"]
        directives = dict(part.strip().split(" ", 1) for part in csp.split(";"))
        self.assertEqual(directives["script-src"], "'self' https://cdn.jsdelivr.net")   # no inline scripts
        self.assertEqual(directives["frame-ancestors"], "'none'")
        self.assertEqual(directives["object-src"], "'none'")
        self.assertIn("wss://testserver", directives["connect-src"])
        self.assertNotIn("'unsafe-inline'", directives["style-src"])
        self.assertIn("camera=()", response.headers["Permissions-Policy"])

    @override_settings(CSP_REPORT_ONLY=True)
    def test_report_only_mode(self):
        response = self.client.get(reverse("core:home"))
        self.assertIn("Content-Security-Policy-Report-Only", response.headers)
        self.assertNotIn("Content-Security-Policy", response.headers)

    def test_admin_is_exempt(self):
        response = self.client.get(reverse("admin:login"))
        self.assertNotIn("Content-Security-Policy", response.headers)


class TemplateSafetyTests(TestCase):
    """Rules the CSP depends on, checked across every template."""

    templates = list(Path(settings.BASE_DIR, "templates").rglob("*.html"))

    def test_no_inline_scripts_or_event_handlers(self):
        for template in self.templates:
            text = template.read_text(encoding="utf-8")
            with self.subTest(template=template.name):
                self.assertFalse(re.search(r"<script(?![^>]*\bsrc=)[^>]*>", text), "inline <script>")
                self.assertFalse(re.search(r"\son[a-z]+=\"", text), "inline event handler")
                self.assertNotIn("|safe", text)

    def test_cdn_files_are_integrity_checked(self):
        base = Path(settings.BASE_DIR, "templates", "base.html").read_text(encoding="utf-8")
        for tag in re.findall(r"<(?:link|script)[^>]*cdn\.jsdelivr\.net[^>]*>", base, re.S):
            with self.subTest(tag=tag[:60]):
                self.assertIn("integrity=\"sha384-", tag)
                self.assertIn("crossorigin=\"anonymous\"", tag)


class SecretKeyTests(TestCase):
    def test_weak_keys_are_rejected(self):
        for key in ("", "short", "django-insecure-" + "x" * 60, "a" * 60):
            with self.subTest(key=key[:20]):
                self.assertTrue(weak_secret_key(key))
        from django.core.management.utils import get_random_secret_key
        self.assertFalse(weak_secret_key(get_random_secret_key()))
