from datetime import time

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.core.testing import make_user, seed_reference_data
from apps.languages.models import Language, ProficiencyLevel

from .models import AvailabilitySlot, Interest, Profile, UserLanguage, validate_timezone


class ProfileModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_reference_data()
        cls.user = make_user("asha")
        cls.profile = Profile.objects.create(user=cls.user, display_name="Asha")
        cls.en = Language.objects.get(code="en")
        cls.bn = Language.objects.get(code="bn")
        cls.b1 = ProficiencyLevel.objects.get(code="B1")
        cls.b2 = ProficiencyLevel.objects.get(code="B2")

    def test_one_profile_per_user(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Profile.objects.create(user=self.user, display_name="Again")

    def test_interests_many_to_many(self):
        self.profile.interests.set(Interest.objects.filter(slug__in=["music", "movies"]))
        self.assertEqual(self.profile.interests.count(), 2)

    def test_language_cannot_be_native_and_learning(self):
        UserLanguage.objects.create(user=self.user, language=self.bn, role="native")
        with self.assertRaises(IntegrityError), transaction.atomic():
            UserLanguage.objects.create(
                user=self.user, language=self.bn, role="learning", self_declared_level=self.b1
            )

    def test_native_language_has_no_level(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            UserLanguage.objects.create(
                user=self.user, language=self.en, role="native", self_declared_level=self.b1
            )

    def test_current_level_follows_assessment_confidence(self):
        learning = UserLanguage.objects.create(
            user=self.user, language=self.en, role="learning", self_declared_level=self.b1
        )
        self.assertEqual(learning.current_level, self.b1)
        learning.assessed_level = self.b2
        self.assertEqual(learning.current_level, self.b1)  # no confidence yet
        learning.assessment_confidence = 1
        self.assertEqual(learning.current_level, self.b2)

    def test_confidence_must_be_between_0_and_1(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            UserLanguage.objects.create(user=self.user, language=self.en, role="learning",
                                        self_declared_level=self.b1, assessment_confidence=1.5)

    def test_slot_must_end_after_start(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            AvailabilitySlot.objects.create(
                profile=self.profile, weekday=0, start_time=time(18), end_time=time(17)
            )

    def test_valid_slot(self):
        slot = AvailabilitySlot.objects.create(
            profile=self.profile, weekday=2, start_time=time(18), end_time=time(19, 30)
        )
        self.assertEqual(str(slot), "Wednesday 18:00–19:30")

    def test_timezone_validation(self):
        validate_timezone("Asia/Kolkata")
        with self.assertRaises(ValidationError):
            validate_timezone("Mars/Olympus")


class AvailabilitySummaryTests(TestCase):
    def test_groups_days_with_identical_times(self):
        from .presenters import summarize_availability

        user = make_user("sum")
        profile = Profile.objects.create(user=user, display_name="S")
        for day in (0, 2):
            AvailabilitySlot.objects.create(profile=profile, weekday=day,
                                            start_time=time(17), end_time=time(21))
        AvailabilitySlot.objects.create(profile=profile, weekday=5,
                                        start_time=time(6), end_time=time(12))
        self.assertEqual(
            summarize_availability(profile.availability_slots.all()),
            [("Mon, Wed", "17:00–21:00"), ("Sat", "06:00–12:00")],
        )
