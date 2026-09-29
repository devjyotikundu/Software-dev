from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.http import Http404
from django.views.generic import TemplateView

from apps.practice.services.sessions import learning_languages

from .forms import DiscoverFilterForm
from .forms_partners import RequestForm
from .presenters import apply_filters, cards_for, factor_rows
from .services.suggestions import get_suggestions

PAGE_SIZE = 12


class DiscoverView(LoginRequiredMixin, TemplateView):
    template_name = "matching/discover.html"

    def get_context_data(self, **kwargs):
        user = self.request.user
        form = DiscoverFilterForm(self.request.GET or None, learning_languages=learning_languages(user))
        cards = cards_for(get_suggestions(user))
        total = len(cards)
        if form.is_bound and form.is_valid():
            data = form.cleaned_data
            cards = apply_filters(
                cards, language=data["language"],
                goal=data["goal"].pk if data["goal"] else None,
                mode=data["mode"].pk if data["mode"] else None,
                overlap_only=data["overlap"],
            )
        page = Paginator(cards, PAGE_SIZE).get_page(self.request.GET.get("page"))
        query = self.request.GET.copy()
        query.pop("page", None)
        return super().get_context_data(
            **kwargs, form=form, page=page, total=total, shown=len(cards),
            profile=user.profile, filter_query=query.urlencode(),
        )


class MatchDetailView(LoginRequiredMixin, TemplateView):
    """One suggested partner and "Why this match?".

    Only people currently suggested to the viewer can be opened: anyone else,
    including blocked or hidden users, is a 404.
    """

    template_name = "matching/detail.html"

    def get_context_data(self, **kwargs):
        user = self.request.user
        valid = {s.candidate_id: s for s in get_suggestions(user)}
        suggestion = valid.get(kwargs["user_id"])
        if suggestion is None:
            raise Http404("This person isn't one of your suggestions.")
        card, = cards_for([suggestion])
        rank = sorted(valid.values(), key=lambda s: (-s.score, s.candidate_id)).index(suggestion) + 1
        return super().get_context_data(
            **kwargs, card=card, factors=factor_rows(suggestion.breakdown), rank=rank,
            total=len(valid), computed_at=suggestion.computed_at, request_form=RequestForm(),
        )


def top_suggestions(user, count=2):
    """For the dashboard: the best few partner cards."""
    return cards_for(get_suggestions(user)[:count])
