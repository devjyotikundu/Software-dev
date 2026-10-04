"""Room rules, shared by the HTTP views and the WebSocket consumer.

Only the two partners of an active match can use a room. Every function
re-checks that, so a block or ended partnership takes effect immediately,
even for someone who already has the room open.
"""
from dataclasses import dataclass
from datetime import datetime

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from apps.matching.models import Match
from apps.notifications.services import Kind, notify, notify_new_message

from ..models import ExchangeRoom, ExchangeSession, Message
from .config import exchange_setting


class RoomError(Exception):
    """Something the person should be told; views and the socket show the message."""


class RoomClosed(RoomError):
    pass


def group_name(room_id):
    return f"room-{room_id}"


# ------------------------------------------------------------------ access
def room_for(user, room_id):
    """The room if ``user`` is one of its two partners and it's open; otherwise None."""
    if not user or not user.is_authenticated:
        return None
    return (
        ExchangeRoom.objects.select_related(
            "match__user_a__profile", "match__user_b__profile",
            "match__user_a_learning_language", "match__user_b_learning_language",
        )
        .filter(pk=room_id, is_active=True, match__status=Match.Status.ACTIVE)
        .filter(match__in=Match.objects.involving(user))
        .first()
    )


def require_room(user, room_id):
    room = room_for(user, room_id)
    if room is None:
        raise RoomClosed("This room is no longer available.")
    return room


def partner_of(room, user):
    match = room.match
    return match.user_b if match.user_a_id == user.pk else match.user_a


def learning_language(room, user):
    match = room.match
    return match.user_a_learning_language if match.user_a_id == user.pk else match.user_b_learning_language


# ----------------------------------------------------------------- sessions
@dataclass(frozen=True)
class SessionState:
    phase: str                 # "first", "second" or "overtime"
    language_id: int
    elapsed_seconds: int
    remaining_seconds: int     # left in the current half (0 in overtime)


def session_state(session, now=None):
    """Which language the pair should be using right now (pure calculation)."""
    now = now or timezone.now()
    half = session.minutes_per_language * 60
    elapsed = max(0, int((now - session.started_at).total_seconds()))
    if elapsed < half:
        return SessionState("first", session.first_language_id, elapsed, half - elapsed)
    if elapsed < 2 * half:
        return SessionState("second", session.second_language_id, elapsed, 2 * half - elapsed)
    return SessionState("overtime", session.second_language_id, elapsed, 0)


def active_session(room):
    return room.sessions.filter(status=ExchangeSession.Status.ACTIVE).select_related(
        "first_language", "second_language").first()


def start_session(user, room_id, *, first_language_id, minutes):
    room = require_room(user, room_id)
    languages = {room.match.user_a_learning_language_id, room.match.user_b_learning_language_id}
    if first_language_id not in languages:
        raise RoomError("Choose one of the two languages you're exchanging.")
    if minutes not in exchange_setting("MINUTES_CHOICES"):
        raise RoomError("Choose a length from the list.")
    second = (languages - {first_language_id}).pop()
    try:
        with transaction.atomic():
            session = ExchangeSession.objects.create(
                room=room, started_by=user, first_language_id=first_language_id,
                second_language_id=second, minutes_per_language=minutes,
            )
    except IntegrityError:
        raise RoomError("A session is already running in this room.")
    broadcast(room.pk, "session.changed", {"type": "session", "action": "started", "by": user.pk})
    return session


@transaction.atomic
def end_session(user, room_id):
    room = require_room(user, room_id)
    session = room.sessions.select_for_update().filter(status=ExchangeSession.Status.ACTIVE).first()
    if session is None:
        raise RoomError("There's no session running.")
    session.status = ExchangeSession.Status.COMPLETED
    session.ended_at = timezone.now()
    session.save(update_fields=["status", "ended_at"])
    transaction.on_commit(lambda: broadcast(
        room.pk, "session.changed", {"type": "session", "action": "ended", "by": user.pk}))
    notify(partner_of(room, user), Kind.FEEDBACK_REQUEST, "How was your session?",
           body=f"Tell us how practising with {user.profile.display_name} went. It takes 20 seconds.",
           link=reverse("feedback:session", kwargs={"session_id": session.pk}), actor=user)
    return session


# ----------------------------------------------------------------- messages
def clean_body(body):
    body = str(body or "").strip()
    if not body:
        raise RoomError("Write a message first.")
    limit = exchange_setting("MESSAGE_MAX_LENGTH")
    if len(body) > limit:
        raise RoomError(f"Messages can be up to {limit} characters.")
    return body


def post_message(user, room_id, body):
    """Store a message, tagged with the language the pair is practising right now."""
    body = clean_body(body)
    room = require_room(user, room_id)
    session = active_session(room)
    language_id = session_state(session).language_id if session else None
    message = Message.objects.create(room=room, sender=user, body=body, language_id=language_id)
    broadcast(room.pk, "chat.message", message_payload(message, user))
    notify_new_message(room, user, partner_of(room, user))
    return message


def message_payload(message, sender):
    return {
        "type": "message", "id": message.pk, "sender_id": sender.pk,
        "sender_name": sender.profile.display_name, "body": message.body,
        "language": message.language.name if message.language_id else None,
        "created_at": message.created_at.isoformat(),
    }


def recent_messages(room):
    limit = exchange_setting("MESSAGE_HISTORY")
    newest = list(room.messages.select_related("sender__profile", "language").order_by("-created_at", "-pk")[:limit])
    return list(reversed(newest))


# ---------------------------------------------------------------- broadcast
def broadcast(room_id, event_type, payload):
    """Send an event to everyone connected to the room (no-op if nobody is)."""
    layer = get_channel_layer()
    if layer is not None:
        async_to_sync(layer.group_send)(group_name(room_id), {"type": event_type, "payload": payload})


def server_now_iso():
    return datetime.now(tz=timezone.get_current_timezone()).isoformat()
