import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

from apps.core import ratelimit

logger = logging.getLogger(__name__)


def _identity(request, identifier):
    ip = ratelimit.client_ip(request) if request is not None else "no-request"
    return f"{ip}|{identifier.strip().lower()}"


class EmailOrUsernameBackend(ModelBackend):
    """Sign in with an email address (site) or a username (admin).

    Brute-force protection for both: after RATE_LIMITS["login_failures"] failed
    attempts for the same account from the same IP, further attempts are
    refused until the window passes, even with the right password. The lock
    is per account *and* IP, so an attacker can't lock someone out from
    everywhere.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        identifier = username or kwargs.get(User.USERNAME_FIELD)
        if not identifier or password is None:
            return None
        limit, window = ratelimit.limit_setting("login_failures")
        identity = _identity(request, identifier)
        if ratelimit.peek("login_failures", identity, window=window) >= limit:
            User().set_password(password)  # same timing as a normal attempt
            if request is not None:
                request.login_locked = True
            logger.warning("login_locked")
            return None

        if "@" in identifier:
            lookup = {"email__iexact": identifier.strip()}
        else:
            lookup = {User.USERNAME_FIELD: identifier}
        try:
            user = User._default_manager.get(**lookup)
        except (User.DoesNotExist, User.MultipleObjectsReturned):
            # Hash anyway so response time doesn't reveal whether an account exists.
            User().set_password(password)
            user = None
        if user is not None and user.check_password(password) and self.user_can_authenticate(user):
            ratelimit.reset("login_failures", identity, window=window)
            return user
        ratelimit.hit("login_failures", identity, limit=limit, window=window)
        return None
