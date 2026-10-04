"""Generate practice questions with AI, for admin review.

    python manage.py generate_questions --language bn --level 5 --category grammar --count 5
    python manage.py generate_questions --language en --for-user 42     # that learner's weakest area

Questions are saved as AI-generated and unreviewed: learners never see them
until an admin checks them and uses "Mark as reviewed" in the admin.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.ai_services.questions import difficulty_for, generate, weakest_category
from apps.languages.models import Language
from apps.practice.models import QuestionCategory
from apps.practice.services.adaptive import build_plan


class Command(BaseCommand):
    help = "Generate AI practice questions for admin review."

    def add_arguments(self, parser):
        parser.add_argument("--language", required=True)
        parser.add_argument("--level", type=int, help="Difficulty 1–10.")
        parser.add_argument("--category", help="Category slug, e.g. grammar.")
        parser.add_argument("--count", type=int, default=5)
        parser.add_argument("--for-user", type=int, help="Target this learner's level and weakest category.")

    def handle(self, *args, language, level, category, count, for_user, **options):
        lang = Language.objects.filter(code=language).first()
        if lang is None:
            raise CommandError(f"Unknown language {language!r}.")
        cat = QuestionCategory.objects.filter(slug=category).first() if category else None
        if for_user:
            user = get_user_model().objects.filter(pk=for_user).first()
            if user is None:
                raise CommandError("Unknown user.")
            plan = build_plan(user, lang)
            level = level or (plan.center if plan else 1)
            cat = cat or weakest_category(user, lang)
        cat = cat or QuestionCategory.objects.filter(slug="vocabulary").first()
        difficulty = difficulty_for(level or 1)
        if difficulty is None or cat is None:
            raise CommandError("Run seed_data first, and check --level and --category.")

        result = generate(language=lang, difficulty=difficulty, category=cat, count=max(1, min(count, 20)))
        if result.error:
            self.stdout.write(self.style.WARNING(
                f"{result.error} Practice keeps using the verified question bank."))
            return
        for text, reason in result.rejected:
            self.stdout.write(f"  rejected: {text[:60]!r} ({reason})")
        self.stdout.write(self.style.SUCCESS(
            f"Saved {len(result.created)} question(s) for review; rejected {len(result.rejected)}. "
            "Review them in the admin (Practice questions, filter Source = AI-generated)."))
