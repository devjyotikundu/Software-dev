from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailOrUsernameBackend(ModelBackend):
    """Sign in with an email address (site) or a username (admin)."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        identifier = username or kwargs.get(User.USERNAME_FIELD)
        if not identifier or password is None:
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
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
