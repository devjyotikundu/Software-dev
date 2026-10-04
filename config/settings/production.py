"""Production settings. Every secret comes from the environment."""
from django.core.exceptions import ImproperlyConfigured

from apps.core.secrets import weak_secret_key

from .base import *  # noqa: F401,F403
from .base import STORAGES, env

DEBUG = False  # never read from the environment in production

SECRET_KEY = env("SECRET_KEY")
if weak_secret_key(SECRET_KEY):
    raise ImproperlyConfigured(
        "SECRET_KEY is missing or weak. Generate one with: python -c \"from django.core.management.utils "
        "import get_random_secret_key as k; print(k())\"")

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# Render sets this automatically for web services.
_render_host = env("RENDER_EXTERNAL_HOSTNAME", default="")
if _render_host:
    ALLOWED_HOSTS.append(_render_host)
    CSRF_TRUSTED_ORIGINS.append(f"https://{_render_host}")
    SITE_URL = SITE_URL or f"https://{_render_host}"  # noqa: F405

if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("ALLOWED_HOSTS must be set in production.")

DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

# Compressed, cache-busted static files served by WhiteNoise.
STORAGES = {
    **STORAGES,
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# HTTPS: the hosting proxy terminates TLS and forwards the original scheme.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SECURE_REDIRECT_EXEMPT = [r"^health/$"]
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# HSTS: browsers remember to use HTTPS only. One year once enabled; the site
# is HTTPS-only on Render. Subdomains and preloading stay off: they affect
# more than this app and are hard to undo.
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

# Render's proxy appends the visitor's address to X-Forwarded-For.
NUM_PROXIES = env.int("NUM_PROXIES", default=1)

# Real-time rooms must share messages across processes: Redis is required.
if not REDIS_URL:  # noqa: F405
    raise ImproperlyConfigured("REDIS_URL must be set in production for exchange rooms.")
