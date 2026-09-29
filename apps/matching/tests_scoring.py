"""Pure scoring rules: no database needed."""
from datetime import date, time

from django.test import SimpleTestCase, override_settings

from .services import availability as avail
from .services.scoring import MatchProfile, explain, jaccard, proficiency_table_score, score_pair

MONDAY = date(2026, 9, 28)  # London on summer time (UTC+1), Kolkata UTC+5:30
EN, BN, HI = 1, 2, 3


def person(uid, native, learning, **extra):
    defaults = dict(goals={1: "Speaking practice"}, interests={1: "Music", 2: "Movies"},
                    modes={1: "Text"}, timezone="Asia/Kolkata", slots=[(0, time(17), time(21))])
    defaults.update(extra)
    return MatchProfile(uid, f"User {uid}", native, learning, **defaults)


ASHA = person(1, {BN: "Bengali"}, {EN: ("English", 3, "B1")},
              goals={1: "Speaking practice", 4: "Travel"},
              interests={1: "Music", 2: "Movies", 3: "Technology"}, modes={1: "Text", 2: "Voice"})
TOM = person(2, {EN: "English"}, {BN: ("Bengali", 4, "B2")},
             interests={1: "Music", 2: "Movies", 5: "Travel"},
             timezone="Europe/London", slots=[(0, time(12), time(16))])


class FactorTests(SimpleTestCase):
    def test_jaccard(self):
        self.assertEqual(jaccard({1, 2, 3}, {1, 2, 5}), 0.5)
        self.assertEqual(jaccard(set(), set()), 0.0)

    def test_proficiency_table(self):
        self.assertEqual([proficiency_table_score(d) for d in range(6)], [100, 90, 70, 50, 30, 30])

    @override_settings(MATCHING={"PROFICIENCY_SCORES": {"0": 100, "1": 50, "2": 0, "3": 0, "4+": 0}})
    def test_proficiency_table_is_configurable(self):
        self.assertEqual(proficiency_table_score(1), 50)

    def test_availability_across_time_zones(self):
        a = avail.to_utc_intervals([(0, time(17), time(21))], "Asia/Kolkata", MONDAY)
        b = avail.to_utc_intervals([(0, time(12), time(16))], "Europe/London", MONDAY)
        self.assertEqual(avail.total_minutes(avail.intersect(a, b)), 210)  # 3.5 hours

    def test_availability_wraps_around_the_week(self):
        la = avail.to_utc_intervals([(6, time(22), time(23, 59))], "America/Los_Angeles", MONDAY)
        ist = avail.to_utc_intervals([(0, time(10), time(12))], "Asia/Kolkata", MONDAY)
        self.assertEqual(avail.total_minutes(avail.intersect(la, ist)), 90)


class ScorePairTests(SimpleTestCase):
    def test_reciprocal_pair_score_is_the_weighted_sum(self):
        total, breakdown = score_pair(ASHA, TOM, monday=MONDAY)
        scores = {name: part["score"] for name, part in breakdown.items()}
        self.assertEqual(scores, {"language": 100, "proficiency": 90, "goals": 50.0, "interests": 50.0,
                                  "availability": 87.5, "communication": 50.0})
        expected = 0.4 * 100 + 0.2 * 90 + 0.15 * 50 + 0.1 * 50 + 0.1 * 87.5 + 0.05 * 50
        self.assertAlmostEqual(total, expected)
        self.assertAlmostEqual(sum(p["points"] for p in breakdown.values()), total, places=1)

    def test_score_is_symmetric(self):
        self.assertEqual(score_pair(ASHA, TOM, monday=MONDAY)[0], score_pair(TOM, ASHA, monday=MONDAY)[0])

    def test_one_way_compatibility_is_not_a_match(self):
        rahul = person(3, {EN: "English"}, {HI: ("Hindi", 2, "A2")})  # speaks my target, wants Hindi
        self.assertEqual(score_pair(ASHA, rahul, monday=MONDAY), (0, None))

    def test_same_target_language_is_not_a_match(self):
        other_learner = person(3, {BN: "Bengali"}, {EN: ("English", 3, "B1")})
        self.assertEqual(score_pair(ASHA, other_learner, monday=MONDAY), (0, None))

    def test_strong_learner_can_help(self):
        ravi = person(5, {BN: "Bengali"}, {EN: ("English", 2, "A2")})
        mira = person(4, {HI: "Hindi"}, {EN: ("English", 5, "C1"), BN: ("Bengali", 2, "A2")})
        total, breakdown = score_pair(ravi, mira, monday=MONDAY)
        self.assertEqual(breakdown["language"]["score"], 90)  # (80 fluent + 100 native) / 2
        self.assertGreater(total, 0)

    def test_unknown_levels_score_neutral(self):
        tom = person(2, {EN: "English"}, {BN: ("Bengali", None, None)})
        _, breakdown = score_pair(ASHA, tom, monday=MONDAY)
        self.assertEqual(breakdown["proficiency"]["score"], 50)

    @override_settings(MATCHING={"WEIGHTS": {"language": 1, "proficiency": 0, "goals": 0,
                                             "interests": 0, "availability": 0, "communication": 0}})
    def test_weights_are_configurable(self):
        self.assertEqual(score_pair(ASHA, TOM, monday=MONDAY)[0], 100)


class ExplanationTests(SimpleTestCase):
    def test_explanation_uses_the_real_data(self):
        _, breakdown = score_pair(ASHA, TOM, monday=MONDAY)
        text = dict(explain(breakdown))
        self.assertEqual(text["language"], "You're learning English, which they speak natively; "
                                           "they're learning Bengali, which you speak natively.")
        self.assertIn("B1", text["proficiency"]); self.assertIn("B2", text["proficiency"])
        self.assertIn("one level apart", text["proficiency"])
        self.assertEqual(text["goals"], "Shared goal: Speaking practice.")
        self.assertEqual(text["interests"], "Shared interests: Music and Movies.")
        self.assertIn("3.5 hours a week", text["availability"])
        self.assertIn("Monday 17:00–20:30 your time", text["availability"])
        self.assertEqual(text["communication"], "You both like practising by text.")

    def test_explanation_when_nothing_overlaps(self):
        tom = person(2, {EN: "English"}, {BN: ("Bengali", 4, "B2")}, goals={}, interests={9: "Art"},
                     modes={3: "Video"}, slots=[(3, time(6), time(7))])
        _, breakdown = score_pair(ASHA, tom, monday=MONDAY)
        text = dict(explain(breakdown))
        self.assertIn("don't overlap", text["availability"])
        self.assertIn("No shared interests", text["interests"])
        self.assertEqual(text["communication"], "You prefer different ways of practising.")
