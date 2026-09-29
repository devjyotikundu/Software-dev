"""Show how many servable questions exist per language and level.

    python manage.py question_bank_report
"""
from collections import Counter

from django.core.management.base import BaseCommand

from apps.languages.models import Language
from apps.practice.models import DifficultyLevel, PracticeQuestion


class Command(BaseCommand):
    help = "Count servable practice questions per language and difficulty level."

    def handle(self, *args, **options):
        levels = list(DifficultyLevel.objects.order_by("rank"))
        servable = Counter(
            PracticeQuestion.objects.servable().values_list("language__code", "difficulty__rank")
        )
        reviewed = Counter(
            PracticeQuestion.objects.servable().filter(is_verified=True)
            .values_list("language__code", flat=True)
        )
        header = "Language      " + " ".join(f"L{lvl.rank:<3}" for lvl in levels) + "  Total  Reviewed"
        self.stdout.write(header)
        self.stdout.write("-" * len(header))
        for language in Language.objects.active():
            counts = [servable[(language.code, lvl.rank)] for lvl in levels]
            row = f"{language.name:<13} " + " ".join(f"{n:<4}" for n in counts)
            self.stdout.write(f"{row}  {sum(counts):<6} {reviewed[language.code]}")
            short = [lvl.label for lvl, n in zip(levels, counts) if n < 10]
            if short:
                self.stdout.write(self.style.WARNING(f"  Fewer than 10 questions at: {', '.join(short)}"))
