"""Settings shared by every environment.

Environment-specific values (secrets, hosts, database) are defined in the
environment modules, never here, so that production cannot accidentally
inherit a development default.
"""
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
_env_file = BASE_DIR / ".env"
if _env_file.exists():
    environ.Env.read_env(_env_file)

SITE_NAME = "Language Exchange Matcher"

# Safe default; development.py turns it on explicitly.
DEBUG = False

# --------------------------------------------------------------------------
# Applications
# --------------------------------------------------------------------------
DJANGO_APPS = [
    "daphne",  # must come first: makes runserver serve WebSockets too
    "apps.core",  # before django.contrib.auth: its idempotent createsuperuser takes precedence
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "channels",
]

# Each app owns one area of the product. Most are empty until their phase.
LOCAL_APPS = [
    "apps.accounts",       # custom user model, authentication
    "apps.languages",      # languages and proficiency reference data
    "apps.profiles",       # profile, goals, interests, availability
    "apps.practice",       # questions, practice sessions, XP, difficulty
    "apps.matching",       # candidate filtering, scoring, match requests
    "apps.exchange",       # exchange rooms, messages, sessions
    "apps.feedback",       # post-session feedback
    "apps.notifications",  # in-app and email notifications
    "apps.ai_services",    # optional AI assistance with fallbacks
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "apps.profiles.middleware.OnboardingRequiredMiddleware",
    "apps.profiles.middleware.ActivityMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.security.SecurityHeadersMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.site",
                "apps.matching.context_processors.partner_requests",
                "apps.notifications.context_processors.notifications",
            ],
        },
    },
]

# --------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------
# A custom user model must exist before the first migration; see README.
AUTH_USER_MODEL = "accounts.User"

# Email sign-in for the site; username sign-in still works for the admin.
AUTHENTICATION_BACKENDS = ["apps.accounts.backends.EmailOrUsernameBackend"]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:home"  # onboarding middleware redirects if unfinished
LOGOUT_REDIRECT_URL = "core:home"
PASSWORD_RESET_TIMEOUT = 60 * 60 * 2  # reset links expire after two hours

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --------------------------------------------------------------------------
# Internationalisation
# --------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE", default="UTC")
USE_I18N = True
USE_TZ = True  # store all timestamps in UTC

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --------------------------------------------------------------------------
# Static and media files
# --------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Manifest storage everywhere (compressed, cache-busted file names), so every
# `collectstatic` run writes staticfiles.json, whichever settings module it
# used. With DEBUG=True (runserver) Django serves unhashed names, so local
# development doesn't need collectstatic. Test settings use plain storage.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# --------------------------------------------------------------------------
# Admin
# --------------------------------------------------------------------------
# A non-default admin path reduces automated login attempts.
ADMIN_URL = env("ADMIN_URL", default="admin/")

# --------------------------------------------------------------------------
# Django REST Framework
# --------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    # Every endpoint is private unless a view explicitly opts out.
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
}

# --------------------------------------------------------------------------
# Email
# --------------------------------------------------------------------------
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
DEFAULT_FROM_EMAIL = env(
    "DEFAULT_FROM_EMAIL", default="Language Exchange Matcher <noreply@localhost>"
)

# --------------------------------------------------------------------------
# Baseline security (production.py adds HTTPS-specific settings)
# --------------------------------------------------------------------------
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# --------------------------------------------------------------------------
# Logging: one line per event, key=value, to stdout (Render collects stdout)
# --------------------------------------------------------------------------
LOG_LEVEL = env("LOG_LEVEL", default="INFO")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "structured": {
            "format": (
                "time=%(asctime)s level=%(levelname)s "
                "logger=%(name)s message=%(message)s"
            ),
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "structured"},
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "apps": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
    },
}

