import hashlib

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import ReferenceItem, TimeStampedModel


class AnswerOption(models.TextChoices):
    A = "A", "A"
    B = "B", "B"
    C = "C", "C"
    D = "D", "D"


class DifficultyLevel(models.Model):
    """Game difficulty, Level 1 (very easy) to Level 10 (extremely difficult).

    Codes A1–A10 are internal identifiers from the project brief. They are
    NOT CEFR levels and are shown to users as "Level N". This table is the
    single place XP rewards are configured.
    """

    code = models.CharField(max_length=3, unique=True)
    rank = models.PositiveSmallIntegerField(unique=True)
    label = models.CharField(max_length=20)
    xp_reward = models.PositiveSmallIntegerField(help_text="XP for a correct answer.")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["rank"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(rank__gte=1), name="practice_difficulty_rank_gte_1"
            ),
        ]

    def __str__(self):
        return self.label


class QuestionCategory(ReferenceItem):
    """Vocabulary, grammar, sentence completion, context, reading, expressions."""

    class Meta(ReferenceItem.Meta):
        verbose_name_plural = "question categories"


class PracticeQuestionQuerySet(models.QuerySet):
    def servable(self):
        """Questions that may be shown to learners.

        A question must be active and its difficulty level active. Questions
        from the curated bank are served; AI-generated ones only after they
        have been reviewed (Phase 14). ``is_verified`` on bank questions
        records review by a fluent speaker, tracked in the admin.
        """
        return self.filter(is_active=True, difficulty__is_active=True).filter(
            models.Q(source=PracticeQuestion.Source.VERIFIED) | models.Q(is_verified=True)
        )


class PracticeQuestion(TimeStampedModel):
    class Source(models.TextChoices):
        VERIFIED = "verified", "Verified question bank"
        AI = "ai", "AI-generated"

    language = models.ForeignKey(
        "languages.Language", on_delete=models.PROTECT, related_name="questions"
    )
    difficulty = models.ForeignKey(
        DifficultyLevel, on_delete=models.PROTECT, related_name="questions"
    )
    category = models.ForeignKey(
        QuestionCategory, on_delete=models.PROTECT, related_name="questions"
    )
    question_text = models.TextField()
    option_a = models.CharField(max_length=255)
    option_b = models.CharField(max_length=255)
    option_c = models.CharField(max_length=255)
    option_d = models.CharField(max_length=255)
    correct_option = models.CharField(max_length=1, choices=AnswerOption.choices)
    english_meaning = models.TextField()
    english_explanation = models.TextField()

    source = models.CharField(max_length=10, choices=Source.choices, default=Source.VERIFIED)
    # See PracticeQuestionQuerySet.servable() for what learners can see.
    # Admins disable a question instead of deleting it, so past answers keep
    # their history.
    is_active = models.BooleanField(default=True)
    is_verified = models.BooleanField(
        default=False, help_text="Reviewed by a fluent speaker."
    )
    # Normalised text + options, used to reject duplicates (including AI repeats).
    content_hash = models.CharField(max_length=64, editable=False, blank=True)

    objects = PracticeQuestionQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["language", "content_hash"], name="practice_question_unique_content"
            ),
            models.CheckConstraint(
                condition=models.Q(correct_option__in=AnswerOption.values),
                name="practice_question_valid_correct_option",
            ),
        ]
        indexes = [
            models.Index(
                fields=["language", "difficulty", "is_active", "is_verified"],
                name="practice_q_selection_idx",
            ),
            models.Index(fields=["language", "category"], name="practice_q_category_idx"),
        ]

    def __str__(self):
        return f"[{self.language.code} {self.difficulty.code}] {self.question_text[:60]}"

    @property
    def options(self):
        return {
            "A": self.option_a, "B": self.option_b,
            "C": self.option_c, "D": self.option_d,
        }

    @staticmethod
    def compute_content_hash(question_text, options):
        def norm(text):
            return " ".join(str(text).split()).casefold()

        parts = [norm(question_text)] + sorted(norm(o) for o in options)
        return hashlib.sha256("\u241f".join(parts).encode("utf-8")).hexdigest()

    def clean(self):
        normalised = [" ".join(o.split()).casefold() for o in self.options.values()]
        if len(set(normalised)) != 4:
            raise ValidationError("All four options must be different.")

    def save(self, *args, **kwargs):
        self.content_hash = self.compute_content_hash(
            self.question_text, self.options.values()
        )
        super().save(*args, **kwargs)


