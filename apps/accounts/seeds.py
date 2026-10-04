"""Optional admin account for deployments, created from environment variables.

    DJANGO_SUPERUSER_USERNAME, DJANGO_SUPERUSER_EMAIL, DJANGO_SUPERUSER_PASSWORD

Safe on every deploy (unlike `createsuperuser --noinput`, which fails with
"That username is already taken" the second time):
  - missing account: created as a superuser;
  - existing account: kept, and made staff/superuser if it wasn't; its
    password is only reset with `seed_data --update`;
  - variables not set: nothing happens.
"""
import os

from django.contrib.auth import get_user_model


def seed(*, update, **_options):
    username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "").strip()
    password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")
    email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "").strip().lower()
    counts = {"created": 0, "updated": 0, "unchanged": 0}
    if not username or not password:
        return {"Admin account (not configured)": counts}

    User = get_user_model()
    user = User.objects.filter(username=username).first()
    if user is None:
        if email and User.objects.filter(email__iexact=email).exists():
            # Emails are unique; don't fail the deploy, just leave the email off.
            email = ""
        User.objects.create_superuser(username=username, email=email, password=password)
        counts["created"] = 1
        return {"Admin account": counts}

    changed = []
    if not (user.is_staff and user.is_superuser and user.is_active):
        user.is_staff = user.is_superuser = user.is_active = True
        changed += ["is_staff", "is_superuser", "is_active"]
    if update:
        user.set_password(password)
        changed.append("password")
    if changed:
        user.save(update_fields=changed)
        counts["updated"] = 1
    else:
        counts["unchanged"] = 1
    return {"Admin account": counts}
