"""Checking answers and preparing questions for display.

The correct answer never leaves the server before the learner has answered:
``public_question`` omits it, and ``check_answer`` is the only place the
comparison happens.
"""
from dataclasses import dataclass

from ..models import AnswerOption


class InvalidAnswer(ValueError):
    """The submitted option isn't one of A, B, C or D."""


@dataclass(frozen=True)
class AnswerCheck:
    is_correct: bool
    selected_option: str
    correct_option: str
    correct_text: str
    english_meaning: str
    english_explanation: str


def normalise_option(value):
    option = str(value or "").strip().upper()
    if option not in AnswerOption.values:
        raise InvalidAnswer("Choose one of the four options.")
    return option


def check_answer(question, selected):
    option = normalise_option(selected)
    return AnswerCheck(
        is_correct=option == question.correct_option,
        selected_option=option,
        correct_option=question.correct_option,
        correct_text=question.options[question.correct_option],
        english_meaning=question.english_meaning,
        english_explanation=question.english_explanation,
    )


def public_question(question):
    """What a learner may see before answering: no answer, no explanation."""
    return {
        "id": question.pk,
        "language": question.language.code,
        "difficulty": {"rank": question.difficulty.rank, "label": question.difficulty.label},
        "category": question.category.name,
        "text": question.question_text,
        "options": [{"key": key, "text": text} for key, text in question.options.items()],
    }
