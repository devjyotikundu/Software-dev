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

# Tests render templates without running collectstatic.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CELERY_BROKER_URL = "memory://"
CELERY_TASK_ALWAYS_EAGER = True
SITE_URL = "https://testserver"

# Generous limits so the rest of the suite never trips them; the rate-limit
# tests set their own low limits and clear the cache.
RATE_LIMITS = {name: (10_000, 3600) for name in (
    "login_failures", "register", "password_reset", "match_request", "report", "room_message_post")}
NUM_PROXIES = 0
