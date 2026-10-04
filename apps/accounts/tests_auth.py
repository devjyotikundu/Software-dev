from django.contrib.auth import get_user_model
from django.core import mail
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from apps.core.testing import make_user
from apps.profiles.models import Profile

User = get_user_model()
PASSWORD = "a-strong-pass-123"


def registration_data(**overrides):
    data = {"display_name": "Asha", "email": "Asha@Example.com",
            "password1": PASSWORD, "password2": PASSWORD}
    data.update(overrides)
    return data


class RegistrationTests(TestCase):
    url = reverse("accounts:register")

    def test_page_renders(self):
        self.assertContains(self.client.get(self.url), "Create your account")

    def test_creates_user_and_profile_then_starts_onboarding(self):
        response = self.client.post(self.url, registration_data())
        self.assertRedirects(response, reverse("onboarding:start"), fetch_redirect_response=False)
        user = User.objects.get()
        self.assertEqual(user.email, "asha@example.com")  # normalised
        self.assertTrue(user.check_password(PASSWORD))
        self.assertEqual(Profile.objects.get(user=user).display_name, "Asha")
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_email_must_be_unique_ignoring_case(self):
        self.client.post(self.url, registration_data())
        self.client.logout()
        response = self.client.post(self.url, registration_data(email="ASHA@example.com"))
        self.assertContains(response, "already exists")
        self.assertEqual(User.objects.count(), 1)

    def test_passwords_must_match(self):
        response = self.client.post(self.url, registration_data(password2="different-pass-456"))
        self.assertContains(response, "don&#x27;t match")
        self.assertFalse(User.objects.exists())

    def test_weak_password_rejected(self):
        response = self.client.post(self.url, registration_data(password1="password", password2="password"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.exists())

    def test_blank_name_rejected(self):
        response = self.client.post(self.url, registration_data(display_name="   "))
        self.assertContains(response, "Enter the name partners will see")
        self.assertFalse(User.objects.exists())

    def test_signed_in_user_is_sent_home(self):
        self.client.force_login(make_user("x"))
        self.assertRedirects(self.client.get(self.url), reverse("core:home"),
                             fetch_redirect_response=False)

    def test_database_rejects_duplicate_email_in_any_case(self):
        make_user("first")  # first@example.com
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(username="other", email="FIRST@example.com", password="x")

    def test_blank_emails_allowed_more_than_once(self):
        User.objects.create_user(username="admin1", password="x")
        User.objects.create_user(username="admin2", password="x")


class LoginLogoutTests(TestCase):
    def setUp(self):
        self.user = make_user("rahul")  # rahul@example.com

    def test_login_with_email_any_case(self):
        response = self.client.post(
            reverse("accounts:login"), {"username": "RAHUL@example.com", "password": PASSWORD}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_username_login_still_works_for_admin(self):
        self.assertTrue(self.client.login(username="rahul", password=PASSWORD))

    def test_wrong_password_gives_generic_message(self):
        response = self.client.post(
            reverse("accounts:login"), {"username": "rahul@example.com", "password": "wrong"}
        )
        self.assertContains(response, "Email or password is incorrect")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_unknown_email_gives_same_message(self):
        response = self.client.post(
            reverse("accounts:login"), {"username": "nobody@example.com", "password": "wrong"}
        )
        self.assertContains(response, "Email or password is incorrect")

    def test_inactive_user_cannot_log_in(self):
        self.user.is_active = False
        self.user.save()
        self.assertFalse(self.client.login(username="rahul@example.com", password=PASSWORD))

    def test_login_ignores_external_next(self):
        response = self.client.post(
            reverse("accounts:login") + "?next=https://evil.example/",
            {"username": "rahul@example.com", "password": PASSWORD,
             "next": "https://evil.example/"},
        )
        self.assertNotIn("evil.example", response.headers["Location"])

    def test_logout_requires_post(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        self.client.post(reverse("accounts:logout"))
        self.assertNotIn("_auth_user_id", self.client.session)


class PasswordTests(TestCase):
    def setUp(self):
        self.user = make_user("meera")

    def test_change_password(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("accounts:password_change"), {
            "old_password": PASSWORD,
            "new_password1": "another-strong-pass-789",
            "new_password2": "another-strong-pass-789",
        })
        self.assertRedirects(response, reverse("accounts:password_change_done"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("another-strong-pass-789"))

    def test_change_password_requires_login(self):
        response = self.client.get(reverse("accounts:password_change"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.headers["Location"])

    def test_reset_sends_email_for_known_address(self):
        response = self.client.post(reverse("accounts:password_reset"),
                                    {"email": "MEERA@example.com"})
        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/accounts/password/reset/", mail.outbox[0].body)

    def test_reset_does_not_reveal_unknown_address(self):
        response = self.client.post(reverse("accounts:password_reset"),
                                    {"email": "unknown@example.com"})
        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_reset_link_sets_new_password(self):
        self.client.post(reverse("accounts:password_reset"), {"email": "meera@example.com"})
        link = next(line for line in mail.outbox[0].body.splitlines() if "/reset/" in line)
        path = link.split("testserver", 1)[1].strip()
        response = self.client.get(path, follow=True)  # Django swaps the token for a session
        form_url = response.redirect_chain[-1][0]
        self.client.post(form_url, {"new_password1": "brand-new-pass-321",
                                    "new_password2": "brand-new-pass-321"})
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("brand-new-pass-321"))
