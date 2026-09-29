"""Practice sessions: start, answer, finish.

Every write happens inside a transaction with the answer row locked, so a
double click, a refreshed form or two browser tabs can never award XP twice.
"""
import random
from collections import Counter
from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from apps.profiles.models import UserLanguage

from ..models import DifficultyLevel, PracticeAnswer, PracticeSession, UserCategoryStat, UserProgress
from .answers import AnswerCheck, check_answer
from . import adaptive, proficiency
from .questions import pick_questions
from .xp import XpAward, current_streak, xp_for_answer


class PracticeError(Exception):
    """Base class for problems a learner can cause; views show the message."""


class NoQuestionsAvailable(PracticeError):
    pass


class NotLearningLanguage(PracticeError):
    pass


class AnswerOutOfOrder(PracticeError):
    pass


class SessionNotActive(PracticeError):
    pass


# ----------------------------------------------------------------- planning
def level_for_rank(rank):
    levels = list(DifficultyLevel.objects.filter(is_active=True).order_by("rank"))
    if not levels:
        return None
    return min(levels, key=lambda level: (abs(level.rank - rank), level.rank))


def plan_session(user, language):
    """The adaptive plan for this learner's next session (see adaptive.py)."""
    return adaptive.build_plan(user, language)


def starting_rank(user, language):
    plan = plan_session(user, language)
    return plan.center if plan else 1


# ----------------------------------------------------------------- starting
def learning_languages(user):
    return [
        row.language for row in
        UserLanguage.objects.filter(user=user, role=UserLanguage.Role.LEARNING)
        .select_related("language").order_by("language__sort_order")
    ]


def active_session(user, language):
    return PracticeSession.objects.filter(
        user=user, language=language, status=PracticeSession.Status.IN_PROGRESS
    ).first()


def start_session(user, language, *, rng=None):
    """Resume the unfinished session for this language, or start a new one."""
    if language not in learning_languages(user):
        raise NotLearningLanguage("You can practise languages you're learning.")
    existing = active_session(user, language)
    if existing is not None:
        return existing

    plan = plan_session(user, language)
    questions = _questions_for_plan(user, language, plan, rng or random.Random()) if plan else []
    if not questions:
        raise NoQuestionsAvailable(f"There are no practice questions for {language.name} yet.")

    try:
        with transaction.atomic():
            session = PracticeSession.objects.create(
                user=user, language=language, question_count=len(questions)
            )
            PracticeAnswer.objects.bulk_create([
                PracticeAnswer(session=session, question=q, difficulty=q.difficulty, position=i)
                for i, q in enumerate(questions, 1)
            ])
    except IntegrityError:
        # Another request started a session at the same moment; use that one.
        return active_session(user, language)
    return session


def _questions_for_plan(user, language, plan, rng):
    """Fill each level's slots, weak-category questions first, easiest level first."""
    levels = {level.rank: level for level in DifficultyLevel.objects.filter(rank__in=plan.distribution)}
    weak_ids = [c.category_id for c in plan.weak_categories]
    weak_left = plan.weak_question_count
    chosen = []
    # Give weak-category questions to the main level first, then the others.
    order = sorted(plan.distribution, key=lambda rank: (rank != plan.center, rank))
    for rank in order:
        count, batch = plan.distribution[rank], []
        if weak_left and weak_ids:
            batch += pick_questions(language=language, difficulty=levels[rank], count=min(count, weak_left),
                                    user=user, exclude_ids=[q.pk for q in chosen], rng=rng,
                                    category_ids=weak_ids, widen=False)
            weak_left -= len(batch)
        batch += pick_questions(language=language, difficulty=levels[rank], count=count - len(batch),
                                user=user, exclude_ids=[q.pk for q in chosen + batch], rng=rng)
        chosen += batch
    # Easier questions first, so a session warms up rather than jumping about.
    return sorted(chosen, key=lambda q: q.difficulty.rank)


# ---------------------------------------------------------------- answering
def next_answer(session):
    """The first unanswered question in the session, or None if all are answered."""
    return (
        session.answers.filter(answered_at__isnull=True)
        .select_related("question__language", "question__category", "difficulty")
        .order_by("position").first()
    )


