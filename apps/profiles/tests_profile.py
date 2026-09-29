import shutil
import tempfile
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from apps.accounts.models import Report
from apps.core.testing import PASSWORD, make_onboarded_user, make_user, seed_reference_data
from apps.languages.models import Language, ProficiencyLevel

from .models import AvailabilitySlot, Profile, UserLanguage

MEDIA = tempfile.mkdtemp()


def image_upload(fmt="PNG", size=(900, 600), name="photo.png", exif_gps=False):
    buffer = BytesIO()
    image = Image.new("RGB", size, (30, 90, 200))
    kwargs = {}
    if exif_gps:
        exif = image.getexif()
        exif[0x8825] = {2: (22.0, 34.0, 0.0)}  # GPS latitude
        kwargs["exif"] = exif
    image.save(buffer, fmt, **kwargs)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type=f"image/{fmt.lower()}")


class ProfileTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_reference_data()

    def setUp(self):
        self.user = make_onboarded_user("asha")
        self.profile = self.user.profile
        self.client.force_login(self.user)


class ProfilePageTests(ProfileTestCase):
    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("profiles:detail"))
        self.assertIn(reverse("accounts:login"), response.headers["Location"])

    def test_requires_finished_onboarding(self):
        unfinished = make_user("new")
        Profile.objects.create(user=unfinished, display_name="New")
        self.client.force_login(unfinished)
        self.assertRedirects(self.client.get(reverse("profiles:detail")),
                             reverse("onboarding:start"), fetch_redirect_response=False)

    def test_shows_real_profile_data_and_edit_links(self):
        response = self.client.get(reverse("profiles:detail"))
        for text in ("Asha", "Speaking practice", "Music", "Mon", "Asia/Kolkata",
                     "Visible in partner suggestions", "Delete account"):
            self.assertContains(response, text)
        self.assertContains(response, reverse("profiles:edit", kwargs={"section": "goals"}))

    def test_email_is_not_shown_on_profile_page(self):
        response = self.client.get(reverse("profiles:detail"))
        body = response.content.decode()
        # The address appears once, in the account menu, never in the profile itself.
        self.assertEqual(body.count(self.user.email), 1)

    def test_unknown_section_is_404(self):
        response = self.client.get(reverse("profiles:edit", kwargs={"section": "nope"}))
        self.assertEqual(response.status_code, 404)

    def test_header_links_to_profile(self):
        self.assertContains(self.client.get(reverse("core:home")), reverse("profiles:detail"))


class AboutSectionTests(ProfileTestCase):
    url = reverse("profiles:edit", kwargs={"section": "about"})

    def test_update_name_and_bio(self):
        response = self.client.post(self.url, {"display_name": " Asha R ", "bio": "I love films."})
        self.assertRedirects(response, reverse("profiles:detail"))
        self.profile.refresh_from_db()
        self.assertEqual((self.profile.display_name, self.profile.bio), ("Asha R", "I love films."))

    def test_blank_name_rejected(self):
        response = self.client.post(self.url, {"display_name": "  ", "bio": ""})
        self.assertContains(response, "Enter the name partners will see")

    def test_bio_length_limit(self):
        response = self.client.post(self.url, {"display_name": "Asha", "bio": "x" * 501})
        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.bio, "")


@override_settings(MEDIA_ROOT=MEDIA)
class AvatarTests(ProfileTestCase):
    url = reverse("profiles:edit", kwargs={"section": "about"})

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA, ignore_errors=True)
        super().tearDownClass()

    def upload(self, file, **extra):
        return self.client.post(self.url, {"display_name": "Asha", "bio": "", "avatar_upload": file, **extra})

    def test_photo_is_cropped_reencoded_and_renamed(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.upload(image_upload("JPEG", name="my-real-name.jpg", exif_gps=True))
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.avatar.name.startswith("avatars/"))
        self.assertNotIn("my-real-name", self.profile.avatar.name)
        with Image.open(self.profile.avatar.path) as saved:
            self.assertEqual((saved.format, saved.size), ("JPEG", (400, 400)))
            self.assertNotIn(0x8825, saved.getexif())  # location data removed

    def test_replacing_photo_deletes_old_file(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.upload(image_upload())
        self.profile.refresh_from_db()
        old = self.profile.avatar.name
        with self.captureOnCommitCallbacks(execute=True):
            self.upload(image_upload())
        self.profile.refresh_from_db()
        self.assertNotEqual(self.profile.avatar.name, old)
        self.assertFalse(self.profile.avatar.storage.exists(old))

    def test_remove_photo(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.upload(image_upload())
        self.profile.refresh_from_db()
        old = self.profile.avatar.name
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(self.url, {"display_name": "Asha", "bio": "", "remove_avatar": "on"})
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.avatar)
        self.assertFalse(self.profile.avatar.storage.exists(old))

    def test_non_image_rejected(self):
        fake = SimpleUploadedFile("photo.png", b"<?php echo 'x'; ?>", content_type="image/png")
        response = self.upload(fake)
        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.avatar)

    def test_gif_rejected(self):
        response = self.upload(image_upload("GIF", name="a.gif"))
        self.assertContains(response, "JPEG, PNG or WebP")


