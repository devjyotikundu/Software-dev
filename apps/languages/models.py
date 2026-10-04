from django.db import models


class LanguageQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class Language(models.Model):
    """A language users can speak or learn. Adding one is a data change only."""

    code = models.CharField(
        max_length=10, unique=True, help_text="BCP 47 tag, for example en, bn or hi."
    )
    name = models.CharField(max_length=60, help_text="Name in English.")
    native_name = models.CharField(max_length=60, help_text="Name in the language itself.")
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    objects = LanguageQuerySet.as_manager()

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class ProficiencyLevel(models.Model):
    """Estimated proficiency (A1–C2) shown to users.

    These are application estimates modelled on CEFR labels, not official
    certification. ``rank`` orders the levels and drives compatibility maths.
    """

    code = models.CharField(max_length=2, unique=True)
    name = models.CharField(max_length=40)
    rank = models.PositiveSmallIntegerField(unique=True)
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["rank"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(rank__gte=1), name="languages_proficiency_rank_gte_1"
            ),
        ]

    def __str__(self):
        return f"{self.code} ({self.name})"
