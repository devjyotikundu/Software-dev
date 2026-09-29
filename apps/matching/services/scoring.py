"""Match scoring: six transparent factors, each 0–100, and a weighted total.

    Match score = 0.40 × language + 0.20 × proficiency + 0.15 × goals
                + 0.10 × interests + 0.10 × availability + 0.05 × communication

Weights and the proficiency table live in settings.MATCHING. Every factor
also returns the facts it used, which become the "Why this match?" text,
so explanations can never disagree with the score.
"""
from dataclasses import dataclass, field

from . import availability as avail
from .config import matching_setting

FACTORS = ("language", "proficiency", "goals", "interests", "availability", "communication")


@dataclass
class MatchProfile:
    """Everything matching needs about one person, as plain data."""

    user_id: int
    display_name: str
    native: dict                           # {language_id: name}
    learning: dict                         # {language_id: (name, level_rank or None, level_code or None)}
    goals: dict = field(default_factory=dict)          # {id: name}
    interests: dict = field(default_factory=dict)
    modes: dict = field(default_factory=dict)
    timezone: str = "UTC"
    slots: list = field(default_factory=list)          # [(weekday, start, end)]

    def teaching_score(self, language_id):
        """How well this person can help with a language: native, strong learner, or not."""
        if language_id in self.native:
            return matching_setting("NATIVE_TEACHER_SCORE")
        entry = self.learning.get(language_id)
        if entry and entry[1] is not None and entry[1] >= matching_setting("STRONG_LEVEL_RANK"):
            return matching_setting("STRONG_TEACHER_SCORE")
        return 0

    def language_name(self, language_id):
        if language_id in self.native:
            return self.native[language_id]
        return self.learning[language_id][0]


def jaccard(a, b):
    """Shared items ÷ all distinct items (0–1). Two empty sets share nothing."""
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if a | b else 0.0


def proficiency_table_score(difference):
    table = matching_setting("PROFICIENCY_SCORES")
    return table.get(str(difference), table["4+"])


# ------------------------------------------------------------------ factors
def language_factor(me, them):
    """Best reciprocal pair: they can help with what I learn, and I with what they learn."""
    best = None
    for mine in me.learning:
        they_teach = them.teaching_score(mine)
        if not they_teach:
            continue
        for theirs in them.learning:
            if theirs == mine:
                continue
            i_teach = me.teaching_score(theirs)
            if not i_teach:
                continue
            score = (they_teach + i_teach) / 2
            if best is None or score > best[0]:
                best = (score, mine, theirs, they_teach, i_teach)
    if best is None:
        return 0, {}
    score, mine, theirs, they_teach, i_teach = best
    native = matching_setting("NATIVE_TEACHER_SCORE")
    return score, {
        "you_learn": mine, "you_learn_name": me.language_name(mine),
        "they_learn": theirs, "they_learn_name": them.language_name(theirs),
        "they_speak_natively": they_teach == native, "you_speak_natively": i_teach == native,
    }


def proficiency_factor(me, them, pair):
    mine = me.learning.get(pair.get("you_learn"), (None, None, None))
    theirs = them.learning.get(pair.get("they_learn"), (None, None, None))
    if mine[1] is None or theirs[1] is None:
        return matching_setting("PROFICIENCY_UNKNOWN_SCORE"), {"your_level": mine[2], "their_level": theirs[2]}
    difference = abs(mine[1] - theirs[1])
    return proficiency_table_score(difference), {
        "your_level": mine[2], "their_level": theirs[2], "difference": difference,
    }


def set_factor(mine, theirs):
    shared = sorted(set(mine) & set(theirs))
    return round(jaccard(mine, theirs) * 100, 1), {
        "shared": [mine[i] for i in shared], "total_distinct": len(set(mine) | set(theirs)),
    }


