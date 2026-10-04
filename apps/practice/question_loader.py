"""Load practice questions from JSON files into the database.

File format (one file per language, in apps/practice/seed_questions/):

    {
      "language": "bn",
      "questions": [
        {
          "difficulty": "A1",
          "category": "vocabulary",
          "question_text": "...",
          "options": {"A": "...", "B": "...", "C": "...", "D": "..."},
          "correct_option": "B",
          "english_meaning": "...",
          "english_explanation": "...",
          "verified": true
        }
      ]
    }

Every question is validated before anything is written. Questions already in
the database (same normalised content) are skipped, so loading is repeatable.
"""
import json
from pathlib import Path

from apps.languages.models import Language

from .models import AnswerOption, DifficultyLevel, PracticeQuestion, QuestionCategory

QUESTIONS_DIR = Path(__file__).resolve().parent / "seed_questions"

REQUIRED_FIELDS = (
    "difficulty", "category", "question_text", "options",
    "correct_option", "english_meaning", "english_explanation",
)


class QuestionFileError(ValueError):
    """Raised with a message naming the file and question that failed."""


def _validate(item, where, difficulties, categories):
    missing = [f for f in REQUIRED_FIELDS if not str(item.get(f, "")).strip()]
    if missing:
        raise QuestionFileError(f"{where}: missing {', '.join(missing)}")

    options = item["options"]
    if not isinstance(options, dict) or sorted(options) != AnswerOption.values:
        raise QuestionFileError(f"{where}: options must have exactly the keys A, B, C, D")
    texts = [" ".join(str(v).split()).casefold() for v in options.values()]
    if any(not t for t in texts):
        raise QuestionFileError(f"{where}: options must not be empty")
    if len(set(texts)) != 4:
        raise QuestionFileError(f"{where}: all four options must be different")
    if any(len(str(v)) > 255 for v in options.values()):
        raise QuestionFileError(f"{where}: options must be 255 characters or fewer")
    if item["correct_option"] not in AnswerOption.values:
        raise QuestionFileError(f"{where}: correct_option must be A, B, C or D")
    if item["difficulty"] not in difficulties:
        raise QuestionFileError(f"{where}: unknown difficulty {item['difficulty']!r}")
    if item["category"] not in categories:
        raise QuestionFileError(f"{where}: unknown category {item['category']!r}")


def load_question_file(path):
    """Validate and load one file. Returns counts of created and skipped questions."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise QuestionFileError(f"{path.name}: invalid JSON ({exc})") from exc

    try:
        language = Language.objects.get(code=data.get("language"))
    except Language.DoesNotExist:
        raise QuestionFileError(f"{path.name}: unknown language {data.get('language')!r}")

    difficulties = {d.code: d for d in DifficultyLevel.objects.all()}
    categories = {c.slug: c for c in QuestionCategory.objects.all()}
    items = data.get("questions") or []

    # Validate the whole file first, so a bad question loads nothing.
    for index, item in enumerate(items, 1):
        _validate(item, f"{path.name} question {index}", difficulties, categories)

    existing = set(
        PracticeQuestion.objects.filter(language=language).values_list("content_hash", flat=True)
    )
    counts = {"created": 0, "skipped": 0}
    for item in items:
        options = item["options"]
        content_hash = PracticeQuestion.compute_content_hash(
            item["question_text"], options.values()
        )
        if content_hash in existing:
            counts["skipped"] += 1
            continue
        PracticeQuestion.objects.create(
            language=language,
            difficulty=difficulties[item["difficulty"]],
            category=categories[item["category"]],
            question_text=item["question_text"].strip(),
            option_a=options["A"].strip(), option_b=options["B"].strip(),
            option_c=options["C"].strip(), option_d=options["D"].strip(),
            correct_option=item["correct_option"],
            english_meaning=item["english_meaning"].strip(),
            english_explanation=item["english_explanation"].strip(),
            source=PracticeQuestion.Source.VERIFIED,
            is_verified=bool(item.get("verified", False)),
        )
        existing.add(content_hash)
        counts["created"] += 1
    return counts


def load_all(directory=QUESTIONS_DIR):
    totals = {"created": 0, "skipped": 0}
    for path in sorted(Path(directory).glob("*.json")):
        for key, value in load_question_file(path).items():
            totals[key] += value
    return totals
