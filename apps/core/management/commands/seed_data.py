"""Populate reference data: python manage.py seed_data

Safe to run repeatedly. Existing rows are kept as they are unless --update
is passed, so admin edits (for example a changed XP value) survive.
"""
from importlib import import_module

from django.core.management.base import BaseCommand
from django.db import transaction

# Order matters: later seeders reference rows created by earlier ones.
SEEDERS = (
    "apps.languages.seeds",
    "apps.profiles.seeds",
    "apps.practice.seeds",
)


class Command(BaseCommand):
    help = "Seed languages, proficiency and difficulty levels, goals, interests and questions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-questions",
            action="store_true",
            help="Seed reference data only, without loading the question bank.",
        )
        parser.add_argument(
            "--update",
            action="store_true",
            help="Overwrite existing reference rows with the seed values.",
        )

    def handle(self, *args, update=False, skip_questions=False, **options):
        with transaction.atomic():  # all or nothing
            for path in SEEDERS:
                results = import_module(path).seed(
                    update=update, load_questions=not skip_questions
                )
                for label, counts in results.items():
                    summary = ", ".join(f"{n} {k}" for k, n in counts.items())
                    self.stdout.write(f"{label}: {summary}")
        self.stdout.write(self.style.SUCCESS("Seed data is up to date."))