class LanguageManagementTests(ProfileTestCase):
    url = reverse("profiles:languages")

    def setUp(self):
        super().setUp()
        self.hi = Language.objects.get(code="hi")
        self.a2 = ProficiencyLevel.objects.get(code="A2")

    def test_add_learning_language(self):
        response = self.client.post(self.url, {"language": self.hi.pk, "role": "learning", "level": self.a2.pk})
        self.assertRedirects(response, self.url)
        row = UserLanguage.objects.get(user=self.user, language=self.hi)
        self.assertEqual((row.role, row.self_declared_level), ("learning", self.a2))

    def test_learning_language_needs_level(self):
        response = self.client.post(self.url, {"language": self.hi.pk, "role": "learning"})
        self.assertContains(response, "Choose your level")

    def test_native_language_ignores_level(self):
        self.client.post(self.url, {"language": self.hi.pk, "role": "native", "level": self.a2.pk})
        self.assertIsNone(UserLanguage.objects.get(user=self.user, language=self.hi).self_declared_level)

    def test_cannot_add_language_already_on_profile(self):
        en = Language.objects.get(code="en")
        response = self.client.post(self.url, {"language": en.pk, "role": "native"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.user.languages.count(), 2)

    def test_cannot_remove_last_native_or_learning_language(self):
        for row in self.user.languages.all():
            response = self.client.post(reverse("profiles:language_remove", kwargs={"pk": row.pk}), follow=True)
            self.assertContains(response, "Keep at least one")
        self.assertEqual(self.user.languages.count(), 2)

    def test_remove_extra_language(self):
        extra = UserLanguage.objects.create(user=self.user, language=self.hi, role="learning", self_declared_level=self.a2)
        self.client.post(reverse("profiles:language_remove", kwargs={"pk": extra.pk}))
        self.assertFalse(UserLanguage.objects.filter(pk=extra.pk).exists())

    def test_remove_requires_post(self):
        row = self.user.languages.first()
        response = self.client.get(reverse("profiles:language_remove", kwargs={"pk": row.pk}))
        self.assertEqual(response.status_code, 405)

    def test_cannot_touch_another_users_languages(self):
        other = make_onboarded_user("rahul", native="en", learning="bn")
        other_row = other.languages.get(role="learning")
        self.assertEqual(self.client.post(reverse("profiles:language_remove", kwargs={"pk": other_row.pk})).status_code, 404)
        self.assertEqual(self.client.get(reverse("profiles:language_level", kwargs={"pk": other_row.pk})).status_code, 404)

    def test_change_level(self):
        row = self.user.languages.get(role="learning")
        url = reverse("profiles:language_level", kwargs={"pk": row.pk})
        self.assertRedirects(self.client.post(url, {"self_declared_level": self.a2.pk}), self.url)
        row.refresh_from_db()
        self.assertEqual(row.self_declared_level, self.a2)

    def test_level_page_only_for_learning_languages(self):
        native = self.user.languages.get(role="native")
        url = reverse("profiles:language_level", kwargs={"pk": native.pk})
        self.assertEqual(self.client.get(url).status_code, 404)


class AvailabilityEditTests(ProfileTestCase):
    url = reverse("profiles:availability")

    def formset_data(self, rows, timezone="Asia/Kolkata", existing=()):
        data = {"tz-timezone": timezone, "slots-TOTAL_FORMS": str(len(rows)),
                "slots-INITIAL_FORMS": str(len(existing)),
                "slots-MIN_NUM_FORMS": "0", "slots-MAX_NUM_FORMS": "21"}
        for i, row in enumerate(rows):
            for key, value in row.items():
                data[f"slots-{i}-{key}"] = value
            if i < len(existing):
                data[f"slots-{i}-id"] = str(existing[i].pk)
                data[f"slots-{i}-profile"] = str(self.profile.pk)
        return data

    def test_page_renders_with_existing_slot(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'value="17:00"')

    def test_add_slot_and_change_timezone(self):
        existing = list(self.profile.availability_slots.all())
        data = self.formset_data(
            [{"weekday": "0", "start_time": "17:00", "end_time": "21:00"},
             {"weekday": "5", "start_time": "09:30", "end_time": "11:00"}],
            timezone="Europe/London", existing=existing,
        )
        self.assertRedirects(self.client.post(self.url, data), reverse("profiles:detail"))
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.timezone, "Europe/London")
        self.assertEqual(self.profile.availability_slots.count(), 2)

    def test_overlapping_times_rejected(self):
        existing = list(self.profile.availability_slots.all())
        data = self.formset_data(
            [{"weekday": "0", "start_time": "17:00", "end_time": "21:00"},
             {"weekday": "0", "start_time": "20:00", "end_time": "22:00"}], existing=existing)
        response = self.client.post(self.url, data)
        self.assertContains(response, "Monday has overlapping times")
        self.assertEqual(self.profile.availability_slots.count(), 1)

    def test_end_must_follow_start(self):
        existing = list(self.profile.availability_slots.all())
        data = self.formset_data([{"weekday": "0", "start_time": "21:00", "end_time": "17:00"}], existing=existing)
        self.assertContains(self.client.post(self.url, data), "End time must be after")

    def test_cannot_remove_every_slot(self):
        existing = list(self.profile.availability_slots.all())
        data = self.formset_data(
            [{"weekday": "0", "start_time": "17:00", "end_time": "21:00", "DELETE": "on"}], existing=existing)
        self.assertContains(self.client.post(self.url, data), "at least one time")
        self.assertEqual(self.profile.availability_slots.count(), 1)

    def test_blank_extra_row_is_ignored(self):
        existing = list(self.profile.availability_slots.all())
        data = self.formset_data(
            [{"weekday": "0", "start_time": "17:00", "end_time": "21:00"},
             {"weekday": "", "start_time": "", "end_time": ""}], existing=existing)
        self.assertRedirects(self.client.post(self.url, data), reverse("profiles:detail"))
        self.assertEqual(AvailabilitySlot.objects.filter(profile=self.profile).count(), 1)


