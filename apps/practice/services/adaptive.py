"""Adaptive difficulty: choose the level mix for a learner's next session.

Two steps, kept separate so the rules are easy to test and to replace:

    gather_evidence(user, language) -> Evidence     reads the database
    decide(evidence, ranks)         -> AdaptivePlan  pure rules, no database

The rules (all numbers live in settings.PRACTICE["ADAPTIVE"]):

1. Start from the average level of the last finished session, or, for a
   first session, from the learner's current CEFR estimate mapped to a game
   level (B1 -> Level 4).
2. Step by recent accuracy (last 10 answers): up for strong results, down
   when struggling. A clear trend across the last 20 answers adds a quarter
   level either way. The total change is capped at one level per session.
3. XP unlocks the top levels gradually (XP_CEILINGS), so nobody jumps
   straight to Level 10 on a new account.
4. Spread the session around the target: mostly at the target, some a level
   either side, leaning easier when struggling and harder when doing well.
5. Give extra questions from the learner's weakest categories.

Every decision carries the real numbers behind it, for "Why this level?".
"""
from dataclasses import dataclass, field
from math import floor

from django.db.models import Avg

from apps.profiles.models import UserLanguage

from ..models import DifficultyLevel, PracticeAnswer, PracticeSession, UserCategoryStat, UserProgress
from .config import adaptive_setting, practice_setting


# --------------------------------------------------------------------- data
@dataclass(frozen=True)
class CategoryResult:
    category_id: int
    name: str
    answered: int
    correct: int

    @property
    def accuracy(self):
        return self.correct / self.answered if self.answered else 0.0


@dataclass(frozen=True)
class Evidence:
    prior_code: str | None                 # current CEFR estimate, e.g. "B1"
    prior_rank: int                        # that estimate mapped to a game level
    last_session_rank: float | None        # average level of the last finished session
    recent: tuple = ()                     # (is_correct, rank), newest first
    total_xp: int = 0
    categories: tuple = ()                 # CategoryResult


@dataclass
class AdaptivePlan:
    target: float
    center: int                            # the level most questions are at
    distribution: dict                     # {rank: number of questions}, easiest first
    mode: str                              # "support", "steady" or "stretch"
    weak_categories: list = field(default_factory=list)
    strong_categories: list = field(default_factory=list)
    weak_question_count: int = 0
    recent_accuracy: float | None = None
    xp_ceiling: int | None = None
    reasons: list = field(default_factory=list)

    @property
    def total(self):
        return sum(self.distribution.values())


# ------------------------------------------------------------ pure decision
def _accuracy(rows):
    return sum(1 for correct, _ in rows if correct) / len(rows) if rows else None


def _step_for(accuracy):
    for rule in adaptive_setting("STEP_RULES"):
        if "min_accuracy" in rule and accuracy >= rule["min_accuracy"]:
            return rule["step"]
        if "max_accuracy" in rule and accuracy <= rule["max_accuracy"]:
            return rule["step"]
    return 0.0


def xp_ceiling(total_xp):
    ceiling = None
    for minimum_xp, highest in sorted(adaptive_setting("XP_CEILINGS")):
        if total_xp >= minimum_xp:
            ceiling = highest
    return ceiling


def _shares(center, mode, low, high):
    shares = {}
    for offset, share in adaptive_setting("MIXES")[mode].items():
        rank = min(max(center + int(offset), low), high)
        shares[rank] = shares.get(rank, 0) + share
    whole = sum(shares.values())
    return {rank: share / whole for rank, share in shares.items()}


def spread(target, mode, ranks, total):
    """Share ``total`` questions around a (possibly fractional) ``target``.

    A target of 5.5 blends the mix centred on 5 with the mix centred on 6,
    so the session's average level matches the target. The next session
    starts from that average, which is what makes half steps add up
    gradually instead of rounding to a full level every time.
    Ranks outside the available range fold onto the nearest valid one;
    largest-remainder rounding keeps the total exact.
    """
    low, high = min(ranks), max(ranks)
    # A mix may lean (e.g. "stretch" has more questions above than below).
    # Shift by its lean so the session still averages the target: the step
    # decides how far the level moves; the mix only decides the spread.
    mix = adaptive_setting("MIXES")[mode]
    lean = sum(int(offset) * share for offset, share in mix.items()) / sum(mix.values())
    anchor = target - lean
    lower = floor(anchor)
    weight_up = anchor - lower
    raw = {}
    for center, weight in ((lower, 1 - weight_up), (lower + 1, weight_up)):
        if weight <= 0:
            continue
        for rank, share in _shares(center, mode, low, high).items():
            raw[rank] = raw.get(rank, 0) + share * weight * total
    counts = {rank: floor(value) for rank, value in raw.items()}
    leftovers = sorted(raw, key=lambda r: (raw[r] - counts[r], -abs(r - target)), reverse=True)
    for rank in leftovers[: total - sum(counts.values())]:
        counts[rank] += 1
    return {rank: counts[rank] for rank in sorted(counts) if counts[rank]}


def main_level(distribution):
    """The level with the most questions (the lower one on a tie)."""
    return max(sorted(distribution), key=lambda rank: distribution[rank])


