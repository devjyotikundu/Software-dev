from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Kind(models.TextChoices):
        MATCH_REQUEST = "match_request", "Match request"
        MATCH_ACCEPTED = "match_accepted", "Match accepted"
        NEW_MESSAGE = "new_message", "New message"
        SESSION_REMINDER = "session_reminder", "Session reminder"
        FEEDBACK_REQUEST = "feedback_request", "Feedback request"

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    title = models.CharField(max_length=120)
    body = models.CharField(max_length=300, blank=True)
    link = models.CharField(
        max_length=200, blank=True, help_text="Site-relative path, e.g. /matches/12/."
    )
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["recipient", "is_read", "-created_at"], name="notifications_inbox_idx"
            ),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} for {self.recipient}"