@dataclass(frozen=True)
class SubmitResult:
    answer: PracticeAnswer
    check: AnswerCheck
    xp: XpAward
    session_complete: bool
    level_change: tuple | None = None   # (old_code, new_code) when the estimate moved


@transaction.atomic
def submit_answer(session, answer_id, selected_option, *, now=None):
    """Record one answer. Raises PracticeError subclasses for anything invalid."""
    now = now or timezone.now()
    session = PracticeSession.objects.select_for_update().get(pk=session.pk)
    if session.status != PracticeSession.Status.IN_PROGRESS:
        raise SessionNotActive("This practice session has already finished.")

    expected = session.answers.filter(answered_at__isnull=True).order_by("position").first()
    if expected is None or expected.pk != answer_id:
        raise AnswerOutOfOrder("That question has already been answered.")
    answer = (
        PracticeAnswer.objects.select_for_update()
        .select_related("question__category", "difficulty")
        .get(pk=answer_id)
    )

    check = check_answer(answer.question, selected_option)  # raises InvalidAnswer
    answered_before = list(
        session.answers.filter(answered_at__isnull=False).order_by("position").only("is_correct")
    )
    award = xp_for_answer(
        difficulty=answer.difficulty, is_correct=check.is_correct,
        previous_streak=current_streak(answered_before),
    )

    answer.selected_option = check.selected_option
    answer.is_correct = check.is_correct
    answer.xp_awarded = award.total
    answer.answered_at = now
    answer.save(update_fields=["selected_option", "is_correct", "xp_awarded", "answered_at"])

    session.correct_count = F("correct_count") + int(check.is_correct)
    session.xp_earned = F("xp_earned") + award.total
    complete = len(answered_before) + 1 >= session.question_count
    update_fields = ["correct_count", "xp_earned", "updated_at"]
    if complete:
        session.status = PracticeSession.Status.COMPLETED
        session.completed_at = now
        update_fields += ["status", "completed_at"]
    session.save(update_fields=update_fields)
    session.refresh_from_db()

    _record_progress(session, answer, check.is_correct, award.total, complete, now)
    level_change = proficiency.update_assessment(session.user, session.language) if complete else None
    return SubmitResult(answer=answer, check=check, xp=award, session_complete=complete,
                        level_change=level_change)


def _record_progress(session, answer, is_correct, xp, complete, now):
    progress, _ = UserProgress.objects.get_or_create(user=session.user, language=session.language)
    UserProgress.objects.filter(pk=progress.pk).update(
        total_xp=F("total_xp") + xp,
        questions_answered=F("questions_answered") + 1,
        correct_answers=F("correct_answers") + int(is_correct),
        sessions_completed=F("sessions_completed") + int(complete),
        last_practiced_at=now,
    )
    stat, _ = UserCategoryStat.objects.get_or_create(
        user=session.user, language=session.language, category=answer.question.category
    )
    UserCategoryStat.objects.filter(pk=stat.pk).update(
        questions_answered=F("questions_answered") + 1,
        correct_answers=F("correct_answers") + int(is_correct),
    )


@transaction.atomic
def abandon_session(session):
    updated = PracticeSession.objects.filter(
        pk=session.pk, status=PracticeSession.Status.IN_PROGRESS
    ).update(status=PracticeSession.Status.ABANDONED)
    return bool(updated)


# ------------------------------------------------------------------ results
def session_accuracy(session):
    answered = session.answers.filter(answered_at__isnull=False).count()
    return session.correct_count / answered if answered else None


def main_rank(session):
    """The difficulty most questions in the session were set at."""
    ranks = Counter(session.answers.values_list("difficulty__rank", flat=True))
    if not ranks:
        return 1
    return max(sorted(ranks), key=lambda rank: ranks[rank])


def recommended_rank(session):
    """Main level of the learner's next session, from the adaptive engine."""
    return starting_rank(session.user, session.language)


def performance_summary(session):
    """Plain-language verdict built from the session's real numbers."""
    accuracy = session_accuracy(session) or 0
    if accuracy >= 0.8:
        band = "Strong"
    elif accuracy >= 0.5:
        band = "Steady"
    else:
        band = "Building up"
    return {"band": band, "accuracy_percent": round(accuracy * 100), "level": level_for_rank(main_rank(session))}
