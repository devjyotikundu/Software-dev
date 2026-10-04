"""AI endpoints. Both are POST-only, limited to the room's partners, and
answer either JSON (for the in-page helper) or a plain page (no JavaScript)."""
import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views import View

from apps.exchange.services import rooms
from apps.feedback.services import session_for_feedback
from apps.profiles.models import UserLanguage

from . import assist
from .client import AIUnavailable, is_enabled

logger = logging.getLogger(__name__)


def learner_context(user, learning_language):
    native = user.languages.filter(role=UserLanguage.Role.NATIVE).select_related("language").first()
    row = user.languages.filter(language=learning_language, role=UserLanguage.Role.LEARNING) \
        .select_related("self_declared_level", "assessed_level").first()
    level = row.current_level.code if row and row.current_level else "beginner"
    return assist.LearnerContext(learning=learning_language.name,
                                 native=native.language.name if native else "English", level=level)


def respond(request, *, ok, text, back_url, status=200):
    if request.headers.get("accept", "").startswith("application/json"):
        return JsonResponse({"ok": ok, "text": text}, status=status)
    return render(request, "ai_services/result.html", {"ok": ok, "text": text, "back_url": back_url}, status=status)


class AssistView(LoginRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, room_id):
        if not is_enabled():
            raise Http404
        room = rooms.room_for(request.user, room_id)
        if room is None:
            raise Http404
        back = reverse("exchange:room", kwargs={"room_id": room.pk})
        context = learner_context(request.user, rooms.learning_language(room, request.user))
        try:
            answer = assist.assist(request.user, request.POST.get("task"), request.POST.get("text"), context)
        except assist.AssistError as error:
            return respond(request, ok=False, text=str(error), back_url=back, status=400)
        except AIUnavailable as error:
            return respond(request, ok=False, text=str(error), back_url=back, status=503)
        return respond(request, ok=True, text=answer, back_url=back)


class SessionSummaryView(LoginRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, session_id):
        if not is_enabled():
            raise Http404
        session = session_for_feedback(request.user, session_id)
        if session is None:
            raise Http404
        back = reverse("feedback:session", kwargs={"session_id": session.pk})
        context = learner_context(request.user, rooms.learning_language(session.room, request.user))
        try:
            answer = assist.summarize_session(request.user, session, context)
        except assist.AssistError as error:
            return respond(request, ok=False, text=str(error), back_url=back, status=400)
        except AIUnavailable as error:
            return respond(request, ok=False, text=str(error), back_url=back, status=503)
        return respond(request, ok=True, text=answer, back_url=back)
