"""Celery application. Tasks live in each app's tasks.py.

    celery -A config worker -l info      # runs tasks
    celery -A config beat -l info        # schedules periodic tasks (CELERY_BEAT_SCHEDULE)
"""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

app = Celery("language_exchange")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
