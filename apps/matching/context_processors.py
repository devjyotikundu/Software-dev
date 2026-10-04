from django.utils.functional import SimpleLazyObject

from .services.requests import pending_received_count


def partner_requests(request):
    """Number of requests waiting for the signed-in user, for the header badge.

    Lazy, so pages that don't show the header don't pay for the query.
    """
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    return {"pending_request_count": SimpleLazyObject(lambda: pending_received_count(user))}
