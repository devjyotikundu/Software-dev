"""Who currently has a room open, so chat notifications aren't sent to someone
who is already reading the conversation. Stored in the cache (Redis in
production, shared across processes) with a short expiry that's refreshed
while the socket is active."""
from django.conf import settings
from django.core.cache import cache


def _key(room_id, user_id):
    return f"presence:{room_id}:{user_id}"


def _ttl():
    return getattr(settings, "NOTIFICATIONS", {}).get("PRESENCE_SECONDS", 90)


def mark_present(room_id, user_id):
    cache.set(_key(room_id, user_id), True, _ttl())


def mark_absent(room_id, user_id):
    cache.delete(_key(room_id, user_id))


def is_present(room_id, user_id):
    return bool(cache.get(_key(room_id, user_id)))