def availability_factor(me, them, monday):
    a = avail.to_utc_intervals(me.slots, me.timezone, monday)
    b = avail.to_utc_intervals(them.slots, them.timezone, monday)
    overlap = avail.intersect(a, b)
    shared = avail.total_minutes(overlap)
    smaller = min(avail.total_minutes(a), avail.total_minutes(b))
    score = round(min(1.0, shared / smaller) * 100, 1) if smaller else 0
    detail = {"minutes_per_week": shared}
    if overlap:
        longest = max(overlap, key=lambda iv: iv[1] - iv[0])
        day, start, end = avail.describe_window(longest, me.timezone, monday)
        detail["example"] = {"day": day, "start": start, "end": end, "timezone": me.timezone}
    return score, detail


# -------------------------------------------------------------------- total
def score_pair(me, them, *, monday=None):
    """Score ``them`` as a partner for ``me``. Returns (total, breakdown) or (0, None) if not reciprocal."""
    monday = monday or avail.reference_monday()
    language, pair = language_factor(me, them)
    if not language:
        return 0, None
    factors = {
        "language": (language, pair),
        "proficiency": proficiency_factor(me, them, pair),
        "goals": set_factor(me.goals, them.goals),
        "interests": set_factor(me.interests, them.interests),
        "availability": availability_factor(me, them, monday),
        "communication": set_factor(me.modes, them.modes),
    }
    weights = matching_setting("WEIGHTS")
    total_weight = sum(weights[name] for name in FACTORS)
    breakdown, total = {}, 0.0
    for name in FACTORS:
        score, detail = factors[name]
        weight = weights[name] / total_weight
        total += weight * score
        breakdown[name] = {"score": score, "weight": round(weight, 4),
                           "points": round(weight * score, 2), "detail": detail}
    return round(total, 2), breakdown


# -------------------------------------------------------------- explanation
def _list(names):
    names = list(names)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def explain(breakdown):
    """Plain-language reasons, one per factor, built only from stored numbers."""
    lines = []
    lang = breakdown["language"]["detail"]
    they = "natively" if lang["they_speak_natively"] else "fluently"
    you = "natively" if lang["you_speak_natively"] else "fluently"
    lines.append(("language", f"You're learning {lang['you_learn_name']}, which they speak {they}; "
                              f"they're learning {lang['they_learn_name']}, which you speak {you}."))

    prof = breakdown["proficiency"]["detail"]
    if prof.get("difference") is None:
        lines.append(("proficiency", "We don't have enough level information yet to compare progress."))
    else:
        gap = {0: "the same level", 1: "one level apart"}.get(prof["difference"], f"{prof['difference']} levels apart")
        lines.append(("proficiency", f"You're at {prof['your_level']} and they're at {prof['their_level']} "
                                     f"in the languages you're each learning: {gap}."))

    for name, label in (("goals", "goal"), ("interests", "interest")):
        shared = breakdown[name]["detail"]["shared"]
        if shared:
            plural = label + ("s" if len(shared) > 1 else "")
            lines.append((name, f"Shared {plural}: {_list(shared)}."))
        else:
            lines.append((name, f"No shared {label}s yet, which can be a chance to try something new."))

    slot = breakdown["availability"]["detail"]
    minutes = slot["minutes_per_week"]
    if minutes:
        hours = minutes / 60
        amount = f"{hours:g} hours" if hours >= 1 else f"{minutes} minutes"
        example = slot["example"]
        lines.append(("availability", f"You're both free for about {amount} a week, for example "
                                      f"{example['day']} {example['start']}–{example['end']} your time."))
    else:
        lines.append(("availability", "Your free times don't overlap yet; you'd need to agree a time."))

    modes = breakdown["communication"]["detail"]["shared"]
    lines.append(("communication", f"You both like practising by {_list([m.lower() for m in modes])}."
                  if modes else "You prefer different ways of practising."))

    if "feedback" in breakdown:
        detail, points = breakdown["feedback"]["detail"], breakdown["feedback"]["points"]
        change = f"adds {points:g} points" if points > 0 else f"takes {abs(points):g} points off"
        lines.append(("feedback", f"Partners rated sessions with them {detail['average']:g}/5 on average "
                                  f"({detail['reviews']} reviews), which {change}."))
    return lines
