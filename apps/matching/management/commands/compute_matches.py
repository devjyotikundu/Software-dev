"""Recompute stored match suggestions.

    python manage.py compute_matches              # every onboarded user
    python manage.py compute_matches --user 42    # one user

Phase 15 schedules this in the background; for now run it manually or
from a scheduler.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.matching.services.suggestions import refresh_suggestions


class Command(BaseCommand):
    help = "Recompute match suggestions."

    def add_arguments(self, parser):
        parser.add_argument("--user", type=int, help="Only this user id.")

    def handle(self, *args, user=None, **options):
        users = get_user_model().objects.filter(is_active=True, profile__onboarding_completed_at__isnull=False)
        if user:
            users = users.filter(pk=user)
        total = people = 0
        for person in users.iterator():
            total += refresh_suggestions(person)
            people += 1
        self.stdout.write(self.style.SUCCESS(f"Stored {total} suggestions for {people} users."))
