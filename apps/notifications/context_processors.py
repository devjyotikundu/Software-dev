from django.utils.functional import SimpleLazyObject

from .services import unread_count


def notifications(request):
    """Unread count for the header bell. Lazy: no query unless a page shows it."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    return {"unread_notification_count": SimpleLazyObject(lambda: unread_count(user))}
