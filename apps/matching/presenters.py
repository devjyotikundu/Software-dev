"""Turn stored suggestions into what the discovery pages display.

Everything shown comes from the stored breakdown (real scores) and the
candidate's public profile. Email, exact schedule and account details are
never included.
"""
from dataclasses import dataclass, field

from .services import feedback
from .services.profiles import load_profiles
from .services.scoring import FACTORS, explain, score_pair

FACTOR_LABELS = {
    "language": ("Language exchange", "translate"),
    "proficiency": ("Similar progress", "bar-chart"),
    "goals": ("Shared goals", "bullseye"),
    "interests": ("Common interests", "heart"),
    "availability": ("Free at the same time", "calendar3"),
    "communication": ("Practice style", "chat-dots"),
}


@dataclass
class PartnerCard:
    suggestion: object
    profile: object                   # candidate's Profile (name, photo, bio)
    percent: int
    #score: object = None              # exact score, for the calculation table
    they_speak: str
    they_learn: str
    their_level: str | None
    shared_interests: list
    shared_goals: list
    score: int = 0
    other_goals: list = field(default_factory=list)
    goal_ids: set = field(default_factory=set)
    mode_ids: set = field(default_factory=set)
    you_learn_id: int | None = None
    overlap_minutes: int = 0

    @property
    def headline_goal(self):
        return (self.shared_goals or self.other_goals or [None])[0]


def card_from(profile, snapshot, score, breakdown, suggestion=None):
    lang = breakdown["language"]["detail"]
    shared_goals = breakdown["goals"]["detail"]["shared"]
    return PartnerCard(
        suggestion=suggestion, profile=profile, percent=round(float(score)), score=score,
        they_speak=lang["you_learn_name"], they_learn=lang["they_learn_name"],
        their_level=breakdown["proficiency"]["detail"].get("their_level"),
        shared_interests=breakdown["interests"]["detail"]["shared"], shared_goals=shared_goals,
        other_goals=[g for g in snapshot.goals.values() if g not in shared_goals],
        goal_ids=set(snapshot.goals), mode_ids=set(snapshot.modes),
        you_learn_id=lang.get("you_learn"),
        overlap_minutes=breakdown["availability"]["detail"].get("minutes_per_week", 0),
    )


def cards_for(suggestions):
    """PartnerCards for suggestions, loading candidates in a fixed number of queries."""
    snapshots = load_profiles([s.candidate_id for s in suggestions])
    return [
        card_from(s.candidate.profile, snapshots[s.candidate_id], s.score, s.breakdown, suggestion=s)
        for s in suggestions if s.candidate_id in snapshots
    ]


def live_card(viewer, other):
    """Score two people now (for requests and partners, who aren't in suggestions).

    Returns (card, factor rows), or (None, []) if they're no longer compatible.
    """
    snapshots = load_profiles([viewer.pk, other.pk])
    if viewer.pk not in snapshots or other.pk not in snapshots:
        return None, []
    score, breakdown = score_pair(snapshots[viewer.pk], snapshots[other.pk])
    if breakdown is None:
        return None, []
    score, breakdown = feedback.apply(score, breakdown, feedback.reputations([other.pk]).get(other.pk))
    return card_from(other.profile, snapshots[other.pk], score, breakdown), factor_rows(breakdown)


def factor_rows(breakdown):
    """For "Why this match?": each factor's label, icon, score, weight and plain-language reason."""
    reasons = dict(explain(breakdown))
    rows = []
    for name in FACTORS:
        part = breakdown[name]
        label, icon = FACTOR_LABELS[name]
        rows.append({
            "name": name, "label": label, "icon": icon, "reason": reasons[name],
            "score": round(float(part["score"])), "weight_percent": round(part["weight"] * 100),
            "points": part["points"],
        })
    if "feedback" in breakdown:
        part = breakdown["feedback"]
        rows.append({
            "name": "feedback", "label": "Partner feedback", "icon": "star", "reason": reasons["feedback"],
            "score": None, "weight_percent": None, "points": part["points"],
        })
    return rows


def apply_filters(cards, *, language=None, goal=None, mode=None, overlap_only=False):
    """Filter already-scored cards. All filters are optional and combine with AND."""
    out = []
    for card in cards:
        if language and card.you_learn_id != language:
            continue
        if goal and goal not in card.goal_ids:
            continue
        if mode and mode not in card.mode_ids:
            continue
        if overlap_only and not card.overlap_minutes:
            continue
        out.append(card)
    return out
