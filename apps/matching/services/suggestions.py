"""Compute, store and serve match suggestions.

Scores are stored in MatchSuggestion so pages never recompute them on every
request; they are refreshed when older than STALE_AFTER_MINUTES, or on
demand (``refresh_suggestions`` / ``python manage.py compute_matches``).
"""
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from ..models import MatchSuggestion
from . import feedback
from .candidates import candidate_ids
from .config import matching_setting
from .profiles import load_profiles
from .scoring import score_pair


def compute_for(user):
    """[(candidate_id, score, breakdown)] best first, without saving."""
    ids = candidate_ids(user)
    if not ids:
        return []
    profiles = load_profiles([user.pk, *ids])
    me = profiles.get(user.pk)
    if me is None:
        return []
    reputation = feedback.reputations(ids)
    results = []
    for candidate_id in ids:
        them = profiles.get(candidate_id)
        if them is None:
            continue
        score, breakdown = score_pair(me, them)
        if breakdown is None:
            continue
        score, breakdown = feedback.apply(score, breakdown, reputation.get(candidate_id))
        if score >= matching_setting("MIN_SCORE"):
            results.append((candidate_id, score, breakdown))
    results.sort(key=lambda r: (-r[1], r[0]))
    return results[: matching_setting("MAX_SUGGESTIONS")]


@transaction.atomic
def refresh_suggestions(user):
    """Replace this user's stored suggestions with freshly computed ones."""
    now = timezone.now()
    results = compute_for(user)
    MatchSuggestion.objects.filter(user=user).delete()
    MatchSuggestion.objects.bulk_create([
        MatchSuggestion(user=user, candidate_id=cid, score=Decimal(str(score)),
                        breakdown=breakdown, computed_at=now)
        for cid, score, breakdown in results
    ])
    return len(results)


def is_stale(user):
    latest = MatchSuggestion.objects.filter(user=user).order_by("-computed_at") \
        .values_list("computed_at", flat=True).first()
    profile = getattr(user, "profile", None)
    if latest is None:
        return True
    if profile is not None and profile.updated_at > latest:
        return True  # the user changed their own profile since the last run
    return timezone.now() - latest > timedelta(minutes=matching_setting("STALE_AFTER_MINUTES"))


def get_suggestions(user, *, refresh_if_stale=True):
    """Stored suggestions, best first, refreshing first if they're out of date.

    Suggestions for people who have since become unavailable (blocked,
    matched, hidden…) are filtered out even before the next refresh.
    """
    if refresh_if_stale and is_stale(user):
        refresh_suggestions(user)
    still_valid = set(candidate_ids(user))
    return [
        s for s in MatchSuggestion.objects.filter(user=user)
        .select_related("candidate__profile").order_by("-score", "candidate_id")
        if s.candidate_id in still_valid
    ]
