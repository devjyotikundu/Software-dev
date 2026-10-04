import logging

from celery import shared_task
from django.contrib.auth import get_user_model

from .services.suggestions import refresh_suggestions

logger = logging.getLogger(__name__)


@shared_task
def refresh_all_suggestions():
    """Hourly: keep stored match suggestions fresh (same as `manage.py compute_matches`)."""
    users = get_user_model().objects.filter(is_active=True, profile__onboarding_completed_at__isnull=False)
    total = people = 0
    for user in users.iterator():
        try:
            total += refresh_suggestions(user)
            people += 1
        except Exception:  # noqa: BLE001 — one bad profile mustn't stop the rest
            logger.exception("refresh_suggestions_failed user=%s", user.pk)
    logger.info("refresh_all_suggestions users=%s suggestions=%s", people, total)
    return total
