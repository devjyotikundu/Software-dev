"""How partner feedback shapes future recommendations.

Kept separate from scoring.py so the six-factor formula stays unchanged:

1. Never again: if either person said they wouldn't practise with the
   other again, they aren't suggested to each other in future.
2. Reputation: once someone has FEEDBACK_MIN_REVIEWS reviews, their average
   usefulness (1–5) moves their score by up to ±FEEDBACK_MAX_POINTS points
   (5/5 -> +max, 3/5 -> 0, 1/5 -> -max). The final score stays within 0–100.
Only averages are used; individual answers and comments stay private.
"""
from django.db.models import Avg, Count, Q

from apps.feedback.models import SessionFeedback

from .config import matching_setting


def never_again_ids(user):
    """People either side said they wouldn't practise with again."""
    ids = set()
    for reviewer, reviewee in SessionFeedback.objects.filter(
        Q(reviewer=user) | Q(reviewee=user), would_practice_again=False
    ).values_list("reviewer_id", "reviewee_id"):
        ids.add(reviewee if reviewer == user.pk else reviewer)
    ids.discard(None)
    return ids


def reputations(user_ids):
    """{user_id: (average usefulness, number of reviews)} in one query."""
    rows = (
        SessionFeedback.objects.filter(reviewee_id__in=user_ids)
        .values("reviewee_id").annotate(average=Avg("usefulness"), reviews=Count("id"))
    )
    return {r["reviewee_id"]: (float(r["average"]), r["reviews"]) for r in rows}


def reputation_points(average, reviews):
    if reviews < matching_setting("FEEDBACK_MIN_REVIEWS"):
        return 0.0
    return round((average - 3) / 2 * matching_setting("FEEDBACK_MAX_POINTS"), 2)


def apply(score, breakdown, reputation):
    """Adjust a score by the candidate's reputation; record it in the breakdown."""
    if not reputation:
        return score, breakdown
    average, reviews = reputation
    points = reputation_points(average, reviews)
    if not points:
        return score, breakdown
    adjusted = round(max(0.0, min(100.0, score + points)), 2)
    breakdown = {**breakdown, "feedback": {
        "points": round(adjusted - score, 2),
        "detail": {"average": round(average, 1), "reviews": reviews},
    }}
    return adjusted, breakdown
