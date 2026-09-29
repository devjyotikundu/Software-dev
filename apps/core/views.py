import logging

from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from django.views.generic import TemplateView


logger = logging.getLogger(__name__)

# Landing-page copy only. Supported languages become database records in
# Phase 2; this greeting row is presentation, not language logic.
HERO_GREETINGS = (
    {"word": "Hello", "language": "English", "code": "en"},
    {"word": "নমস্কার", "language": "Bengali", "code": "bn"},
    {"word": "नमस्ते", "language": "Hindi", "code": "hi"},
)


class HomeView(TemplateView):
    """Landing page for visitors; a short welcome for signed-in users.

    Signed-in users who haven't finished onboarding never reach this view:
    the onboarding middleware redirects them first.
    """

    def get_template_names(self):
        if self.request.user.is_authenticated:
            return ["core/welcome.html"]
        return ["core/home.html"]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        if user.is_authenticated:
            context.update(dashboard_context(user))
        else:
            context["greetings"] = HERO_GREETINGS
        return context


@never_cache
@require_GET
def health_check(request):
    """Used by the hosting platform to confirm the app and database are up.

    Returns no internal details, only whether each dependency is reachable.
    """
    try:
        connection.ensure_connection()
    except DatabaseError:
        logger.exception("health_check database=unavailable")
        return JsonResponse({"status": "error", "database": "unavailable"}, status=503)
    return JsonResponse({"status": "ok", "database": "ok"})


def dashboard_context(user):
    """Only what the dashboard needs: languages and level, progress, 2 partners, last practice."""
    from apps.matching.views import top_suggestions
    from apps.practice.models import PracticeSession
    from apps.profiles.presenters import learning_progress

    profile = user.profile
    learning = list(
        user.languages.filter(role="learning")
        .select_related("language", "self_declared_level", "assessed_level")
        .order_by("language__sort_order")
    )
    progress = {row["language"].pk: row for row in learning_progress(user)}
    return {
        "profile": profile,
        "learning": [{"row": row, "progress": progress.get(row.language_id)} for row in learning],
        "partners": top_suggestions(user, 2),
        "last_session": PracticeSession.objects.filter(user=user, status="completed")
            .select_related("language").order_by("-completed_at").first(),
    }
