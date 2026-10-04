"""Blocking and reporting.

A block hides both people from each other everywhere (suggestions, requests,
partner pages), closes pending requests between them and ends an active
partnership. A report is stored for admins to review.
"""
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import BlockedUser, Report

from ..models import Match, MatchRequest, MatchSuggestion
from .candidates import candidate_ids
from .requests import pending_between


def has_relationship(user, other):
    """True if ``user`` has actually come across ``other``: a suggestion, request or match.

    Blocking and reporting are limited to these people so user ids can't be probed.
    """
    if other.pk == user.pk:
        return False
    if other.pk in candidate_ids(user) or MatchSuggestion.objects.filter(user=user, candidate=other).exists():
        return True
    if MatchRequest.objects.between(user, other).exists():
        return True
    if BlockedUser.objects.filter(blocker=user, blocked=other).exists():
        return True
    return Match.objects.between(user, other).exists()


@transaction.atomic
def block_user(blocker, blocked):
    now = timezone.now()
    BlockedUser.objects.get_or_create(blocker=blocker, blocked=blocked)
    pending_between(blocker, blocked).update(status=MatchRequest.Status.CANCELLED, responded_at=now)
    low, high = Match.ordered_pair(blocker, blocked)
    for match in Match.objects.filter(user_a=low, user_b=high, status=Match.Status.ACTIVE):
        match.status = Match.Status.ENDED
        match.ended_at = now
        match.save(update_fields=["status", "ended_at", "updated_at"])
        if hasattr(match, "room"):
            match.room.is_active = False
            match.room.save(update_fields=["is_active", "updated_at"])
    MatchSuggestion.objects.filter(Q(user=blocker, candidate=blocked) | Q(user=blocked, candidate=blocker)).delete()


def unblock_user(blocker, blocked):
    return BlockedUser.objects.filter(blocker=blocker, blocked=blocked).delete()[0] > 0


@transaction.atomic
def report_user(reporter, reported, reason, details="", *, also_block=False):
    report = Report.objects.create(reporter=reporter, reported=reported, reason=reason, details=details.strip())
    if also_block:
        block_user(reporter, reported)
    return report
