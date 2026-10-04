"""Background tasks. They catch and log their own failures, so a problem with
email or a scheduled job never affects what the user was doing."""
import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


@shared_task
def send_notification_email(notification_id):
    from .models import Notification

    note = Notification.objects.select_related("recipient").filter(pk=notification_id).first()
    if note is None or not note.recipient.email or not note.recipient.is_active:
        return False
    link = f"{settings.SITE_URL}{note.link}" if note.link else settings.SITE_URL
    body = f"{note.body}\n\n{link}\n\nYou're receiving this because you have an account on {settings.SITE_NAME}."
    try:
        send_mail(note.title, body.strip(), settings.DEFAULT_FROM_EMAIL, [note.recipient.email])
    except Exception:  # noqa: BLE001 — never let email break anything
        logger.exception("notification_email_failed notification=%s", notification_id)
        return False
    return True


@shared_task
def send_session_reminders():
    from .services import session_reminders

    try:
        sent = session_reminders()
    except Exception:  # noqa: BLE001
        logger.exception("session_reminders_failed")
        return 0
    logger.info("session_reminders sent=%s", sent)
    return sent
