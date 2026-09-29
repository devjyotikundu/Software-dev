from django.core.management.base import CommandError

from apps.core.seeding import seed_reference

from .models import DifficultyLevel, QuestionCategory
from .question_loader import QuestionFileError, load_all

# Game difficulty and XP per correct answer. Codes are internal only; users
# see "Level N". Admins can change XP later; re-seeding keeps their changes.
DIFFICULTY_LEVELS = [
    {"code": f"A{rank}", "rank": rank, "label": f"Level {rank}", "xp_reward": xp}
    for rank, xp in enumerate((10, 12, 15, 18, 20, 22, 25, 28, 30, 35), 1)
]

QUESTION_CATEGORIES = [
    {"slug": "vocabulary", "name": "Vocabulary", "sort_order": 1},
    {"slug": "grammar", "name": "Grammar", "sort_order": 2},
    {"slug": "sentence-completion", "name": "Sentence completion", "sort_order": 3},
    {"slug": "context", "name": "Context", "sort_order": 4},
    {"slug": "reading-comprehension", "name": "Reading comprehension", "sort_order": 5},
    {"slug": "everyday-expressions", "name": "Everyday expressions", "sort_order": 6},
]


def seed(*, update, load_questions=True):
    results = {
        "Difficulty levels": seed_reference(
            DifficultyLevel, DIFFICULTY_LEVELS, key="code", update=update
        ),
        "Question categories": seed_reference(
            QuestionCategory, QUESTION_CATEGORIES, key="slug", update=update
        ),
    }
    if not load_questions:
        return results
    try:
        results["Practice questions"] = load_all()
    except QuestionFileError as exc:
        raise CommandError(str(exc)) from exc
    return results
