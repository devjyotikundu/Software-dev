"""Choosing questions for a practice session."""
import random

from ..models import DifficultyLevel, PracticeAnswer, PracticeQuestion

# Avoid repeating anything from the learner's most recent answers when the
# bank allows it. With 10 questions per level per language, 30 covers the
# last three sessions.
RECENT_WINDOW = 30


def recent_question_ids(user, language, window=RECENT_WINDOW):
    return set(
        PracticeAnswer.objects.filter(session__user=user, session__language=language)
        .order_by("-session__created_at", "-position")
        .values_list("question_id", flat=True)[:window]
    )


def ranks_by_distance(target_rank, available_ranks):
    """Target level first, then its neighbours, nearest first (easier before harder)."""
    return sorted(available_ranks, key=lambda rank: (abs(rank - target_rank), rank))


def pick_questions(*, language, difficulty, count, user=None, exclude_ids=(), rng=None,
                   category_ids=None, widen=True):
    """Return up to ``count`` distinct servable questions near ``difficulty``.

    Order of preference:
      1. the requested level, questions the user hasn't seen recently;
      2. neighbouring levels, nearest first, still unseen;
      3. recently seen questions, in the same level order, if the bank runs short.
    Fewer than ``count`` come back only if the whole bank for the language
    is exhausted. ``category_ids`` limits the pool to those categories;
    ``widen=False`` stays at the requested level only. ``rng`` makes
    selection repeatable in tests.
    """
    rng = rng or random.Random()
    pool = {}
    for pk, rank in (
        PracticeQuestion.objects.servable()
        .filter(language=language)
        .exclude(pk__in=exclude_ids)
        .filter(**({"category_id__in": category_ids} if category_ids is not None else {}))
        .filter(**({} if widen else {"difficulty__rank": difficulty.rank}))
        .values_list("pk", "difficulty__rank")
    ):
        pool.setdefault(rank, []).append(pk)

    recent = recent_question_ids(user, language) if user is not None else set()
    order = ranks_by_distance(difficulty.rank, pool)
    chosen = []
    for allow_recent in (False, True):
        for rank in order:
            candidates = [
                pk for pk in pool[rank]
                if pk not in chosen and (allow_recent or pk not in recent)
            ]
            rng.shuffle(candidates)
            chosen.extend(candidates[: count - len(chosen)])
            if len(chosen) == count:
                break
        if len(chosen) == count:
            break

    by_id = PracticeQuestion.objects.select_related(
        "language", "difficulty", "category"
    ).in_bulk(chosen)
    return [by_id[pk] for pk in chosen]


def active_difficulties():
    return list(DifficultyLevel.objects.filter(is_active=True).order_by("rank"))
