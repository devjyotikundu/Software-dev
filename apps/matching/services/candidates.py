"""Candidate filtering: narrow everyone down to people worth scoring, in SQL.

Nobody is compared with everyone. A candidate must:
  - be an active account with a finished, discoverable profile, active recently;
  - be reciprocal: able to help with a language I'm learning, while learning
    a language I can help with ("help" = native, or learning it at C1+);
  - not be blocked by me or have blocked me;
  - not already be my active partner, or have a pending request with me,
    or have declined me (or I them) recently.
Uses the indexes on UserLanguage(language, role) and Profile(is_discoverable,
last_active_at).
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import BlockedUser
from apps.profiles.models import UserLanguage

from ..models import Match, MatchRequest
from .config import matching_setting
from .feedback import never_again_ids


def _strong_q(prefix=""):
    rank = matching_setting("STRONG_LEVEL_RANK")
    return Q(**{f"{prefix}role": UserLanguage.Role.NATIVE}) | (
        Q(**{f"{prefix}role": UserLanguage.Role.LEARNING})
        & (Q(**{f"{prefix}self_declared_level__rank__gte": rank})
           | Q(**{f"{prefix}assessed_level__rank__gte": rank}))
    )


def excluded_user_ids(user):
    """People I shouldn't be suggested, whatever their languages."""
    now = timezone.now()
    ids = set(BlockedUser.objects.filter(blocker=user).values_list("blocked_id", flat=True))
    ids |= set(BlockedUser.objects.filter(blocked=user).values_list("blocker_id", flat=True))
    for a, b in Match.objects.filter(status=Match.Status.ACTIVE).involving(user).values_list("user_a_id", "user_b_id"):
        ids.add(b if a == user.pk else a)
    cooldown = now - timedelta(days=matching_setting("DECLINE_COOLDOWN_DAYS"))
    mine = MatchRequest.objects.involving(user)
    pending = mine.filter(status=MatchRequest.Status.PENDING)
    declined = mine.filter(status=MatchRequest.Status.DECLINED, responded_at__gte=cooldown)
    for queryset in (pending, declined):
        for sender, receiver in queryset.values_list("sender_id", "receiver_id"):
            ids.add(receiver if sender == user.pk else sender)
    ids |= never_again_ids(user)  # Phase 13: "wouldn't practise again", either direction
    ids.add(user.pk)
    return ids


def candidate_ids(user):
    my_rows = UserLanguage.objects.filter(user=user)
    learning = list(my_rows.filter(role=UserLanguage.Role.LEARNING).values_list("language_id", flat=True))
    teachable = list(my_rows.filter(_strong_q()).values_list("language_id", flat=True))
    if not learning or not teachable:
        return []

    can_help_me = UserLanguage.objects.filter(_strong_q(), language_id__in=learning).values("user_id")
    wants_my_help = UserLanguage.objects.filter(
        role=UserLanguage.Role.LEARNING, language_id__in=teachable
    ).values("user_id")
    active_since = timezone.now() - timedelta(days=matching_setting("ACTIVE_WITHIN_DAYS"))

    return list(
        get_user_model().objects.filter(
            is_active=True,
            profile__is_discoverable=True,
            profile__onboarding_completed_at__isnull=False,
            profile__last_active_at__gte=active_since,
            pk__in=can_help_me,
        ).filter(pk__in=wants_my_help)
        .exclude(pk__in=excluded_user_ids(user))
        .order_by("-profile__last_active_at")
        .values_list("pk", flat=True)[: matching_setting("MAX_CANDIDATES")]
    )
