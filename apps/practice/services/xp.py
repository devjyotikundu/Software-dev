"""XP rules. XP is only ever calculated here, on the server.

Base XP comes from the question's difficulty level (DifficultyLevel.xp_reward,
editable in the admin). A wrong answer earns nothing. Every Nth correct answer
in a row within one session adds a streak bonus.
"""
from dataclasses import dataclass

from .config import practice_setting


@dataclass(frozen=True)
class XpAward:
    base: int
    streak_bonus: int
    streak: int  # correct answers in a row, including this one (0 if wrong)

    @property
    def total(self):
        return self.base + self.streak_bonus


def xp_for_answer(*, difficulty, is_correct, previous_streak):
    if not is_correct:
        return XpAward(base=0, streak_bonus=0, streak=0)
    streak = previous_streak + 1
    every = practice_setting("STREAK_BONUS_EVERY")
    bonus_xp = practice_setting("STREAK_BONUS_XP")
    bonus = bonus_xp if every and bonus_xp and streak % every == 0 else 0
    return XpAward(base=difficulty.xp_reward, streak_bonus=bonus, streak=streak)


def current_streak(answers):
    """Correct answers in a row at the end of an ordered list of answered rows."""
    streak = 0
    for answer in reversed(answers):
        if not answer.is_correct:
            break
        streak += 1
    return streak
