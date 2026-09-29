"""Creating and reading notifications.

Every notification is stored in-app. Kinds listed in
NOTIFICATIONS["EMAIL_KINDS"] also send an email, in the background and only
after the database transaction commits, so a failed email never breaks the
action that caused it.
"""
from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from .models import Notification

Kind = Notification.Kind


def _setting(key):
    return settings.NOTIFICATIONS[key]


def safe_link(link):
    """Only site-relative paths ("/partners/3/"), never "//evil.example" or full URLs."""
    link = (link or "").strip()
    return link if link.startswith("/") and not link.startswith("//") else ""


def notify(recipient, kind, title, *, body="", link="", actor=None):
    if recipient is None or not recipient.is_active:
        return None
    note = Notification.objects.create(
        recipient=recipient, actor=actor, kind=kind, title=title[:120], body=body[:300], link=safe_link(link),
    )
    if kind in _setting("EMAIL_KINDS") and recipient.email:
        from .tasks import send_notification_email
        transaction.on_commit(lambda: send_notification_email.delay(note.pk))
    return note


def notify_new_message(room, sender, recipient):
    """One unread "new message" note per sender and room, updated as messages arrive.

    Skipped entirely while the recipient has the room open.
    """
    from apps.exchange.presence import is_present
    from apps.exchange.models import Message

    if is_present(room.pk, recipient.pk):
        return None
    link = reverse("exchange:room", kwargs={"room_id": room.pk})
    name = sender.profile.display_name
    existing = Notification.objects.filter(
        recipient=recipient, actor=sender, kind=Kind.NEW_MESSAGE, link=link, is_read=False
    ).first()
    if existing is None:
        return notify(recipient, Kind.NEW_MESSAGE, f"New message from {name}",
                      body=f"{name} sent you a message.", link=link, actor=sender)
    # Messages waiting for a reply: the sender's messages since the recipient last wrote.
    last_reply = (Message.objects.filter(room=room, sender=recipient)
                  .order_by("-created_at").values_list("created_at", flat=True).first())
    waiting = Message.objects.filter(room=room, sender=sender)
    count = (waiting.filter(created_at__gt=last_reply) if last_reply else waiting).count()
    existing.body = f"{name} sent you {count} messages." if count > 1 else f"{name} sent you a message."
    existing.save(update_fields=["body"])
    return existing


def unread_count(user):
    return Notification.objects.filter(recipient=user, is_read=False).count()


def mark_read(note):
    if not note.is_read:
        note.is_read, note.read_at = True, timezone.now()
        note.save(update_fields=["is_read", "read_at"])


def mark_all_read(user):
    return Notification.objects.filter(recipient=user, is_read=False).update(is_read=True, read_at=timezone.now())


# -------------------------------------------------------------- reminders
def session_reminders(now=None):
    """Remind both partners shortly before their regular shared free time starts.

    For each active match, both partners' weekly availability is converted to
    UTC and intersected (the same maths as matching). A window starting in the
    next REMINDER_MINUTES_BEFORE minutes triggers one reminder per partner,
    at most once per REMINDER_DEDUPE_HOURS. Returns the number sent.
    """
    from datetime import datetime, timedelta
    from datetime import timezone as dt_timezone

    from apps.matching.models import Match
    from apps.matching.services import availability as avail
    from apps.matching.services.profiles import load_profiles

    now = now or timezone.now()
    monday = avail.reference_monday(now.astimezone(dt_timezone.utc).date())
    week_start = datetime.combine(monday, datetime.min.time(), tzinfo=dt_timezone.utc)
    now_minute = int((now - week_start).total_seconds() // 60)
    horizon = now_minute + _setting("REMINDER_MINUTES_BEFORE")
    since = now - timedelta(hours=_setting("REMINDER_DEDUPE_HOURS"))

    matches = list(Match.objects.filter(status=Match.Status.ACTIVE).select_related("room"))
    profiles = load_profiles({uid for m in matches for uid in (m.user_a_id, m.user_b_id)})
    users = {u.pk: u for u in _users(profiles)}
    sent = 0
    for match in matches:
        a, b = profiles.get(match.user_a_id), profiles.get(match.user_b_id)
        if not a or not b or not hasattr(match, "room") or not match.room.is_active:
            continue
        overlap = avail.intersect(avail.to_utc_intervals(a.slots, a.timezone, monday),
                                  avail.to_utc_intervals(b.slots, b.timezone, monday))
        upcoming = [start for start, _ in overlap if now_minute < start <= horizon]
        if not upcoming:
            continue
        link = reverse("exchange:room", kwargs={"room_id": match.room.pk})
        for me, them in ((a, b), (b, a)):
            if Notification.objects.filter(recipient_id=me.user_id, kind=Kind.SESSION_REMINDER,
                                           link=link, created_at__gte=since).exists():
                continue
            day, start, _ = avail.describe_window((upcoming[0], upcoming[0] + 1), me.timezone, monday)
            notify(users[me.user_id], Kind.SESSION_REMINDER, f"Practice time with {them.display_name} soon",
                   body=f"You're both usually free from {start} ({day}, your time). Open your room to start a session.",
                   link=link, actor=users.get(them.user_id))
            sent += 1
    return sent


def _users(profiles):
    from django.contrib.auth import get_user_model
    return get_user_model().objects.filter(pk__in=profiles.keys(), is_active=True)
