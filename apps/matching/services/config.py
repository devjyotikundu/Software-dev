from django.conf import settings

DEFAULTS = {
    "WEIGHTS": {"language": 0.40, "proficiency": 0.20, "goals": 0.15,
                "interests": 0.10, "availability": 0.10, "communication": 0.05},
    "PROFICIENCY_SCORES": {"0": 100, "1": 90, "2": 70, "3": 50, "4+": 30},
    "PROFICIENCY_UNKNOWN_SCORE": 50,
    "NATIVE_TEACHER_SCORE": 100,
    "STRONG_TEACHER_SCORE": 80,
    "STRONG_LEVEL_RANK": 5,
    "ACTIVE_WITHIN_DAYS": 90,
    "DECLINE_COOLDOWN_DAYS": 30,
    "MAX_CANDIDATES": 500,
    "MIN_SCORE": 30,
    "MAX_SUGGESTIONS": 50,
    "STALE_AFTER_MINUTES": 30,
    "MAX_PENDING_SENT": 20,
    "REQUEST_MESSAGE_MAX": 300,
    # Partner feedback (Phase 13): a capped adjustment on top of the score.
    "FEEDBACK_MIN_REVIEWS": 3,       # reviews needed before reputation counts
    "FEEDBACK_MAX_POINTS": 5,        # 5/5 average -> +5, 3/5 -> 0, 1/5 -> -5
}


def matching_setting(key):
    return {**DEFAULTS, **getattr(settings, "MATCHING", {})}[key]
