from django.conf import settings

DEFAULTS = {
    "MESSAGE_MAX_LENGTH": 2000, "MESSAGE_HISTORY": 100,
    "RATE_LIMIT_MESSAGES": 10, "RATE_LIMIT_SECONDS": 10,
    "MINUTES_CHOICES": [5, 10, 15, 20, 30], "DEFAULT_MINUTES": 10,
}


def exchange_setting(key):
    return {**DEFAULTS, **getattr(settings, "EXCHANGE", {})}[key]
