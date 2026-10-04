"""WebSocket consumer for exchange rooms.

Protocol (JSON both ways):
  client -> server   {"type": "message", "body": "..."}   send a chat message
                     {"type": "typing"}                    "partner is typing" hint
  server -> client   {"type": "message", ...}              a stored message, to both
                     {"type": "typing", "user_id": ...}    to the other partner only
                     {"type": "session", "action": ...}    session started/ended
                     {"type": "error", "error": "..."}     only to the sender
Close codes: 4401 not signed in, 4403 not a partner in this room / room closed.
"""
import json
import time
from collections import deque

from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer

from . import presence
from .services import rooms
from .services.config import exchange_setting


class RateLimiter:
    """At most ``limit`` events per ``window`` seconds (sliding window)."""

    def __init__(self, limit, window, clock=time.monotonic):
        self.limit, self.window, self.clock = limit, window, clock
        self.events = deque()

    def allow(self):
        now = self.clock()
        while self.events and now - self.events[0] >= self.window:
            self.events.popleft()
        if len(self.events) >= self.limit:
            return False
        self.events.append(now)
        return True


class RoomConsumer(JsonWebsocketConsumer):
    def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            self.close(code=4401)
            return
        room = rooms.room_for(user, self.scope["url_route"]["kwargs"]["room_id"])
        if room is None:
            self.close(code=4403)
            return
        self.user, self.room_id = user, room.pk
        self.group = rooms.group_name(room.pk)
        self.limiter = RateLimiter(exchange_setting("RATE_LIMIT_MESSAGES"), exchange_setting("RATE_LIMIT_SECONDS"))
        self.typing_limiter = RateLimiter(1, 2)
        async_to_sync(self.channel_layer.group_add)(self.group, self.channel_name)
        self.accept()
        presence.mark_present(self.room_id, user.pk)

    def disconnect(self, code):
        if hasattr(self, "group"):
            async_to_sync(self.channel_layer.group_discard)(self.group, self.channel_name)
            presence.mark_absent(self.room_id, self.user.pk)

    def receive_json(self, content, **kwargs):
        presence.mark_present(self.room_id, self.user.pk)  # still here
        kind = content.get("type") if isinstance(content, dict) else None
        if kind == "message":
            if not self.limiter.allow():
                self.send_json({"type": "error", "error": "You're sending messages very quickly. Wait a moment."})
                return
            try:
                rooms.post_message(self.user, self.room_id, content.get("body"))
            except rooms.RoomClosed as error:
                self.send_json({"type": "error", "error": str(error)})
                self.close(code=4403)
            except rooms.RoomError as error:
                self.send_json({"type": "error", "error": str(error)})
        elif kind == "typing":
            if self.typing_limiter.allow() and rooms.room_for(self.user, self.room_id):
                async_to_sync(self.channel_layer.group_send)(
                    self.group, {"type": "chat.typing", "payload": {"type": "typing", "user_id": self.user.pk}})
        else:
            self.send_json({"type": "error", "error": "Unknown message type."})

    @classmethod
    def decode_json(cls, text_data):
        """Treat anything that isn't valid JSON as an unknown message, not a crash."""
        try:
            return json.loads(text_data)
        except ValueError:
            return {}

    # Group events -> this socket
    def chat_message(self, event):
        self.send_json(event["payload"])

    def chat_typing(self, event):
        if event["payload"]["user_id"] != self.user.pk:
            self.send_json(event["payload"])

    def session_changed(self, event):
        self.send_json(event["payload"])
