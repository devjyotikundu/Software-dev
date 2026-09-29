"""Collecting feedback after an exchange session.

Either partner can end a session; both are then asked for feedback, once
each. Individual answers are private (admins only); recommendations use
only anonymous averages and each person's own "practise again?" answer.
"""
from collections import Counter
from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.db.models import Q

from apps.exchange.models import ExchangeSession

from .models import SessionFeedback


class FeedbackError(Exception):
    pass


@dataclass(frozen=True)
class SessionSummary:
    minutes: int
    first_language: str
    second_language: str
    minutes_per_language: int
    messages_by_language: dict      # {language name or "Before the session": count}


def session_for_feedback(user, session_id):
    """A finished session the user took part in, or None."""
    return (
        ExchangeSession.objects.select_related(
            "room__match__user_a__profile", "room__match__user_b__profile", "first_language", "second_language")
        .filter(pk=session_id, status=ExchangeSession.Status.COMPLETED)
        .filter(Q(room__match__user_a=user) | Q(room__match__user_b=user))
        .first()
    )


def partner_in(session, user):
    match = session.room.match
    return match.user_b if match.user_a_id == user.pk else match.user_a


def summary(session):
    counts = Counter(
        session.room.messages.filter(created_at__gte=session.started_at, created_at__lte=session.ended_at)
        .values_list("language__name", flat=True)
    )
    return SessionSummary(
        minutes=max(1, round((session.ended_at - session.started_at).total_seconds() / 60)),
        first_language=session.first_language.name, second_language=session.second_language.name,
        minutes_per_language=session.minutes_per_language,
        messages_by_language={(name or "Outside the timer"): n for name, n in counts.items()},
    )


def already_given(session, user):
    return SessionFeedback.objects.filter(session=session, reviewer=user).exists()


def pending_session(room, user):
    """The latest finished session in this room that the user hasn't reviewed yet."""
    return (
        room.sessions.filter(status=ExchangeSession.Status.COMPLETED)
        .exclude(feedback__reviewer=user).order_by("-ended_at").first()
    )


def submit_feedback(user, session, *, usefulness, would_practice_again, difficulty, comment=""):
    if session.status != ExchangeSession.Status.COMPLETED:
        raise FeedbackError("Feedback opens when the session has ended.")
    if not 1 <= usefulness <= 5:
        raise FeedbackError("Rate usefulness from 1 to 5.")
    try:
        with transaction.atomic():
            return SessionFeedback.objects.create(
                session=session, reviewer=user, reviewee=partner_in(session, user),
                usefulness=usefulness, would_practice_again=would_practice_again,
                difficulty=difficulty, comment=comment.strip(),
            )
    except IntegrityError:
        raise FeedbackError("You've already given feedback for this session.")