def decide(evidence, ranks, *, total=None):
    """Turn evidence into a plan. ``ranks`` are the active difficulty ranks."""
    total = total or practice_setting("QUESTIONS_PER_SESSION")
    reasons = []
    window = adaptive_setting("RECENT_ANSWERS")
    recent = list(evidence.recent[:window])
    accuracy = _accuracy(recent)

    # 1. Where we start from.
    if evidence.last_session_rank is None:
        base = evidence.prior_rank
        reasons.append(
            f"First session: starting from your {evidence.prior_code} estimate."
            if evidence.prior_code else "First session: starting at the easiest level."
        )
    else:
        base = evidence.last_session_rank

    # 2. Step by recent accuracy and trend.
    step = 0.0
    enough = len(recent) >= max(1, window // 2)
    if accuracy is not None and enough:
        step = _step_for(accuracy)
        verdict = "stepping up" if step > 0 else "easing off for now" if step < 0 else "staying at this level"
        reasons.append(f"Your last {len(recent)} answers: {round(accuracy * 100)}% correct, so we're {verdict}.")
    elif recent:
        reasons.append(f"Only {len(recent)} answers so far, so the level holds until there's more to go on.")

    earlier = list(evidence.recent[window: adaptive_setting("TREND_ANSWERS")])
    if accuracy is not None and len(earlier) >= max(1, window // 2):
        change = accuracy - _accuracy(earlier)
        if abs(change) >= adaptive_setting("TREND_THRESHOLD"):
            step += adaptive_setting("TREND_STEP") if change > 0 else -adaptive_setting("TREND_STEP")
            direction = "better" if change > 0 else "lower"
            reasons.append(f"Trend: {round(abs(change) * 100)} points {direction} than the {len(earlier)} answers before.")

    max_step = adaptive_setting("MAX_STEP")
    step = max(-max_step, min(max_step, step))
    target = base + step

    # 3. XP unlocks the top levels.
    ceiling = xp_ceiling(evidence.total_xp)
    if ceiling is not None and target > ceiling:
        target = ceiling
        reasons.append(
            f"Your {evidence.total_xp} XP opens levels up to Level {ceiling}; more practice unlocks harder ones."
        )
    target = max(min(ranks), min(max(ranks), target))

    # 4. Mix around the target.
    if accuracy is not None and enough and accuracy < adaptive_setting("SUPPORT_BELOW_ACCURACY"):
        mode = "support"
    elif accuracy is not None and enough and accuracy >= adaptive_setting("STRETCH_FROM_ACCURACY"):
        mode = "stretch"
    else:
        mode = "steady"
    distribution = spread(target, mode, ranks, total)
    center = main_level(distribution)

    # 5. Weak and strong categories.
    minimum = adaptive_setting("MIN_CATEGORY_ANSWERS")
    rated = [c for c in evidence.categories if c.answered >= minimum]
    weak = sorted((c for c in rated if c.accuracy < adaptive_setting("WEAK_CATEGORY_ACCURACY")),
                  key=lambda c: c.accuracy)[: adaptive_setting("MAX_WEAK_CATEGORIES")]
    strong = sorted((c for c in rated if c.accuracy >= adaptive_setting("STRONG_CATEGORY_ACCURACY")),
                    key=lambda c: -c.accuracy)
    weak_count = round(total * adaptive_setting("WEAK_CATEGORY_SHARE")) if weak else 0
    if weak:
        names = " and ".join(f"{c.name.lower()} ({round(c.accuracy * 100)}%)" for c in weak)
        reasons.append(f"Extra questions on {names}, your weakest area{'s' if len(weak) > 1 else ''} so far.")

    return AdaptivePlan(
        target=round(target, 2), center=center, distribution=distribution, mode=mode,
        weak_categories=weak, strong_categories=strong, weak_question_count=weak_count,
        recent_accuracy=accuracy, xp_ceiling=ceiling, reasons=reasons,
    )


# ------------------------------------------------------------ reading data
def prior_estimate(user, language):
    row = (
        UserLanguage.objects.filter(user=user, language=language, role=UserLanguage.Role.LEARNING)
        .select_related("self_declared_level", "assessed_level").first()
    )
    level = row.current_level if row else None
    if level is None:
        return None, 1
    return level.code, practice_setting("START_LEVEL_BY_PROFICIENCY").get(level.code, 1)


def gather_evidence(user, language):
    prior_code, prior_rank = prior_estimate(user, language)
    last = (
        PracticeSession.objects.filter(user=user, language=language, status=PracticeSession.Status.COMPLETED)
        .order_by("-completed_at").first()
    )
    last_rank = None
    if last is not None:
        last_rank = last.answers.aggregate(avg=Avg("difficulty__rank"))["avg"]
    recent = tuple(
        PracticeAnswer.objects.filter(
            session__user=user, session__language=language, answered_at__isnull=False
        ).order_by("-answered_at", "-pk").values_list("is_correct", "difficulty__rank")[
            : adaptive_setting("TREND_ANSWERS")
        ]
    )
    progress = UserProgress.objects.filter(user=user, language=language).first()
    categories = tuple(
        CategoryResult(s.category_id, s.category.name, s.questions_answered, s.correct_answers)
        for s in UserCategoryStat.objects.filter(user=user, language=language).select_related("category")
    )
    return Evidence(
        prior_code=prior_code, prior_rank=prior_rank, last_session_rank=last_rank,
        recent=recent, total_xp=progress.total_xp if progress else 0, categories=categories,
    )


def active_ranks():
    return list(DifficultyLevel.objects.filter(is_active=True).order_by("rank").values_list("rank", flat=True))


def build_plan(user, language):
    ranks = active_ranks()
    if not ranks:
        return None
    return decide(gather_evidence(user, language), ranks)
