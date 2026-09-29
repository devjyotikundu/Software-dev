"""Match requests: Suggested -> Request sent -> Accepted -> Match + exchange room.

Every function checks who is acting and the request's current state inside
a transaction with the row locked, so double clicks and two open tabs
can't create two matches or act on a request twice.
"""
from dataclasses import dataclass
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from apps.exchange.models import ExchangeRoom
from apps.notifications.services import Kind, notify

from ..models import Match, MatchRequest, MatchSuggestion
from .candidates import candidate_ids
from .config import matching_setting
from .suggestions import refresh_suggestions


class RequestError(Exception):
    """A problem the person can fix or should be told about; views show the message."""


@dataclass(frozen=True)
class SendResult:
    request: MatchRequest
    matched: bool             # True when their earlier request made this a mutual match
    match: Match | None = None


# ------------------------------------------------------------------ helpers
def pending_between(a, b):
    return MatchRequest.objects.filter(
        Q(sender=a, receiver=b) | Q(sender=b, receiver=a), status=MatchRequest.Status.PENDING
    )


def active_match_between(a, b):
    low, high = Match.ordered_pair(a, b)
    return Match.objects.filter(user_a=low, user_b=high, status=Match.Status.ACTIVE).first()


def pending_received_count(user):
    return MatchRequest.objects.filter(receiver=user, status=MatchRequest.Status.PENDING).count()


# --------------------------------------------------------------------- send
def send_request(sender, receiver, message=""):
    message = (message or "").strip()
    if len(message) > matching_setting("REQUEST_MESSAGE_MAX"):
        raise RequestError(f"Keep your message under {matching_setting('REQUEST_MESSAGE_MAX')} characters.")

    # Their pending request to me? Then sending back is mutual acceptance.
    incoming = MatchRequest.objects.filter(
        sender=receiver, receiver=sender, status=MatchRequest.Status.PENDING
    ).first()
    if incoming is not None:
        match = accept_request(incoming, sender)
        return SendResult(request=incoming, matched=True, match=match)

    if receiver.pk not in candidate_ids(sender):
        raise RequestError("You can only send requests to people suggested to you.")
    open_sent = MatchRequest.objects.filter(sender=sender, status=MatchRequest.Status.PENDING).count()
    if open_sent >= matching_setting("MAX_PENDING_SENT"):
        raise RequestError("You have a lot of requests waiting for replies. Cancel some before sending more.")

    suggestion = MatchSuggestion.objects.filter(user=sender, candidate=receiver).first()
    if suggestion is None:
        refresh_suggestions(sender)
        suggestion = MatchSuggestion.objects.filter(user=sender, candidate=receiver).first()
    if suggestion is None:
        raise RequestError("You can only send requests to people suggested to you.")
    pair = suggestion.breakdown["language"]["detail"]
    try:
        with transaction.atomic():
            request = MatchRequest.objects.create(
                sender=sender, receiver=receiver, message=message,
                sender_learning_language_id=pair["you_learn"],
                receiver_learning_language_id=pair["they_learn"],
                score_at_request=Decimal(str(suggestion.score)),
            )
    except IntegrityError:
        raise RequestError("You've already sent this person a request.")
    notify(receiver, Kind.MATCH_REQUEST, f"{sender.profile.display_name} wants to practise with you",
           body=message[:200] or "Open the request to see why you match.",
           link=reverse("partners:request_detail", kwargs={"pk": request.pk}), actor=sender)
    return SendResult(request=request, matched=False)


# -------------------------------------------------------------- respond
def _locked_pending(request, actor, *, role):
    locked = MatchRequest.objects.select_for_update().get(pk=request.pk)
    if getattr(locked, f"{role}_id") != actor.pk:
        raise RequestError("That request isn't yours to change.")
    if locked.status != MatchRequest.Status.PENDING:
        raise RequestError("That request has already been answered or withdrawn.")
    return locked


@transaction.atomic
def accept_request(request, receiver):
    """Confirm the match and open its private exchange room, all or nothing."""
    request = _locked_pending(request, receiver, role="receiver")
    if active_match_between(request.sender, request.receiver):
        raise RequestError("You're already partners.")
    now = timezone.now()
    request.status = MatchRequest.Status.ACCEPTED
    request.responded_at = now
    request.save(update_fields=["status", "responded_at", "updated_at"])

    sender, receiver = request.sender, request.receiver
    low, high = Match.ordered_pair(sender, receiver)
    languages = {sender.pk: request.sender_learning_language_id,
                 receiver.pk: request.receiver_learning_language_id}
    match = Match.objects.create(
        user_a=low, user_b=high, request=request,
        user_a_learning_language_id=languages[low.pk], user_b_learning_language_id=languages[high.pk],
    )
    room = ExchangeRoom.objects.create(match=match)
    # A request the other way round is no longer needed.
    pending_between(sender, receiver).exclude(pk=request.pk).update(
        status=MatchRequest.Status.CANCELLED, responded_at=now)
    notify(sender, Kind.MATCH_ACCEPTED, f"{receiver.profile.display_name} accepted your request",
           body="You're now partners. Your private exchange room is ready.",
           link=reverse("exchange:room", kwargs={"room_id": room.pk}), actor=receiver)
    return match


@transaction.atomic
def decline_request(request, receiver):
    request = _locked_pending(request, receiver, role="receiver")
    request.status = MatchRequest.Status.DECLINED
    request.responded_at = timezone.now()
    request.save(update_fields=["status", "responded_at", "updated_at"])
    return request


@transaction.atomic
def cancel_request(request, sender):
    request = _locked_pending(request, sender, role="sender")
    request.status = MatchRequest.Status.CANCELLED
    request.responded_at = timezone.now()
    request.save(update_fields=["status", "responded_at", "updated_at"])
    return request
