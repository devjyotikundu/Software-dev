"""Requests, partners, blocking and reporting pages.

Every view acts only for the signed-in user: someone else's request, match
or a person you've never come across returns 404.
"""
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import FormView, TemplateView
from django.utils.decorators import method_decorator

from apps.core.ratelimit import rate_limited
from apps.accounts.models import BlockedUser

from .forms_partners import ReportForm, RequestForm
from .models import Match, MatchRequest
from .presenters import live_card
from .services import requests as req
from .services import safety

User = get_user_model()


def _other(match, user):
    return match.user_b if match.user_a_id == user.pk else match.user_a


# -------------------------------------------------------------------- send
@method_decorator(rate_limited("match_request", by="user", redirect_to="matching:discover", message="You've sent a lot of requests. Try again later."), name="post")
class SendRequestView(LoginRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, user_id):
        receiver = get_object_or_404(User, pk=user_id, is_active=True)
        form = RequestForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Keep your note under 300 characters.")
            return redirect("matching:detail", user_id=user_id)
        try:
            result = req.send_request(request.user, receiver, form.cleaned_data["message"])
        except req.RequestError as error:
            messages.error(request, str(error))
            return redirect("matching:discover")
        if result.matched:
            messages.success(request, f"You and {receiver.profile.display_name} are now partners.")
            return redirect("partners:detail", match_id=result.match.pk)
        messages.success(request, f"Request sent to {receiver.profile.display_name}.")
        return redirect("partners:requests")


# ---------------------------------------------------------------- requests
class RequestsView(LoginRequiredMixin, TemplateView):
    template_name = "partners/requests.html"

    def get_context_data(self, **kwargs):
        user = self.request.user
        pending = MatchRequest.objects.filter(status=MatchRequest.Status.PENDING).select_related(
            "sender__profile", "receiver__profile", "sender_learning_language", "receiver_learning_language")
        return super().get_context_data(
            **kwargs,
            received=pending.filter(receiver=user).order_by("-created_at"),
            sent=pending.filter(sender=user).order_by("-created_at"),
        )


class RequestDetailView(LoginRequiredMixin, TemplateView):
    template_name = "partners/request_detail.html"

    def get_context_data(self, **kwargs):
        user = self.request.user
        match_request = get_object_or_404(
            MatchRequest.objects.select_related("sender__profile", "receiver__profile"),
            Q(sender=user) | Q(receiver=user), pk=kwargs["pk"],
        )
        incoming = match_request.receiver_id == user.pk
        other = match_request.sender if incoming else match_request.receiver
        card, factors = live_card(user, other)
        if card is None:
            raise Http404("This request is no longer available.")
        return super().get_context_data(**kwargs, match_request=match_request, incoming=incoming,
                                        other=other, card=card, factors=factors)


class RespondView(LoginRequiredMixin, View):
    """Accept, decline or cancel. Which one is fixed by the URL, never by form data."""

    http_method_names = ["post"]
    action = None

    def post(self, request, pk):
        user = request.user
        match_request = get_object_or_404(MatchRequest, Q(sender=user) | Q(receiver=user), pk=pk)
        try:
            if self.action == "accept":
                match = req.accept_request(match_request, user)
                messages.success(request, f"You and {match_request.sender.profile.display_name} are now partners.")
                return redirect("partners:detail", match_id=match.pk)
            if self.action == "decline":
                req.decline_request(match_request, user)
                messages.info(request, "Request declined. They won't be told why.")
            else:
                req.cancel_request(match_request, user)
                messages.info(request, "Request withdrawn.")
        except req.RequestError as error:
            messages.error(request, str(error))
        return redirect("partners:requests")


# ---------------------------------------------------------------- partners
class PartnersView(LoginRequiredMixin, TemplateView):
    template_name = "partners/list.html"

    def get_context_data(self, **kwargs):
        user = self.request.user
        matches = Match.objects.filter(Q(user_a=user) | Q(user_b=user), status=Match.Status.ACTIVE).select_related(
            "user_a__profile", "user_b__profile", "user_a_learning_language", "user_b_learning_language", "room",
        ).order_by("-created_at")
        partners = []
        for match in matches:
            mine_is_a = match.user_a_id == user.pk
            partners.append({
                "match": match, "other": _other(match, user),
                "you_learn": match.user_a_learning_language if mine_is_a else match.user_b_learning_language,
                "they_learn": match.user_b_learning_language if mine_is_a else match.user_a_learning_language,
            })
        return super().get_context_data(**kwargs, partners=partners)


class PartnerDetailView(LoginRequiredMixin, TemplateView):
    template_name = "partners/detail.html"

    def get_context_data(self, **kwargs):
        user = self.request.user
        match = get_object_or_404(
            Match.objects.select_related("user_a__profile", "user_b__profile", "room"),
            Q(user_a=user) | Q(user_b=user), pk=kwargs["match_id"], status=Match.Status.ACTIVE,
        )
        other = _other(match, user)
        card, factors = live_card(user, other)
        return super().get_context_data(**kwargs, match=match, other=other, card=card, factors=factors)


# ------------------------------------------------------------------ safety
class PersonMixin(LoginRequiredMixin):
    def get_person(self):
        person = get_object_or_404(User.objects.select_related("profile"), pk=self.kwargs["user_id"])
        if not safety.has_relationship(self.request.user, person):
            raise Http404
        return person


class BlockView(PersonMixin, TemplateView):
    template_name = "partners/block.html"

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs, person=self.get_person())

    def post(self, request, user_id):
        person = self.get_person()
        safety.block_user(request.user, person)
        messages.success(request, f"{person.profile.display_name} is blocked. You won't see each other anywhere.")
        return redirect("partners:blocked")


@method_decorator(rate_limited("report", by="user", message="You've sent a lot of reports today. Our moderators will review them."), name="post")
class ReportView(PersonMixin, FormView):
    template_name = "partners/report.html"
    form_class = ReportForm

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs, person=self.get_person())

    def form_valid(self, form):
        person = self.get_person()
        data = form.cleaned_data
        safety.report_user(self.request.user, person, data["reason"], data["details"], also_block=data["also_block"])
        messages.success(self.request, "Thanks for telling us. A moderator will review your report.")
        return redirect("partners:blocked" if data["also_block"] else "matching:discover")


class BlockedListView(LoginRequiredMixin, TemplateView):
    template_name = "partners/blocked.html"

    def get_context_data(self, **kwargs):
        blocked = BlockedUser.objects.filter(blocker=self.request.user).select_related("blocked__profile").order_by("-created_at")
        return super().get_context_data(**kwargs, blocked=blocked)


class UnblockView(LoginRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, user_id):
        person = get_object_or_404(User, pk=user_id)
        if safety.unblock_user(request.user, person):
            messages.info(request, "Unblocked. They may appear in suggestions again.")
        return redirect("partners:blocked")
