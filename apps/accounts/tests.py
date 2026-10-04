from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.core.testing import make_user

from .models import BlockedUser, Report


class UserModelTests(TestCase):
    def test_custom_user_model_is_active(self):
        self.assertEqual(settings.AUTH_USER_MODEL, "accounts.User")
        self.assertEqual(get_user_model()._meta.label, "accounts.User")

    def test_password_is_hashed(self):
        user = get_user_model().objects.create_user(
            username="ayush", email="ayush@example.com", password="a-strong-pass-123"
        )
        self.assertNotEqual(user.password, "a-strong-pass-123")
        self.assertTrue(user.check_password("a-strong-pass-123"))


class SafetyModelTests(TestCase):
    def setUp(self):
        self.a = make_user("a")
        self.b = make_user("b")

    def test_cannot_block_self(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            BlockedUser.objects.create(blocker=self.a, blocked=self.a)

    def test_block_is_unique(self):
        BlockedUser.objects.create(blocker=self.a, blocked=self.b)
        with self.assertRaises(IntegrityError), transaction.atomic():
            BlockedUser.objects.create(blocker=self.a, blocked=self.b)

    def test_report_survives_account_deletion(self):
        report = Report.objects.create(reporter=self.a, reported=self.b, reason="spam")
        self.b.delete()
        report.refresh_from_db()
        self.assertIsNone(report.reported)
        self.assertEqual(report.status, "open")
