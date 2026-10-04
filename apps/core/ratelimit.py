"""Small, dependency-free rate limiting on the Django cache.

The cache is Redis in production, so limits are shared by every server
process. Counters use fixed windows: simple, cheap, and good enough to stop
brute-force and spam.
"""
import functools
import hashlib
import logging

from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.shortcuts import redirect
from django.utils import timezone

logger = logging.getLogger(__name__)


def client_ip(request):
    """The visitor's IP address, correct behind Render's proxy.

    With NUM_PROXIES = N, the address N entries from the right of
    X-Forwarded-For is used: the one our own proxy saw. A visitor can put
    anything at the left of that header, so the leftmost value is never
    trusted. Without a proxy (N = 0), REMOTE_ADDR is used.
    """
    proxies = getattr(settings, "NUM_PROXIES", 0)
    forwarded = [part.strip() for part in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if part.strip()]
    if proxies and len(forwarded) >= proxies:
        return forwarded[-proxies]
    return request.META.get("REMOTE_ADDR", "unknown")


def _key(scope, identity, window):
    bucket = int(timezone.now().timestamp() // window)
    digest = hashlib.sha256(str(identity).lower().encode()).hexdigest()[:32]  # no raw emails/IPs in keys
    return f"rl:{scope}:{digest}:{bucket}"


def hit(scope, identity, *, limit, window):
    """Count one attempt. Returns True while within the limit."""
    key = _key(scope, identity, window)
    added = cache.add(key, 1, timeout=window)
    count = 1 if added else cache.incr(key)
    if count > limit:
        logger.warning("rate_limited scope=%s", scope)
        return False
    return True


def peek(scope, identity, *, window):
    return cache.get(_key(scope, identity, window), 0)


def reset(scope, identity, *, window):
    cache.delete(_key(scope, identity, window))


def limit_setting(name):
    return settings.RATE_LIMITS[name]


def rate_limited(name, *, by="ip", methods=("POST",), redirect_to=None, message=None):
    """View decorator. ``by`` is "ip" or "user". Over the limit: a message and a redirect
    (or a 429 page if no redirect is given)."""
    def decorator(view):
        @functools.wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.method in methods:
                limit, window = limit_setting(name)
                identity = request.user.pk if by == "user" and request.user.is_authenticated else client_ip(request)
                if not hit(name, identity, limit=limit, window=window):
                    text = message or "Too many attempts. Please wait a while and try again."
                    if redirect_to:
                        messages.error(request, text)
                        return redirect(redirect_to)
                    from django.shortcuts import render
                    return render(request, "429.html", {"message": text}, status=429)
            return view(request, *args, **kwargs)
        return wrapped
    return decorator