# --------------------------------------------------------------------------
# Practice game. XP per correct answer lives on each DifficultyLevel (admin-
# editable); everything else about the game is configured here.
# --------------------------------------------------------------------------
PRACTICE = {
    "QUESTIONS_PER_SESSION": 10,
    # Bonus XP for every Nth correct answer in a row within a session.
    # Set either value to 0 to switch streak bonuses off.
    "STREAK_BONUS_EVERY": 3,
    "STREAK_BONUS_XP": 5,
    # First-session starting level (1–10) from the self-declared (or assessed) proficiency.
    "START_LEVEL_BY_PROFICIENCY": {"A1": 1, "A2": 2, "B1": 4, "B2": 6, "C1": 8, "C2": 9},
    # Proficiency estimation (apps/practice/services/proficiency.py).
    "PROFICIENCY": {
        "MIN_ANSWERS": 20,               # no assessed level before this many answers
        "FULL_CONFIDENCE_ANSWERS": 60,   # effective answers for full data confidence
        "MAX_ANSWERS": 300,              # most recent answers considered
        "HALF_LIFE_ANSWERS": 50,         # an answer's weight halves every N newer answers
        "RECENT_ANSWERS": 20,            # window for the consistency check
        "TARGET_SUCCESS": 0.7,           # "comfortable level" = where you'd get ~70% right
        "SLOPE": 1.0,                    # how sharply success falls as questions get harder
        "PRIOR_SD": 2.0,                 # how firmly the self-declared level is held at first
        # Lowest comfortable level for each CEFR-style estimate.
        "THRESHOLDS": [["A1", 0], ["A2", 2.0], ["B1", 3.5], ["B2", 5.0], ["C1", 6.5], ["C2", 8.5]],
    },
    # Adaptive difficulty (apps/practice/services/adaptive.py).
    "ADAPTIVE": {
        # Evidence window: the most recent answers in this language.
        "RECENT_ANSWERS": 10,
        "TREND_ANSWERS": 20,          # compare the latest 10 with the 10 before
        # Step from the last session's level, by recent accuracy.
        # Checked in order; the first matching rule wins.
        "STEP_RULES": [
            {"min_accuracy": 0.85, "step": 1.0},
            {"min_accuracy": 0.70, "step": 0.5},
            {"max_accuracy": 0.40, "step": -1.0},
            {"max_accuracy": 0.55, "step": -0.5},
        ],
        "TREND_THRESHOLD": 0.20,      # accuracy change that counts as a trend
        "TREND_STEP": 0.25,
        "MAX_STEP": 1.0,              # never move more than this per session
        # XP unlocks higher levels gradually: (minimum XP, highest level allowed).
        "XP_CEILINGS": [[0, 6], [300, 7], [800, 8], [1500, 9], [2500, 10]],
        # How a session is spread around its target level (offset: share).
        "MIXES": {
            "support": {"-1": 0.4, "0": 0.5, "1": 0.1},   # struggling: ease off
            "steady": {"-1": 0.2, "0": 0.6, "1": 0.2},
            "stretch": {"-1": 0.1, "0": 0.6, "1": 0.3},   # doing well: push a little
        },
        "SUPPORT_BELOW_ACCURACY": 0.5,
        "STRETCH_FROM_ACCURACY": 0.85,
        # Weak categories get extra questions.
        "WEAK_CATEGORY_ACCURACY": 0.6,
        "STRONG_CATEGORY_ACCURACY": 0.85,
        "MIN_CATEGORY_ANSWERS": 5,
        "WEAK_CATEGORY_SHARE": 0.3,
        "MAX_WEAK_CATEGORIES": 2,
    },
}

# --------------------------------------------------------------------------
# Matching (apps/matching/services/). All scores are 0–100.
# --------------------------------------------------------------------------
MATCHING = {
    # Weights must add up to 1. Match score = sum(weight × factor score).
    "WEIGHTS": {
        "language": 0.40,
        "proficiency": 0.20,
        "goals": 0.15,
        "interests": 0.10,
        "availability": 0.10,
        "communication": 0.05,
    },
    # Proficiency compatibility by difference in CEFR rank (A1=1 … C2=6).
    # Application-defined values, not a language-learning standard.
    "PROFICIENCY_SCORES": {"0": 100, "1": 90, "2": 70, "3": 50, "4+": 30},
    "PROFICIENCY_UNKNOWN_SCORE": 50,
    # Language compatibility: can the partner teach what you're learning?
    "NATIVE_TEACHER_SCORE": 100,
    "STRONG_TEACHER_SCORE": 80,      # a learning language at STRONG_LEVEL_RANK or above
    "STRONG_LEVEL_RANK": 5,          # C1
    # Candidate filtering.
    "ACTIVE_WITHIN_DAYS": 90,
    "DECLINE_COOLDOWN_DAYS": 30,
    "MAX_CANDIDATES": 500,           # most recently active reciprocal candidates scored
    # Stored suggestions.
    "MIN_SCORE": 30,
    "MAX_SUGGESTIONS": 50,
    "STALE_AFTER_MINUTES": 30,
    # Requests.
    "MAX_PENDING_SENT": 20,          # open requests one person may have sent at once
    "REQUEST_MESSAGE_MAX": 300,
    # Partner feedback (Phase 13): a capped adjustment on top of the score.
    "FEEDBACK_MIN_REVIEWS": 3,       # reviews needed before reputation counts
    "FEEDBACK_MAX_POINTS": 5,        # 5/5 average -> +5, 3/5 -> 0, 1/5 -> -5
}

