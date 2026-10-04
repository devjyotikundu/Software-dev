from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class SessionFeedback(models.Model):
    """One participant's feedback about their partner after a session."""

    class Difficulty(models.TextChoices):
        TOO_EASY = "too_easy", "Too easy"
        COMFORTABLE = "comfortable", "Comfortable"
        TOO_DIFFICULT = "too_difficult", "Too difficult"

    session = models.ForeignKey(
        "exchange.ExchangeSession", on_delete=models.CASCADE, related_name="feedback"
    )
    # Kept if the reviewer later deletes their account, so the partner's
    # recommendation history is not lost.
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="feedback_given",
    )
    reviewee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="feedback_received"
    )
    usefulness = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    would_practice_again = models.BooleanField()
    difficulty = models.CharField(max_length=15, choices=Difficulty.choices)
    comment = models.TextField(max_length=1000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "session feedback"
        constraints = [
            models.UniqueConstraint(
                fields=["session", "reviewer"], name="feedback_one_per_reviewer_session"
            ),
            models.CheckConstraint(
                condition=models.Q(usefulness__gte=1, usefulness__lte=5),
                name="feedback_usefulness_range",
            ),
            models.CheckConstraint(
                condition=~models.Q(reviewer=models.F("reviewee")),
                name="feedback_not_self",
            ),
        ]
        indexes = [models.Index(fields=["reviewee", "-created_at"], name="feedback_reviewee_idx")]

    def __str__(self):
        return f"Feedback on {self.reviewee} ({self.usefulness}/5)"
