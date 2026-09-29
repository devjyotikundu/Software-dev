import uuid
import zoneinfo
from math import floor
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import ReferenceItem, TimeStampedModel


def validate_timezone(value):
    if value not in zoneinfo.available_timezones():
        raise ValidationError(f"{value} is not a recognised time zone.")


def avatar_upload_to(instance, filename):
    """Random file names so uploads never reveal usernames or original names."""
    extension = Path(filename).suffix.lower()[:10]
    return f"avatars/{uuid.uuid4().hex}{extension}"


class LearningGoal(ReferenceItem):
    """Why someone is learning: speaking, grammar, travel, interview, ..."""


class Interest(ReferenceItem):
    """Topics to talk about: music, technology, food, ..."""


class CommunicationMode(ReferenceItem):
    """How someone is willing to practise: text, voice or video."""


class Profile(TimeStampedModel):
    """Public-facing details and preferences. One per user.

    Created during onboarding (Phase 3), so a user may briefly have none.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    display_name = models.CharField(max_length=50)
    bio = models.TextField(max_length=500, blank=True)
    avatar = models.ImageField(upload_to=avatar_upload_to, blank=True)
    timezone = models.CharField(
        max_length=64, default="UTC", validators=[validate_timezone],
        help_text="Availability times are stored in this time zone.",
    )

    goals = models.ManyToManyField(LearningGoal, blank=True, related_name="profiles")
    interests = models.ManyToManyField(Interest, blank=True, related_name="profiles")
    communication_modes = models.ManyToManyField(
        CommunicationMode, blank=True, related_name="profiles"
    )

    # Privacy: hidden profiles never appear in partner discovery.
    is_discoverable = models.BooleanField(default=True)
    onboarding_completed_at = models.DateTimeField(null=True, blank=True)
    last_active_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            # Candidate filtering starts from discoverable, recently active users.
            models.Index(
                fields=["is_discoverable", "last_active_at"],
                name="profiles_discoverable_idx",
            ),
        ]

    def __str__(self):
        return self.display_name

    @property
    def is_onboarded(self):
        return self.onboarding_completed_at is not None


class UserLanguage(TimeStampedModel):
    """A language a user speaks natively or is learning.

    Matching is reciprocal: A's learning language must be B's native language
    and vice versa. The (language, role) index makes that lookup cheap.
    """

    class Role(models.TextChoices):
        NATIVE = "native", "Native"
        LEARNING = "learning", "Learning"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="languages"
    )
    language = models.ForeignKey(
        "languages.Language", on_delete=models.PROTECT, related_name="user_languages"
    )
    role = models.CharField(max_length=10, choices=Role.choices)
    self_declared_level = models.ForeignKey(
        "languages.ProficiencyLevel", on_delete=models.PROTECT,
        null=True, blank=True, related_name="+",
    )
    # Written by the proficiency engine (Phase 8), never by the user.
    assessed_level = models.ForeignKey(
        "languages.ProficiencyLevel", on_delete=models.PROTECT,
        null=True, blank=True, related_name="+",
    )
    assessed_at = models.DateTimeField(null=True, blank=True)
    # 0–1: how much the assessed level is trusted over the self-declared one.
    assessment_confidence = models.FloatField(default=0)

    class Meta:
        constraints = [
            # A language is either native or being learned, never both.
            models.UniqueConstraint(
                fields=["user", "language"], name="profiles_userlanguage_unique_user_language"
            ),
            # Levels only make sense for a language being learned.
            models.CheckConstraint(
                condition=models.Q(role="learning")
                | models.Q(self_declared_level__isnull=True, assessed_level__isnull=True),
                name="profiles_userlanguage_levels_only_when_learning",
            ),
            models.CheckConstraint(
                condition=models.Q(assessment_confidence__gte=0, assessment_confidence__lte=1),
                name="profiles_userlanguage_confidence_range",
            ),
        ]
        indexes = [
            models.Index(fields=["language", "role"], name="profiles_ul_language_role_idx"),
        ]

    def __str__(self):
        return f"{self.user} – {self.language} ({self.get_role_display()})"

    @property
    def current_rank(self):
        """current_level's rank (1–6) without a database query, or None."""
        declared, assessed = self.self_declared_level, self.assessed_level
        if assessed is None:
            return declared.rank if declared else None
        confidence = self.assessment_confidence
        if declared is None or confidence >= 1:
            return assessed.rank
        return floor((1 - confidence) * declared.rank + confidence * assessed.rank + 0.5)

    @property
    def current_level(self):
        """The level shown to the user and used for matching.

        A blend of the self-declared and assessed levels, weighted by
        ``assessment_confidence``: with little practice data the learner's
        own estimate dominates; as evidence grows, the assessed level takes
        over (at confidence 1 it is used alone).
        """
        declared, assessed = self.self_declared_level, self.assessed_level
        rank = self.current_rank
        if rank is None:
            return None
        if declared is not None and rank == declared.rank:
            return declared
        if assessed is not None and rank == assessed.rank:
            return assessed
        from apps.languages.models import ProficiencyLevel
        return ProficiencyLevel.objects.get(rank=rank)

    @property
    def level_source(self):
        """Where current_level comes from: "self-declared", "practice" or "both"."""
        if self.assessed_level is None or self.assessment_confidence <= 0:
            return "self-declared"
        if self.self_declared_level is None or self.assessment_confidence >= 1:
            return "practice"
        return "both"


class AvailabilitySlot(models.Model):
    """A weekly time range, in the profile's time zone.

    Ranges crossing midnight are stored as two slots (e.g. 22:00–24:00 is
    saved as 22:00–23:59 plus the next day's slot).
    """

    class Weekday(models.IntegerChoices):
        MONDAY = 0, "Monday"
        TUESDAY = 1, "Tuesday"
        WEDNESDAY = 2, "Wednesday"
        THURSDAY = 3, "Thursday"
        FRIDAY = 4, "Friday"
        SATURDAY = 5, "Saturday"
        SUNDAY = 6, "Sunday"

    profile = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name="availability_slots"
    )
    weekday = models.PositiveSmallIntegerField(choices=Weekday.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        ordering = ["weekday", "start_time"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="profiles_slot_end_after_start",
            ),
            models.CheckConstraint(
                condition=models.Q(weekday__gte=0, weekday__lte=6),
                name="profiles_slot_valid_weekday",
            ),
            models.UniqueConstraint(
                fields=["profile", "weekday", "start_time"],
                name="profiles_slot_unique_start",
            ),
        ]

    def __str__(self):
        return (
            f"{self.get_weekday_display()} "
            f"{self.start_time:%H:%M}–{self.end_time:%H:%M}"
        )
