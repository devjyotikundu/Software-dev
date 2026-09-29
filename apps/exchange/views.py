"""Room pages. Every view resolves the room through rooms.room_for, so only the
two partners of an active match ever get past the first line."""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.shortcuts import redirect
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.matching.services.profiles import load_profiles

from apps.ai_services.assist import TASKS
from apps.ai_services.client import is_enabled as ai_enabled
from apps.feedback.services import pending_session

AI_TASKS = [(key, label) for key, (label, _) in TASKS.items()]

from .forms import MessageForm, StartSessionForm
from .services import rooms
from .starters import starters_for


class RoomView(LoginRequiredMixin, TemplateView):
    template_name = "exchange/room.html"

    def get_context_data(self, **kwargs):
        user = self.request.user
        room = rooms.room_for(user, kwargs["room_id"])
        if room is None:
            raise Http404("Room not found.")
        partner = rooms.partner_of(room, user)
        session = rooms.active_session(room)
        state = rooms.session_state(session) if session else None
        snapshots = load_profiles([user.pk, partner.pk])
        shared = set(snapshots[user.pk].interests) & set(snapshots[partner.pk].interests)
        from apps.profiles.models import Interest
        slugs = list(Interest.objects.filter(pk__in=shared).values_list("slug", flat=True))
        return super().get_context_data(
            **kwargs, room=room, partner=partner,
            you_learn=rooms.learning_language(room, user), they_learn=rooms.learning_language(room, partner),
            session=session, state=state, history=rooms.recent_messages(room),
            start_form=StartSessionForm(room=room), message_form=MessageForm(),
            starters=starters_for(sorted(slugs), seed=f"{room.pk}-{timezone.now().date()}"),
            feedback_due=pending_session(room, user),
            ai_enabled=ai_enabled(), ai_tasks=AI_TASKS,
            server_now=timezone.now().isoformat(),
        )


class PostMessageView(LoginRequiredMixin, View):
    """Fallback for browsers without WebSockets: an ordinary form post."""

    http_method_names = ["post"]

    def post(self, request, room_id):
        form = MessageForm(request.POST)
        try:
            rooms.post_message(request.user, room_id, form.data.get("body", ""))
        except rooms.RoomClosed:
            raise Http404
        except rooms.RoomError as error:
            messages.error(request, str(error))
        return redirect("exchange:room", room_id=room_id)


class StartSessionView(LoginRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, room_id):
        room = rooms.room_for(request.user, room_id)
        if room is None:
            raise Http404
        form = StartSessionForm(request.POST, room=room)
        if not form.is_valid():
            messages.error(request, "Choose a starting language and a length.")
            return redirect("exchange:room", room_id=room_id)
        try:
            rooms.start_session(request.user, room_id, first_language_id=form.cleaned_data["first_language"],
                                minutes=form.cleaned_data["minutes"])
        except rooms.RoomError as error:
            messages.error(request, str(error))
        return redirect("exchange:room", room_id=room_id)


class EndSessionView(LoginRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, room_id):
        try:
            session = rooms.end_session(request.user, room_id)
        except rooms.RoomClosed:
            raise Http404
        except rooms.RoomError as error:
            messages.error(request, str(error))
        else:
            minutes = round((session.ended_at - session.started_at).total_seconds() / 60)
            messages.success(request, f"Session ended after {minutes} minute{'s' if minutes != 1 else ''}.")
            return redirect("feedback:session", session_id=session.pk)
        return redirect("exchange:room", room_id=room_id)
