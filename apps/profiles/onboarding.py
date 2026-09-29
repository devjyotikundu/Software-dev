"""The onboarding steps, in order.

A step counts as complete when its data exists in the database, so progress
survives logging out, and nobody can finish onboarding by skipping a step.
"""
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from . import forms
from .models import Profile, UserLanguage


@dataclass(frozen=True)
class Step:
    slug: str
    title: str
    short_title: str
    icon: str  # Bootstrap Icons name
    intro: str
    form_class: type
    is_complete: callable


def _has_languages(profile):
    roles = set(profile.user.languages.values_list("role", flat=True))
    return {UserLanguage.Role.NATIVE, UserLanguage.Role.LEARNING} <= roles


STEPS = (
    Step("languages", "Your languages", "Languages", "translate",
         "We pair you with someone who speaks the language you're learning and is learning yours.",
         forms.LanguagesForm, _has_languages),
    Step("goals", "Your goals", "Goals", "bullseye",
         "Partners with similar goals get more out of each session.",
         forms.GoalsForm, lambda p: p.goals.exists()),
    Step("interests", "Your interests", "Interests", "heart",
         "These give you and your partner something to talk about.",
         forms.InterestsForm, lambda p: p.interests.exists()),
    Step("availability", "When you're free", "Availability", "calendar3",
         "We use this to suggest partners whose free time overlaps with yours.",
         forms.AvailabilityForm, lambda p: p.availability_slots.exists()),
    Step("communication", "How you'd like to practise", "Practice style", "chat-dots",
         "Choose the ways you're comfortable talking with a partner.",
         forms.CommunicationForm, lambda p: p.communication_modes.exists()),
)

STEP_BY_SLUG = {step.slug: step for step in STEPS}


def get_or_create_profile(user):
    """Accounts made outside registration (e.g. createsuperuser) get a profile here."""
    profile, _ = Profile.objects.get_or_create(
        user=user, defaults={"display_name": user.get_full_name() or user.get_username()}
    )
    return profile


def first_incomplete_step(profile):
    for step in STEPS:
        if not step.is_complete(profile):
            return step
    return None


def step_number(step):
    return STEPS.index(step) + 1


def previous_step(step):
    index = STEPS.index(step)
    return STEPS[index - 1] if index > 0 else None


def next_step(step):
    index = STEPS.index(step)
    return STEPS[index + 1] if index + 1 < len(STEPS) else None


@transaction.atomic
def complete_if_finished(profile):
    """Mark onboarding complete once every step has data. Returns True if complete."""
    if first_incomplete_step(profile) is not None:
        return False
    if profile.onboarding_completed_at is None:
        profile.onboarding_completed_at = timezone.now()
        profile.save(update_fields=["onboarding_completed_at", "updated_at"])
    return True
