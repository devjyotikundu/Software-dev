from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import TimeStampedModel


class _PairQuerySet(models.QuerySet):
    """Lookups for "either side of a pair" without SQL OR.

    `a = X OR b = X` on these tables (which carry partial unique indexes)
    makes some SQLite releases fail with "internal query planner error". Two
    simple indexed lookups are just as fast and work on every database.
    """

    side_a = side_b = None

    def involving(self, user):
        ids = list(self.filter(**{self.side_a: user}).values_list("pk", flat=True))
        ids += list(self.filter(**{self.side_b: user}).values_list("pk", flat=True))
        return self.filter(pk__in=ids)

    def between(self, first, second):
        ids = list(self.filter(**{self.side_a: first, self.side_b: second}).values_list("pk", flat=True))
        ids += list(self.filter(**{self.side_a: second, self.side_b: first}).values_list("pk", flat=True))
        return self.filter(pk__in=ids)


class MatchRequestQuerySet(_PairQuerySet):
    side_a, side_b = "sender", "receiver"


class MatchQuerySet(_PairQuerySet):
    side_a, side_b = "user_a", "user_b"


class MatchSuggestion(models.Model):
    """A precomputed compatibility score for one candidate.

    Scores are calculated in the background (Phase 9) and read by discovery
    pages, so matching maths never runs on every page load. ``breakdown``
    holds the real per-factor values behind "Why this match?".
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="match_suggestions"
    )
    candidate = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    score = models.DecimalField(
        max_digits=5, decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    breakdown = models.JSONField(default=dict)
    computed_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "candidate"], name="matching_suggestion_unique"),
            models.CheckConstraint(
                condition=~models.Q(user=models.F("candidate")),
                name="matching_suggestion_not_self",
            ),
            models.CheckConstraint(
                condition=models.Q(score__gte=0, score__lte=100),
                name="matching_suggestion_score_range",
            ),
        ]
        indexes = [models.Index(fields=["user", "-score"], name="matching_suggestion_rank_idx")]

    def __str__(self):
        return f"{self.user} → {self.candidate}: {self.score}"


class MatchRequest(TimeStampedModel):
    """Suggested → request sent → accepted/declined/cancelled."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        CANCELLED = "cancelled", "Cancelled"

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_match_requests"
    )
    receiver = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="received_match_requests"
    )
    # The exchange being proposed: what each side wants to learn.
    sender_learning_language = models.ForeignKey(
        "languages.Language", on_delete=models.PROTECT, related_name="+"
    )
    receiver_learning_language = models.ForeignKey(
        "languages.Language", on_delete=models.PROTECT, related_name="+"
    )
    message = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    score_at_request = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    objects = MatchRequestQuerySet.as_manager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(sender=models.F("receiver")),
                name="matching_request_not_self",
            ),
            models.CheckConstraint(
                condition=~models.Q(
                    sender_learning_language=models.F("receiver_learning_language")
                ),
                name="matching_request_languages_differ",
            ),
            # One open request from a sender to a receiver at a time.
            models.UniqueConstraint(
                fields=["sender", "receiver"],
                condition=models.Q(status="pending"),
                name="matching_request_one_pending",
            ),
        ]
        indexes = [
            models.Index(fields=["receiver", "status", "-created_at"], name="matching_req_inbox_idx"),
            models.Index(fields=["sender", "status", "-created_at"], name="matching_req_outbox_idx"),
        ]

    def __str__(self):
        return f"{self.sender} → {self.receiver} ({self.get_status_display()})"


class Match(TimeStampedModel):
    """A confirmed exchange partnership between two users.

    The pair is stored in a fixed order (user_a.id < user_b.id) so the same
    two people can never have two active matches.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ENDED = "ended", "Ended"

    user_a = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="matches_as_a"
    )
    user_b = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="matches_as_b"
    )
    user_a_learning_language = models.ForeignKey(
        "languages.Language", on_delete=models.PROTECT, related_name="+"
    )
    user_b_learning_language = models.ForeignKey(
        "languages.Language", on_delete=models.PROTECT, related_name="+"
    )
    request = models.OneToOneField(
        MatchRequest, on_delete=models.SET_NULL, null=True, blank=True, related_name="match"
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    ended_at = models.DateTimeField(null=True, blank=True)

    objects = MatchQuerySet.as_manager()

    class Meta:
        verbose_name_plural = "matches"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(user_a__lt=models.F("user_b")),
                name="matching_match_ordered_pair",
            ),
            models.CheckConstraint(
                condition=~models.Q(
                    user_a_learning_language=models.F("user_b_learning_language")
                ),
                name="matching_match_languages_differ",
            ),
            models.UniqueConstraint(
                fields=["user_a", "user_b"],
                condition=models.Q(status="active"),
                name="matching_match_one_active",
            ),
        ]

    def __str__(self):
        return f"{self.user_a} ↔ {self.user_b}"

    @staticmethod
    def ordered_pair(first, second):
        """Return the two users in storage order (lower id first)."""
        return (first, second) if first.pk < second.pk else (second, first)

    def includes(self, user):
        return user.pk in (self.user_a_id, self.user_b_id)
