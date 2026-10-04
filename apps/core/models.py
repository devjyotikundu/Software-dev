"""Abstract base models shared by every app. They create no tables."""
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ReferenceItem(models.Model):
    """A small admin-managed lookup value (an interest, a goal, a category).

    Stored as data, not code, so new values need no code change.
    """

    slug = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=80)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        abstract = True
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name
