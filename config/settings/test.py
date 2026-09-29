"""Settings for automated tests.

Uses DATABASE_URL (PostgreSQL) when it is set, otherwise an in-memory SQLite
database so the suite can run anywhere. Run the full suite against PostgreSQL
before deploying.
"""
from .base import *  # noqa: F401,F403
from .base import LOGGING, env

DEBUG = False
SECRET_KEY = "test-only-secret-key-not-for-production"
ALLOWED_HOSTS = ["testserver", "localhost"]

DATABASES = {"default": env.db("DATABASE_URL", default="sqlite://:memory:")}

# Fast hashing keeps the suite quick; never use this outside tests.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

LOGGING = {**LOGGING, "root": {"handlers": ["console"], "level": "WARNING"}}

CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

# Tests never call a real AI provider.
AI = {"PROVIDER": "", "API_KEY": "", "MODEL": "", "BASE_URL": "", "TIMEOUT_SECONDS": 1,
      "MAX_INPUT_CHARS": 500, "REQUESTS_PER_HOUR": 30}
