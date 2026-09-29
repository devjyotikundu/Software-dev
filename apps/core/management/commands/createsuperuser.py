"""Django's createsuperuser, made safe to run on every deploy.

With --noinput (e.g. in a Render build or start command) and a username that
already exists, it now reports the existing account and exits successfully
instead of failing with "Error: That username is already taken." Everything
else, including interactive use, is Django's own command unchanged.

Takes precedence over django.contrib.auth's command because apps.core is
listed before django.contrib.auth in INSTALLED_APPS.
"""
import os

from django.contrib.auth.management.commands.createsuperuser import Command as DjangoCreateSuperuser


class Command(DjangoCreateSuperuser):
    def handle(self, *args, **options):
        if not options.get("interactive"):
            field = self.UserModel.USERNAME_FIELD
            username = options.get(field) or os.environ.get(f"DJANGO_SUPERUSER_{field.upper()}")
            manager = self.UserModel._default_manager.db_manager(options.get("database"))
            if username and manager.filter(**{field: username}).exists():
                self.stdout.write(f"Superuser '{username}' already exists; nothing to do.")
                return
        return super().handle(*args, **options)
