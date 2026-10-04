"""Recompute every learner's estimated proficiency.

Run after changing settings.PRACTICE["PROFICIENCY"]:
    python manage.py recalculate_proficiency
"""
from django.core.management.base import BaseCommand

from apps.practice.services.proficiency import update_assessment
from apps.profiles.models import UserLanguage


class Command(BaseCommand):
    help = "Recalculate assessed proficiency for every learning language."

    def handle(self, *args, **options):
        rows = UserLanguage.objects.filter(role=UserLanguage.Role.LEARNING).select_related("user", "language")
        changed = 0
        for row in rows.iterator():
            if update_assessment(row.user, row.language):
                changed += 1
        self.stdout.write(self.style.SUCCESS(f"Checked {rows.count()} learning languages; {changed} estimates changed."))
