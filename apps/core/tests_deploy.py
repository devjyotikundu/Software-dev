"""Deployment safety: the static manifest check and idempotent admin seeding."""
import os
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings

from .checks import static_manifest_exists

MANIFEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}


class StaticManifestCheckTests(TestCase):
    def test_missing_manifest_is_an_error(self):
        with tempfile.TemporaryDirectory() as root, \
                override_settings(STORAGES=MANIFEST_STORAGES, STATIC_ROOT=root):
            errors = static_manifest_exists()
        self.assertEqual([e.id for e in errors], ["core.E001"])
        self.assertIn("collectstatic", errors[0].hint)

    def test_present_manifest_passes(self):
        with tempfile.TemporaryDirectory() as root, \
                override_settings(STORAGES=MANIFEST_STORAGES, STATIC_ROOT=root):
            Path(root, "staticfiles.json").write_text("{}")
            self.assertEqual(static_manifest_exists(), [])

    def test_not_applicable_without_manifest_storage(self):
        self.assertEqual(static_manifest_exists(), [])  # tests use plain storage

    def test_every_static_reference_exists_in_the_project(self):
        import re
        from django.conf import settings
        from django.contrib.staticfiles import finders
        missing = []
        for template in Path(settings.BASE_DIR, "templates").rglob("*.html"):
            for ref in re.findall(r"{% static '([^']+)' %}", template.read_text(encoding="utf-8")):
                if finders.find(ref) is None:
                    missing.append((template.name, ref))
        self.assertEqual(missing, [])


ADMIN_ENV = {"DJANGO_SUPERUSER_USERNAME": "admin", "DJANGO_SUPERUSER_EMAIL": "Admin@Example.com",
             "DJANGO_SUPERUSER_PASSWORD": "first-strong-pass-123"}


class AdminSeedTests(TestCase):
    def seed(self, *args, env=ADMIN_ENV):
        out = StringIO()
        with mock.patch.dict(os.environ, env, clear=False):
            call_command("seed_data", "--skip-questions", *args, stdout=out)
        return out.getvalue()

    def test_creates_admin_once_and_reruns_safely(self):
        self.assertIn("Admin account: 1 created", self.seed())
        output = self.seed()  # second deploy: no "username is already taken"
        self.assertIn("Admin account: 0 created, 0 updated, 1 unchanged", output)
        User = get_user_model()
        self.assertEqual(User.objects.filter(username="admin").count(), 1)
        admin = User.objects.get(username="admin")
        self.assertTrue(admin.is_superuser and admin.is_staff)
        self.assertEqual(admin.email, "admin@example.com")

    def test_existing_user_is_promoted_not_duplicated(self):
        get_user_model().objects.create_user(username="admin", password="old-pass-123456")
        self.assertIn("1 updated", self.seed())
        admin = get_user_model().objects.get(username="admin")
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.check_password("old-pass-123456"))  # password kept without --update

    def test_update_flag_resets_password(self):
        self.seed()
        self.seed("--update", env={**ADMIN_ENV, "DJANGO_SUPERUSER_PASSWORD": "second-strong-pass-456"})
        self.assertTrue(get_user_model().objects.get(username="admin").check_password("second-strong-pass-456"))

    def test_email_already_used_by_someone_else(self):
        get_user_model().objects.create_user(username="someone", email="admin@example.com", password="x")
        self.seed()
        self.assertEqual(get_user_model().objects.get(username="admin").email, "")

    def test_nothing_happens_without_variables(self):
        output = self.seed(env={"DJANGO_SUPERUSER_USERNAME": "", "DJANGO_SUPERUSER_PASSWORD": ""})
        self.assertIn("not configured", output)
        self.assertFalse(get_user_model().objects.filter(is_superuser=True).exists())
