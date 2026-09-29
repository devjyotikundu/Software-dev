"""Read the PRACTICE settings with safe defaults, so tests can override one key."""
from django.conf import settings

DEFAULTS = {
    "QUESTIONS_PER_SESSION": 10,
    "STREAK_BONUS_EVERY": 3,
    "STREAK_BONUS_XP": 5,
    "START_LEVEL_BY_PROFICIENCY": {"A1": 1, "A2": 2, "B1": 4, "B2": 6, "C1": 8, "C2": 9},
    "PROFICIENCY": {
        "MIN_ANSWERS": 20,
        "FULL_CONFIDENCE_ANSWERS": 60,
        "MAX_ANSWERS": 300,
        "HALF_LIFE_ANSWERS": 50,
        "RECENT_ANSWERS": 20,
        "TARGET_SUCCESS": 0.7,
        "SLOPE": 1.0,
        "PRIOR_SD": 2.0,
        "THRESHOLDS": [["A1", 0], ["A2", 2.0], ["B1", 3.5], ["B2", 5.0], ["C1", 6.5], ["C2", 8.5]],
    },
    "ADAPTIVE": {
        "RECENT_ANSWERS": 10,
        "TREND_ANSWERS": 20,
        "STEP_RULES": [
            {"min_accuracy": 0.85, "step": 1.0},
            {"min_accuracy": 0.70, "step": 0.5},
            {"max_accuracy": 0.40, "step": -1.0},
            {"max_accuracy": 0.55, "step": -0.5},
        ],
        "TREND_THRESHOLD": 0.20,
        "TREND_STEP": 0.25,
        "MAX_STEP": 1.0,
        "XP_CEILINGS": [[0, 6], [300, 7], [800, 8], [1500, 9], [2500, 10]],
        "MIXES": {
            "support": {"-1": 0.4, "0": 0.5, "1": 0.1},
            "steady": {"-1": 0.2, "0": 0.6, "1": 0.2},
            "stretch": {"-1": 0.1, "0": 0.6, "1": 0.3},
        },
        "SUPPORT_BELOW_ACCURACY": 0.5,
        "STRETCH_FROM_ACCURACY": 0.85,
        "WEAK_CATEGORY_ACCURACY": 0.6,
        "STRONG_CATEGORY_ACCURACY": 0.85,
        "MIN_CATEGORY_ANSWERS": 5,
        "WEAK_CATEGORY_SHARE": 0.3,
        "MAX_WEAK_CATEGORIES": 2,
    },
}


def practice_setting(key):
    return {**DEFAULTS, **getattr(settings, "PRACTICE", {})}[key]


def adaptive_setting(key):
    """One ADAPTIVE value; overriding a single key in settings keeps the other defaults."""
    configured = getattr(settings, "PRACTICE", {}).get("ADAPTIVE", {})
    return {**DEFAULTS["ADAPTIVE"], **configured}[key]


def proficiency_setting(key):
    configured = getattr(settings, "PRACTICE", {}).get("PROFICIENCY", {})
    return {**DEFAULTS["PROFICIENCY"], **configured}[key]
