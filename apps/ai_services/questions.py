"""AI-generated practice questions: generate -> validate -> save for review.

Nothing the model writes reaches learners directly. Every question must pass
the same checks as the curated bank (question_loader._validate), plus:
  - it is written in the right script for its language;
  - it isn't a duplicate of anything in the bank or in the same batch.
Valid questions are saved with source="ai" and is_verified=False, which
PracticeQuestion.objects.servable() keeps away from learners until an admin
reviews them. If generation fails, practice simply keeps using the verified
bank (it never depends on AI).
"""
import json
import logging
import re
from dataclasses import dataclass, field

from django.db import transaction

from apps.practice.models import DifficultyLevel, PracticeQuestion, QuestionCategory
from apps.practice.question_loader import QuestionFileError, _validate

from .client import AIUnavailable, get_client

logger = logging.getLogger(__name__)

SCRIPTS = {"bn": ("\u0980", "\u09FF"), "hi": ("\u0900", "\u097F")}

SYSTEM = (
    "You write multiple-choice language-practice questions. Reply with JSON only, no prose and "
    "no code fences. Questions must be natural and correct in the target language, not translated "
    "word-for-word from English."
)

PROMPT = """Write {count} {language} questions at game difficulty {difficulty} of 10 (1 = very easy, 10 = extremely hard),
category "{category}"{focus}. Return exactly this JSON shape:
{{"questions": [{{"question_text": "...", "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
"correct_option": "A", "english_meaning": "...", "english_explanation": "..."}}]}}
Rules: the question and options are in {language}; four different options; exactly one correct answer;
english_meaning translates the question; english_explanation says briefly why the answer is right."""


@dataclass
class GenerationResult:
    created: list = field(default_factory=list)
    rejected: list = field(default_factory=list)    # (question text or "?", reason)
    error: str = ""


def extract_json(text):
    """Parse the model's reply, tolerating a ```json fence around it."""
    text = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S)
    if fence:
        text = fence.group(1)
    data = json.loads(text)
    if not isinstance(data, dict) or not isinstance(data.get("questions"), list):
        raise ValueError("Expected an object with a 'questions' list.")
    return data["questions"]


def in_script(code, item):
    """Bengali and Hindi questions must actually be written in their script."""
    texts = [item.get("question_text", "")] + list((item.get("options") or {}).values())
    if code in SCRIPTS:
        low, high = SCRIPTS[code]
        return any(low <= ch <= high for ch in item.get("question_text", "")) and \
            all(any(low <= ch <= high for ch in str(t)) or str(t).isdigit() for t in texts[1:])
    if code == "en":
        return not any(low <= ch <= high for t in texts for low, high in SCRIPTS.values() for ch in str(t))
    return True


def validate_item(item, *, language, difficulty, category, seen_hashes):
    """Return (cleaned item, None) or (None, reason)."""
    if not isinstance(item, dict):
        return None, "not an object"
    item = {**item, "difficulty": difficulty.code, "category": category.slug}
    try:
        _validate(item, "AI question", {difficulty.code: difficulty}, {category.slug: category})
    except QuestionFileError as error:
        return None, str(error).replace("AI question: ", "")
    if not in_script(language.code, item):
        return None, f"not written in {language.name}"
    content_hash = PracticeQuestion.compute_content_hash(item["question_text"], item["options"].values())
    if content_hash in seen_hashes:
        return None, "duplicate of an existing question"
    seen_hashes.add(content_hash)
    return item, None


def generate(*, language, difficulty, category, count=5, focus="", client=None):
    """Ask the model for questions and save the valid ones for review."""
    result = GenerationResult()
    try:
        reply = (client or get_client()).complete(
            system=SYSTEM,
            prompt=PROMPT.format(count=count, language=language.name, difficulty=difficulty.rank,
                                 category=category.name.lower(), focus=f", focusing on {focus}" if focus else ""),
            max_tokens=2000,
        )
        items = extract_json(reply)
    except AIUnavailable as error:
        result.error = str(error)
        return result
    except (ValueError, TypeError) as error:
        logger.warning("ai_questions_unparseable error=%s", error)
        result.error = "The AI reply wasn't valid JSON; nothing was saved."
        return result

    seen = set(PracticeQuestion.objects.filter(language=language).values_list("content_hash", flat=True))
    with transaction.atomic():
        for item in items[:count]:
            clean, reason = validate_item(item, language=language, difficulty=difficulty,
                                          category=category, seen_hashes=seen)
            if clean is None:
                result.rejected.append(((item or {}).get("question_text", "?") if isinstance(item, dict) else "?", reason))
                continue
            options = clean["options"]
            result.created.append(PracticeQuestion.objects.create(
                language=language, difficulty=difficulty, category=category,
                question_text=clean["question_text"].strip(),
                option_a=options["A"].strip(), option_b=options["B"].strip(),
                option_c=options["C"].strip(), option_d=options["D"].strip(),
                correct_option=clean["correct_option"],
                english_meaning=clean["english_meaning"].strip(),
                english_explanation=clean["english_explanation"].strip(),
                source=PracticeQuestion.Source.AI, is_verified=False, is_active=True,
            ))
    logger.info("ai_questions_generated language=%s level=%s created=%s rejected=%s",
                language.code, difficulty.code, len(result.created), len(result.rejected))
    return result


def weakest_category(user, language):
    """The learner's weakest category, for targeted generation (or None)."""
    from apps.practice.services.adaptive import gather_evidence, decide, active_ranks
    plan = decide(gather_evidence(user, language), active_ranks() or [1])
    if plan.weak_categories:
        return QuestionCategory.objects.get(pk=plan.weak_categories[0].category_id)
    return None


def difficulty_for(rank):
    return DifficultyLevel.objects.filter(rank=rank).first()
