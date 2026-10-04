"""Estimated proficiency (A1–C2) from practice answers.

In one sentence: we find the level that best explains your right and wrong
answers.

Model (a one-parameter item-response, or "Rasch", model):
    The chance of answering a Level d question correctly, for a learner whose
    comfortable level is θ, is
        P(correct) = 1 / (1 + exp(-(SLOPE · (θ − d) + logit(TARGET_SUCCESS))))
    so at θ = d the learner is expected to get TARGET_SUCCESS (70%) right.

Fitting:
    θ is the value on a 0.5–10.5 grid that maximises the likelihood of the
    learner's actual answers, with newer answers weighted more (half-life)
    and a gentle prior centred on the self-declared level, which matters
    only while there is little data. No external libraries are needed.

Confidence (0–1):
    grows with the effective number of answers, and is reduced when the
    most recent answers point to a different level than the full record.

The estimator is pure (``estimate``); ``update_assessment`` is the only
function that reads or writes the database, so the model can be replaced
later without touching the rest of the app.
"""
import math
from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone

from apps.languages.models import ProficiencyLevel
from apps.profiles.models import UserLanguage

from ..models import PracticeAnswer
from .config import practice_setting, proficiency_setting

GRID = [round(0.5 + i * 0.05, 2) for i in range(201)]  # 0.5 … 10.5


@dataclass(frozen=True)
class Observation:
    rank: int
    correct: bool
    weight: float = 1.0


@dataclass
class Estimate:
    ability: float                 # comfortable level on the 1–10 game scale
    level_code: str                # A1 … C2
    confidence: float              # 0–1
    answers: int
    recent_ability: float | None
    lowest_rank: int
    highest_rank: int
    reasons: list = field(default_factory=list)


# ------------------------------------------------------------------ the model
def _logit(p):
    return math.log(p / (1 - p))


def success_probability(ability, rank):
    slope = proficiency_setting("SLOPE")
    z = slope * (ability - rank) + _logit(proficiency_setting("TARGET_SUCCESS"))
    return 1 / (1 + math.exp(-z))


def fit_ability(observations, prior_rank):
    """Maximum a-posteriori ability on the grid (log-likelihood + Gaussian prior)."""
    prior_sd = proficiency_setting("PRIOR_SD")
    best, best_score = prior_rank, -math.inf
    for theta in GRID:
        score = -((theta - prior_rank) ** 2) / (2 * prior_sd ** 2)
        for obs in observations:
            p = success_probability(theta, obs.rank)
            score += obs.weight * math.log(p if obs.correct else 1 - p)
        if score > best_score:
            best, best_score = theta, score
    return best


def level_code_for(ability):
    code = None
    for level_code, minimum in sorted(proficiency_setting("THRESHOLDS"), key=lambda t: t[1]):
        if ability >= minimum:
            code = level_code
    return code


def weighted(rows):
    """Newest first -> Observations whose weight halves every HALF_LIFE answers."""
    half_life = proficiency_setting("HALF_LIFE_ANSWERS")
    return [Observation(rank, correct, 0.5 ** (i / half_life)) for i, (correct, rank) in enumerate(rows)]


def estimate(rows, prior_rank):
    """Pure estimator. ``rows`` are (is_correct, rank), newest first."""
    if len(rows) < proficiency_setting("MIN_ANSWERS"):
        return None
    observations = weighted(rows)
    ability = fit_ability(observations, prior_rank)

    recent_n = proficiency_setting("RECENT_ANSWERS")
    recent = [Observation(rank, correct) for correct, rank in rows[:recent_n]]
    recent_ability = fit_ability(recent, prior_rank) if len(rows) > recent_n else None

    effective = sum(o.weight for o in observations)
    data_confidence = min(1.0, effective / proficiency_setting("FULL_CONFIDENCE_ANSWERS"))
    agreement = 1.0 if recent_ability is None else 1 - min(1.0, abs(recent_ability - ability) / 2)
    confidence = round(data_confidence * (0.5 + 0.5 * agreement), 2)

    ranks = [rank for _, rank in rows]
    code = level_code_for(ability)
    correct = sum(1 for c, _ in rows if c)
    reasons = [
        f"Based on your last {len(rows)} practice answers ({round(correct / len(rows) * 100)}% correct) "
        f"at Levels {min(ranks)}–{max(ranks)}.",
        f"Your comfortable level is about Level {ability:.1f}: where you'd expect to get "
        f"{round(proficiency_setting('TARGET_SUCCESS') * 100)}% right. That corresponds to {code}.",
    ]
    if recent_ability is not None:
        if agreement >= 0.75:
            reasons.append("Your recent answers agree with your overall record.")
        else:
            direction = "higher" if recent_ability > ability else "lower"
            reasons.append(
                f"Your recent answers point {direction} (about Level {recent_ability:.1f}), "
                "so confidence is lower until the picture settles."
            )
    return Estimate(ability=ability, level_code=code, confidence=confidence, answers=len(rows),
                    recent_ability=recent_ability, lowest_rank=min(ranks), highest_rank=max(ranks),
                    reasons=reasons)


# --------------------------------------------------------------- database side
def answer_history(user, language):
    return list(
        PracticeAnswer.objects.filter(
            session__user=user, session__language=language, answered_at__isnull=False
        ).order_by("-answered_at", "-pk").values_list("is_correct", "difficulty__rank")[
            : proficiency_setting("MAX_ANSWERS")
        ]
    )


def self_declared_rank(row):
    """The self-declared level mapped onto the game scale, as the starting belief."""
    if row.self_declared_level is None:
        return 1
    return practice_setting("START_LEVEL_BY_PROFICIENCY").get(row.self_declared_level.code, 1)


def estimate_for(user, language):
    row = (
        UserLanguage.objects.filter(user=user, language=language, role=UserLanguage.Role.LEARNING)
        .select_related("self_declared_level").first()
    )
    if row is None:
        return None, None
    return row, estimate(answer_history(user, language), self_declared_rank(row))


@transaction.atomic
def update_assessment(user, language):
    """Recalculate and store the assessed level. Returns (old_code, new_code) if it changed."""
    row, result = estimate_for(user, language)
    if row is None or result is None:
        return None
    row = (
        UserLanguage.objects
        .select_for_update(of=("self",))
        .select_related("assessed_level")
        .get(pk=row.pk)
    )
    old_code = row.assessed_level.code if row.assessed_level else None
    row.assessed_level = ProficiencyLevel.objects.get(code=result.level_code)
    row.assessment_confidence = result.confidence
    row.assessed_at = timezone.now()
    row.save(update_fields=["assessed_level", "assessment_confidence", "assessed_at", "updated_at"])
    return (old_code, result.level_code) if old_code != result.level_code else None
