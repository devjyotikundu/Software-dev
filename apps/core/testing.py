"""Small helpers shared by test modules. Not used by application code."""
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command

PASSWORD = "a-strong-pass-123"


def seed_reference_data(*, questions=False):
    """Seed lookup data. The 300-question bank is opt-in to keep tests fast."""
    args = [] if questions else ["--skip-questions"]
    call_command("seed_data", *args, stdout=StringIO())


def make_user(username, **extra):
    return get_user_model().objects.create_user(
        username=username, email=f"{username}@example.com", password=PASSWORD, **extra
    )


def make_onboarded_user(username, native="bn", learning="en", level="B1", **_ignored):
    """A user who has finished onboarding, built directly in the database."""
    from datetime import time

    from django.utils import timezone

    from apps.languages.models import Language, ProficiencyLevel
    from apps.profiles.models import (
        AvailabilitySlot, CommunicationMode, Interest, LearningGoal, Profile, UserLanguage,
    )

    user = make_user(username)
    profile = Profile.objects.create(
        user=user, display_name=username.title(), timezone="Asia/Kolkata",
        onboarding_completed_at=timezone.now(), last_active_at=timezone.now(),
    )
    UserLanguage.objects.create(user=user, language=Language.objects.get(code=native), role="native")
    UserLanguage.objects.create(
        user=user, language=Language.objects.get(code=learning), role="learning",
        self_declared_level=ProficiencyLevel.objects.get(code=level),
    )
    profile.goals.set(LearningGoal.objects.filter(slug="speaking"))
    profile.interests.set(Interest.objects.filter(slug__in=["music", "movies"]))
    profile.communication_modes.set(CommunicationMode.objects.filter(slug="text"))
    AvailabilitySlot.objects.create(profile=profile, weekday=0, start_time=time(17), end_time=time(21))
    return user
