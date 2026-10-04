from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower


class User(AbstractUser):
    """Project user model (table: accounts_user).

    Defined now, before the first migration, because Django cannot easily
    switch AUTH_USER_MODEL once tables exist. Profile data lives in
    profiles.Profile.

    People sign in with their email. ``username`` is kept as an internal,
    generated identifier (and for admin sign-in); users never see it.
    """

    class Meta:
        constraints = [
            # Case-insensitive unique email. Blank emails (possible for
            # accounts made with createsuperuser) are allowed more than once.
            models.UniqueConstraint(
                Lower("email"),
                condition=~models.Q(email=""),
                name="accounts_user_email_ci_unique",
            ),
        ]



class BlockedUser(models.Model):
    """Blocks are one-directional but hide both users from each other everywhere."""

    blocker = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="blocks_made"
    )
    blocked = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="blocks_received"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["blocker", "blocked"], name="accounts_block_unique"),
            models.CheckConstraint(
                condition=~models.Q(blocker=models.F("blocked")), name="accounts_block_not_self"
            ),
        ]

    def __str__(self):
        return f"{self.blocker} blocked {self.blocked}"


class Report(models.Model):
    """A user report for admins to review. Kept even if either account is deleted."""

    class Reason(models.TextChoices):
        HARASSMENT = "harassment", "Harassment or bullying"
        INAPPROPRIATE = "inappropriate", "Inappropriate content"
        SPAM = "spam", "Spam or scam"
        FAKE_PROFILE = "fake_profile", "Fake profile"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        REVIEWING = "reviewing", "Under review"
        RESOLVED = "resolved", "Resolved"
        DISMISSED = "dismissed", "Dismissed"

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="reports_made",
    )
    reported = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="reports_received",
    )
    reason = models.CharField(max_length=20, choices=Reason.choices)
    details = models.TextField(max_length=2000, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(reporter=models.F("reported")),
                name="accounts_report_not_self",
            ),
        ]
        indexes = [models.Index(fields=["status", "-created_at"], name="accounts_report_queue_idx")]

    def __str__(self):
        return f"Report #{self.pk}: {self.get_reason_display()}"
