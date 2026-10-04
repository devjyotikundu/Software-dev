from datetime import timedelta

from django.conf import settings
from django.shortcuts import redirect
from django.utils import timezone

# Pages a signed-in user can reach before finishing onboarding.
ALLOWED_NAMESPACES = {"onboarding", "accounts", "admin"}
ALLOWED_VIEW_NAMES = {"core:health"}


class OnboardingRequiredMiddleware:
    """Send signed-in users who haven't finished onboarding back to it."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return None
        match = request.resolver_match
        if match and (set(match.namespaces) & ALLOWED_NAMESPACES
                      or match.view_name in ALLOWED_VIEW_NAMES):
            return None
        if settings.MEDIA_URL and request.path.startswith(settings.MEDIA_URL):
            return None
        # A missing profile raises RelatedObjectDoesNotExist, an AttributeError.
        profile = getattr(user, "profile", None)
        if profile is not None and profile.is_onboarded:
            return None
        return redirect("onboarding:start")


ACTIVITY_WRITE_INTERVAL = timedelta(minutes=15)


class ActivityMiddleware:
    """Record when each signed-in user was last active.

    Matching only suggests people active recently. To keep this cheap, the
    timestamp is written at most once every 15 minutes per user.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            profile = getattr(user, "profile", None)
            now = timezone.now()
            if profile is not None and (
                profile.last_active_at is None or now - profile.last_active_at >= ACTIVITY_WRITE_INTERVAL
            ):
                type(profile).objects.filter(pk=profile.pk).update(last_active_at=now)
                profile.last_active_at = now
        return self.get_response(request)
