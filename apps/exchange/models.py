from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class ExchangeRoom(TimeStampedModel):
    """Private room for one confirmed match. Only the match's two users may enter.

    Participants are read from the match, not stored twice.
    """

    match = models.OneToOneField("matching.Match", on_delete=models.CASCADE, related_name="room")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"Room for {self.match}"

    def has_participant(self, user):
        return self.match.includes(user)


class Message(models.Model):
    room = models.ForeignKey(ExchangeRoom, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="exchange_messages"
    )
    body = models.TextField(max_length=2000)
    # Which language the message was written in, when known.
    language = models.ForeignKey(
        "languages.Language", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["room", "created_at"], name="exchange_msg_room_time_idx")]

    def __str__(self):
        return f"{self.sender}: {self.body[:40]}"


class ExchangeSession(models.Model):
    """A timed practice session: minutes in one language, then the other."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    room = models.ForeignKey(ExchangeRoom, on_delete=models.CASCADE, related_name="sessions")
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    first_language = models.ForeignKey(
        "languages.Language", on_delete=models.PROTECT, related_name="+"
    )
    second_language = models.ForeignKey(
        "languages.Language", on_delete=models.PROTECT, related_name="+"
    )
    minutes_per_language = models.PositiveSmallIntegerField(default=10)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(minutes_per_language__gte=1, minutes_per_language__lte=60),
                name="exchange_session_minutes_range",
            ),
            models.CheckConstraint(
                condition=~models.Q(first_language=models.F("second_language")),
                name="exchange_session_languages_differ",
            ),
            models.CheckConstraint(
                condition=models.Q(ended_at__isnull=True)
                | models.Q(ended_at__gte=models.F("started_at")),
                name="exchange_session_ends_after_start",
            ),
            models.UniqueConstraint(
                fields=["room"], condition=models.Q(status="active"),
                name="exchange_session_one_active_per_room",
            ),
        ]
        indexes = [models.Index(fields=["room", "-started_at"], name="exchange_session_hist_idx")]

    def __str__(self):
        return f"Session in {self.room} at {self.started_at:%Y-%m-%d %H:%M}"

    @property
    def duration(self):
        """Elapsed time as a timedelta, or None while still running."""
        if self.ended_at is None:
            return None
        return self.ended_at - self.started_at
