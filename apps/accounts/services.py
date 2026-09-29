"""Account operations. Views call these; they contain no request handling."""
import secrets

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.text import slugify

from apps.profiles.models import Profile


def generate_username(email):
    """Internal identifier derived from the email, never shown to users."""
    User = get_user_model()
    base = slugify(email.split("@", 1)[0])[:30] or "user"
    while True:
        candidate = f"{base}-{secrets.token_hex(3)}"
        if not User.objects.filter(username=candidate).exists():
            return candidate


@transaction.atomic
def register_user(*, email, password, display_name):
    """Create the account and its profile together, or neither."""
    email = email.strip().lower()
    user = get_user_model().objects.create_user(
        username=generate_username(email), email=email, password=password
    )
    Profile.objects.create(user=user, display_name=display_name.strip())
    return user


@transaction.atomic
def delete_account(user):
    """Delete the user and everything that belongs only to them.

    Cascades remove the profile, languages, practice history, matches and
    rooms. Reports and feedback written about others are kept anonymised
    (their author becomes empty). The photo file is removed after commit.
    """
    profile = getattr(user, "profile", None)
    avatar_name = profile.avatar.name if profile is not None and profile.avatar else ""
    storage = profile.avatar.storage if profile is not None else None
    user.delete()
    if avatar_name:
        transaction.on_commit(lambda: storage.delete(avatar_name))
