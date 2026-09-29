"""Candidate filtering, stored suggestions and activity tracking (database)."""
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import BlockedUser
from apps.core.testing import make_onboarded_user, seed_reference_data
from apps.languages.models import Language, ProficiencyLevel
from apps.profiles.models import Profile, UserLanguage

from .models import Match, MatchRequest, MatchSuggestion
from .services.candidates import candidate_ids
from .services.suggestions import get_suggestions, is_stale, refresh_suggestions


class EngineTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_reference_data()
        cls.en = Language.objects.get(code="en")
        cls.bn = Language.objects.get(code="bn")

    def setUp(self):
        # Asha: native Bengali, learning English. Tom: native English, learning Bengali.
        self.asha = make_onboarded_user("asha", native="bn", learning="en", level="B1")
        self.tom = make_onboarded_user("tom", native="en", learning="bn", level="B2")

    def ids(self):
        return candidate_ids(self.asha)


class CandidateFilterTests(EngineTestCase):
    def test_reciprocal_partner_is_a_candidate(self):
        self.assertEqual(self.ids(), [self.tom.pk])

    def test_one_way_and_same_direction_users_are_not(self):
        make_onboarded_user("rahul", native="en", learning="hi")   # speaks my target, wants Hindi
        make_onboarded_user("mitu", native="bn", learning="en")    # same languages as me
        self.assertEqual(self.ids(), [self.tom.pk])

    def test_strong_learner_counts_as_speaker(self):
        mira = make_onboarded_user("mira", native="hi", learning="en", level="C1")
        UserLanguage.objects.create(user=mira, language=self.bn, role="learning",
                                    self_declared_level=ProficiencyLevel.objects.get(code="A2"))
        self.assertIn(mira.pk, self.ids())

    def test_hidden_inactive_unfinished_and_stale_users_are_excluded(self):
        cases = {
            "hidden": {"profile": {"is_discoverable": False}},
            "unfinished": {"profile": {"onboarding_completed_at": None}},
            "stale": {"profile": {"last_active_at": timezone.now() - timedelta(days=200)}},
            "deactivated": {"user": {"is_active": False}},
        }
        for name, change in cases.items():
            with self.subTest(name):
                person = make_onboarded_user(name, native="en", learning="bn")
                Profile.objects.filter(user=person).update(**change.get("profile", {}))
                type(person).objects.filter(pk=person.pk).update(**change.get("user", {}))
                self.assertNotIn(person.pk, self.ids())

    def test_blocks_in_either_direction(self):
        BlockedUser.objects.create(blocker=self.tom, blocked=self.asha)
        self.assertEqual(self.ids(), [])
        self.assertEqual(candidate_ids(self.tom), [])

    def test_existing_relationships_are_excluded(self):
        MatchRequest.objects.create(sender=self.tom, receiver=self.asha,
                                    sender_learning_language=self.bn, receiver_learning_language=self.en)
        self.assertEqual(self.ids(), [])

    def test_recent_decline_excluded_old_decline_allowed(self):
        req = MatchRequest.objects.create(sender=self.asha, receiver=self.tom, status="declined",
                                          responded_at=timezone.now() - timedelta(days=5),
                                          sender_learning_language=self.en, receiver_learning_language=self.bn)
        self.assertEqual(self.ids(), [])
        MatchRequest.objects.filter(pk=req.pk).update(responded_at=timezone.now() - timedelta(days=45))
        self.assertEqual(self.ids(), [self.tom.pk])

    def test_active_partner_excluded(self):
        low, high = Match.ordered_pair(self.asha, self.tom)
        Match.objects.create(user_a=low, user_b=high, user_a_learning_language=self.en,
                             user_b_learning_language=self.bn)
        self.assertEqual(self.ids(), [])


class SuggestionTests(EngineTestCase):
    def test_refresh_stores_scores_and_breakdown(self):
        self.assertEqual(refresh_suggestions(self.asha), 1)
        suggestion = MatchSuggestion.objects.get(user=self.asha)
        self.assertEqual(suggestion.candidate, self.tom)
        self.assertGreater(suggestion.score, 70)
        self.assertEqual(set(suggestion.breakdown), {"language", "proficiency", "goals", "interests",
                                                     "availability", "communication"})
        self.assertEqual(suggestion.breakdown["language"]["detail"]["you_learn_name"], "English")

    def test_best_match_first(self):
        weaker = make_onboarded_user("sam", native="en", learning="bn", level="A1")  # 3 levels away
        refresh_suggestions(self.asha)
        order = [s.candidate_id for s in get_suggestions(self.asha, refresh_if_stale=False)]
        self.assertEqual(order, [self.tom.pk, weaker.pk])

    @override_settings(MATCHING={"MIN_SCORE": 99})
    def test_low_scores_are_not_stored(self):
        self.assertEqual(refresh_suggestions(self.asha), 0)

    def test_refresh_replaces_old_rows(self):
        refresh_suggestions(self.asha)
        Profile.objects.filter(user=self.tom).update(is_discoverable=False)
        refresh_suggestions(self.asha)
        self.assertFalse(MatchSuggestion.objects.filter(user=self.asha).exists())

    def test_staleness(self):
        self.assertTrue(is_stale(self.asha))
        refresh_suggestions(self.asha)
        self.assertFalse(is_stale(self.asha))
        MatchSuggestion.objects.filter(user=self.asha).update(computed_at=timezone.now() - timedelta(hours=2))
        self.assertTrue(is_stale(self.asha))

    def test_editing_own_profile_makes_suggestions_stale(self):
        refresh_suggestions(self.asha)
        profile = self.asha.profile
        profile.bio = "Updated"
        profile.save()
        self.asha.refresh_from_db()
        self.assertTrue(is_stale(self.asha))

    def test_blocked_person_disappears_before_next_refresh(self):
        refresh_suggestions(self.asha)
        BlockedUser.objects.create(blocker=self.asha, blocked=self.tom)
        self.assertEqual(get_suggestions(self.asha, refresh_if_stale=False), [])

    def test_query_count_does_not_grow_with_candidates(self):
        def queries_for_refresh():
            from django.db import connection
            from django.test.utils import CaptureQueriesContext
            with CaptureQueriesContext(connection) as ctx:
                refresh_suggestions(self.asha)
            return len(ctx.captured_queries)

        few = queries_for_refresh()
        for i in range(6):
            make_onboarded_user(f"extra{i}", native="en", learning="bn")
        self.assertEqual(queries_for_refresh(), few)

    def test_compute_matches_command(self):
        out = StringIO()
        call_command("compute_matches", stdout=out)
        self.assertIn("for 2 users", out.getvalue())
        self.assertTrue(MatchSuggestion.objects.filter(user=self.tom, candidate=self.asha).exists())


class ActivityMiddlewareTests(EngineTestCase):
    def test_records_activity_at_most_every_fifteen_minutes(self):
        from django.urls import reverse
        old = timezone.now() - timedelta(hours=1)
        Profile.objects.filter(user=self.asha).update(last_active_at=old)
        self.client.force_login(self.asha)
        self.client.get(reverse("core:health"))
        first = Profile.objects.get(user=self.asha).last_active_at
        self.assertGreater(first, old)
        self.client.get(reverse("core:health"))
        self.assertEqual(Profile.objects.get(user=self.asha).last_active_at, first)
