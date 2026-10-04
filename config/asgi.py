"""ASGI entry point: normal HTTP plus WebSockets for exchange rooms.

WebSocket connections pass three checks before reaching a room:
  1. AllowedHostsOriginValidator: the page must come from one of our hosts
     (blocks other websites from opening sockets with a user's cookies);
  2. AuthMiddlewareStack: the Django session identifies the user;
  3. the room consumer itself: only the room's two partners may join.
"""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

# Django must be set up before importing anything that touches models.
django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

from apps.exchange.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(AuthMiddlewareStack(URLRouter(websocket_urlpatterns))),
})
