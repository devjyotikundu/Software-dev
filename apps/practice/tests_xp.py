from types import SimpleNamespace

from django.test import SimpleTestCase, override_settings

from .services.xp import current_streak, xp_for_answer

LEVEL = SimpleNamespace(xp_reward=20)


class XpRuleTests(SimpleTestCase):
    def test_correct_answer_earns_level_xp(self):
        award = xp_for_answer(difficulty=LEVEL, is_correct=True, previous_streak=0)
        self.assertEqual((award.base, award.streak_bonus, award.total, award.streak), (20, 0, 20, 1))

    def test_wrong_answer_earns_nothing_and_resets_streak(self):
        award = xp_for_answer(difficulty=LEVEL, is_correct=False, previous_streak=5)
        self.assertEqual((award.total, award.streak), (0, 0))

    def test_streak_bonus_on_every_third_correct_answer(self):
        totals = [xp_for_answer(difficulty=LEVEL, is_correct=True, previous_streak=n).total for n in range(6)]
        self.assertEqual(totals, [20, 20, 25, 20, 20, 25])

    @override_settings(PRACTICE={"STREAK_BONUS_EVERY": 0})
    def test_streak_bonus_can_be_switched_off(self):
        self.assertEqual(xp_for_answer(difficulty=LEVEL, is_correct=True, previous_streak=2).total, 20)

    @override_settings(PRACTICE={"STREAK_BONUS_EVERY": 2, "STREAK_BONUS_XP": 10})
    def test_streak_bonus_is_configurable(self):
        self.assertEqual(xp_for_answer(difficulty=LEVEL, is_correct=True, previous_streak=1).total, 30)

    def test_current_streak_counts_trailing_correct_answers(self):
        rows = [SimpleNamespace(is_correct=v) for v in (True, False, True, True)]
        self.assertEqual(current_streak(rows), 2)
        self.assertEqual(current_streak([]), 0)
