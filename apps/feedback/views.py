from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.shortcuts import redirect
from django.views.generic import FormView

from apps.ai_services.client import is_enabled as ai_enabled

from . import services
from .forms import FeedbackForm


class SessionFeedbackView(LoginRequiredMixin, FormView):
    """Feedback for one finished session. Only its two partners can open it."""

    template_name = "feedback/session_feedback.html"
    form_class = FeedbackForm

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            self.session = services.session_for_feedback(request.user, kwargs["session_id"])
            if self.session is None:
                raise Http404("Session not found.")
            if services.already_given(self.session, request.user):
                messages.info(request, "You've already given feedback for this session. Thank you!")
                return redirect("exchange:room", room_id=self.session.room_id)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            **kwargs, session=self.session, partner=services.partner_in(self.session, self.request.user),
            summary=services.summary(self.session), ai_enabled=ai_enabled(),
        )

    def form_valid(self, form):
        try:
            services.submit_feedback(self.request.user, self.session, **form.cleaned_data)
        except services.FeedbackError as error:
            messages.error(self.request, str(error))
        else:
            messages.success(self.request, "Thanks! Your feedback helps us suggest better partners.")
        return redirect("exchange:room", room_id=self.session.room_id)