class PracticeSession(TimeStampedModel):
    """One practice run of (normally) 10 questions. created_at is its start time."""

    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        ABANDONED = "abandoned", "Abandoned"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="practice_sessions"
    )
    language = models.ForeignKey(
        "languages.Language", on_delete=models.PROTECT, related_name="practice_sessions"
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.IN_PROGRESS)
    question_count = models.PositiveSmallIntegerField(default=10)
    correct_count = models.PositiveSmallIntegerField(default=0)
    xp_earned = models.PositiveIntegerField(default=0)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(question_count__gte=1),
                name="practice_session_has_questions",
            ),
            models.CheckConstraint(
                condition=models.Q(correct_count__lte=models.F("question_count")),
                name="practice_session_correct_lte_total",
            ),
            # At most one unfinished session per user and language.
            models.UniqueConstraint(
                fields=["user", "language"],
                condition=models.Q(status="in_progress"),
                name="practice_session_one_in_progress",
            ),
        ]
        indexes = [
            models.Index(
                fields=["user", "language", "-created_at"], name="practice_session_history_idx"
            ),
        ]

    def __str__(self):
        return f"{self.user} – {self.language} – {self.created_at:%Y-%m-%d %H:%M}"


class PracticeAnswer(models.Model):
    """One question within a session. Unanswered until answered_at is set."""

    session = models.ForeignKey(PracticeSession, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(
        PracticeQuestion, on_delete=models.PROTECT, related_name="answers"
    )
    # Snapshot: history stays accurate even if the question is re-graded later.
    difficulty = models.ForeignKey(DifficultyLevel, on_delete=models.PROTECT, related_name="+")
    position = models.PositiveSmallIntegerField()
    selected_option = models.CharField(max_length=1, choices=AnswerOption.choices, blank=True)
    is_correct = models.BooleanField(null=True)
    xp_awarded = models.PositiveSmallIntegerField(default=0)
    answered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["session", "position"]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "position"], name="practice_answer_unique_position"
            ),
            models.UniqueConstraint(
                fields=["session", "question"], name="practice_answer_unique_question"
            ),
            models.CheckConstraint(
                condition=models.Q(position__gte=1), name="practice_answer_position_gte_1"
            ),
            # Either fully unanswered, or fully answered — never half-recorded.
            models.CheckConstraint(
                condition=(
                    models.Q(
                        answered_at__isnull=True, selected_option="",
                        is_correct__isnull=True, xp_awarded=0,
                    )
                    | (
                        models.Q(answered_at__isnull=False, is_correct__isnull=False)
                        & ~models.Q(selected_option="")
                    )
                ),
                name="practice_answer_consistent_state",
            ),
        ]

    def __str__(self):
        return f"{self.session} – Q{self.position}"


class UserProgress(TimeStampedModel):
    """Running totals per user and language, kept so reads are cheap.

    Updated inside the same transaction as each answer (Phase 6).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="practice_progress"
    )
    language = models.ForeignKey("languages.Language", on_delete=models.PROTECT, related_name="+")
    total_xp = models.PositiveIntegerField(default=0)
    questions_answered = models.PositiveIntegerField(default=0)
    correct_answers = models.PositiveIntegerField(default=0)
    sessions_completed = models.PositiveIntegerField(default=0)
    last_practiced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "user progress"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "language"], name="practice_progress_unique_user_language"
            ),
            models.CheckConstraint(
                condition=models.Q(correct_answers__lte=models.F("questions_answered")),
                name="practice_progress_correct_lte_answered",
            ),
        ]

    def __str__(self):
        return f"{self.user} – {self.language}: {self.total_xp} XP"

    @property
    def accuracy(self):
        """Share of answers correct (0–1), or None before any answers."""
        if not self.questions_answered:
            return None
        return self.correct_answers / self.questions_answered


class UserCategoryStat(models.Model):
    """Per-category totals, used to find strong and weak areas."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="category_stats"
    )
    language = models.ForeignKey("languages.Language", on_delete=models.PROTECT, related_name="+")
    category = models.ForeignKey(QuestionCategory, on_delete=models.PROTECT, related_name="+")
    questions_answered = models.PositiveIntegerField(default=0)
    correct_answers = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "language", "category"],
                name="practice_categorystat_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(correct_answers__lte=models.F("questions_answered")),
                name="practice_categorystat_correct_lte_answered",
            ),
        ]

    def __str__(self):
        return f"{self.user} – {self.language} – {self.category}"

    @property
    def accuracy(self):
        if not self.questions_answered:
            return None
        return self.correct_answers / self.questions_answered