class OtherSectionTests(ProfileTestCase):
    def test_edit_goals_reuses_onboarding_form(self):
        from .models import LearningGoal
        grammar = LearningGoal.objects.get(slug="grammar")
        url = reverse("profiles:edit", kwargs={"section": "goals"})
        self.client.post(url, {"goals": [grammar.pk]})
        self.assertEqual(list(self.profile.goals.all()), [grammar])

    def test_privacy_toggle(self):
        url = reverse("profiles:edit", kwargs={"section": "privacy"})
        self.client.post(url, {})  # unchecked switch submits nothing
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.is_discoverable)
        self.assertContains(self.client.get(reverse("profiles:detail")), "Hidden from partner suggestions")
        self.client.post(url, {"is_discoverable": "on"})
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.is_discoverable)


class DeleteAccountTests(ProfileTestCase):
    url = reverse("profiles:delete_account")

    def test_wrong_password_keeps_account(self):
        response = self.client.post(self.url, {"password": "wrong"})
        self.assertContains(response, "That password is incorrect")
        self.assertTrue(type(self.user).objects.filter(pk=self.user.pk).exists())

    def test_deletes_account_logs_out_and_keeps_reports_anonymised(self):
        other = make_user("other")
        report = Report.objects.create(reporter=self.user, reported=other, reason="spam")
        response = self.client.post(self.url, {"password": PASSWORD}, follow=True)
        self.assertContains(response, "have been deleted")
        self.assertFalse(type(self.user).objects.filter(pk=self.user.pk).exists())
        self.assertFalse(Profile.objects.filter(pk=self.profile.pk).exists())
        self.assertFalse(UserLanguage.objects.filter(user_id=self.user.pk).exists())
        self.assertNotIn("_auth_user_id", self.client.session)
        report.refresh_from_db()
        self.assertIsNone(report.reporter)