# --------------------------------------------------------------------------
# Real-time (Django Channels). With REDIS_URL set, messages go through Redis,
# so any number of server processes can share rooms. Without it (local
# development only) an in-memory layer is used, which works for a single
# `runserver`. Production refuses to start without Redis.
# --------------------------------------------------------------------------
REDIS_URL = env("REDIS_URL", default="")
if REDIS_URL:
    CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels_redis.core.RedisChannelLayer", "CONFIG": {"hosts": [REDIS_URL]}},
    }
else:
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

EXCHANGE = {
    "MESSAGE_MAX_LENGTH": 2000,
    "MESSAGE_HISTORY": 100,           # messages shown when a room opens
    "RATE_LIMIT_MESSAGES": 10,        # per connection…
    "RATE_LIMIT_SECONDS": 10,         # …in this many seconds
    "MINUTES_CHOICES": [5, 10, 15, 20, 30],
    "DEFAULT_MINUTES": 10,
}

# --------------------------------------------------------------------------
# AI assistance (apps/ai_services). Optional: with no provider or key, AI
# features are switched off and everything else works as normal. The key is
# only ever used on the server.
#   AI_PROVIDER = "anthropic" (Messages API) or "openai" (any OpenAI-compatible
#   chat-completions endpoint; set AI_BASE_URL), or empty to disable.
# --------------------------------------------------------------------------
AI = {
    "PROVIDER": env("AI_PROVIDER", default=""),
    "API_KEY": env("AI_API_KEY", default=""),
    "MODEL": env("AI_MODEL", default=""),
    "BASE_URL": env("AI_BASE_URL", default=""),
    "TIMEOUT_SECONDS": 20,
    "MAX_INPUT_CHARS": 500,
    "REQUESTS_PER_HOUR": 30,          # per user, for room assistance
}

# --------------------------------------------------------------------------
# Cache: shared through Redis when available (presence, rate limits),
# otherwise in-process memory for local development.
# --------------------------------------------------------------------------
if REDIS_URL:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": REDIS_URL}}
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# --------------------------------------------------------------------------
# Background jobs (Celery). With REDIS_URL, tasks go to a worker and the
# beat scheduler runs periodic jobs. Without it (local development), tasks
# run inline, so nothing else needs to be running.
# --------------------------------------------------------------------------
CELERY_BROKER_URL = REDIS_URL or "memory://"
CELERY_TASK_ALWAYS_EAGER = not REDIS_URL
CELERY_TASK_IGNORE_RESULT = True
CELERY_TIMEZONE = "UTC"
CELERY_BEAT_SCHEDULE = {
    "session-reminders": {"task": "apps.notifications.tasks.send_session_reminders", "schedule": 5 * 60},
    "refresh-match-suggestions": {"task": "apps.matching.tasks.refresh_all_suggestions", "schedule": 60 * 60},
}

# Absolute site address for links in emails, e.g. https://example.onrender.com
SITE_URL = env("SITE_URL", default="").rstrip("/")

NOTIFICATIONS = {
    # Kinds that also send an email (the rest are in-app only).
    "EMAIL_KINDS": ["match_request", "match_accepted", "session_reminder"],
    "REMINDER_MINUTES_BEFORE": 15,    # remind this long before a shared free window starts
    "REMINDER_DEDUPE_HOURS": 12,      # at most one reminder per pair in this period
    "PRESENCE_SECONDS": 90,           # someone counts as "in the room" this long after activity
    "PAGE_SIZE": 50,
}

# --------------------------------------------------------------------------
# Security hardening (Phase 16)
# --------------------------------------------------------------------------
# Rate limits: name -> (attempts, window in seconds). Stored in the cache.
RATE_LIMITS = {
    "login_failures": (5, 15 * 60),     # per account + IP, then locked for the rest of the window
    "register": (10, 60 * 60),          # per IP
    "password_reset": (5, 60 * 60),     # per IP
    "match_request": (30, 60 * 60),     # per user
    "report": (10, 24 * 60 * 60),       # per user
    "room_message_post": (30, 60),      # per user (the no-JavaScript chat fallback)
    "translate": (120, 60 * 60),        # per user (in-chat translate/romanize)
}
# Proxies in front of the app that append to X-Forwarded-For (Render: 1).
NUM_PROXIES = env.int("NUM_PROXIES", default=0)

# Content Security Policy: where the browser may load code, styles and fonts from.
CSP_SOURCES = {
    "scripts": ["https://cdn.jsdelivr.net"],
    "styles": ["https://cdn.jsdelivr.net", "https://fonts.googleapis.com"],
    "fonts": ["https://cdn.jsdelivr.net", "https://fonts.gstatic.com"],
}
CSP_REPORT_ONLY = env.bool("CSP_REPORT_ONLY", default=False)

SESSION_COOKIE_AGE = 14 * 24 * 60 * 60   # two weeks
