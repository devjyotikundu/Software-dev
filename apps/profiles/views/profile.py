from dataclasses import dataclass

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import FormView, TemplateView

from apps.accounts.services import delete_account

from .. import forms
from ..models import UserLanguage
from ..presenters import profile_summary
from ..services import MAX_LANGUAGES_PER_ROLE, can_remove_language, remove_language, replace_avatar


class ProfileMixin(LoginRequiredMixin):
    """Every profile page acts on the signed-in user's own profile only."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            self.profile = request.user.profile
        return super().dispatch(request, *args, **kwargs)


class ProfileView(ProfileMixin, TemplateView):
    template_name = "profiles/profile.html"

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs, **profile_summary(self.profile), editable=True)


# ---------------------------------------------------------------- simple sections
@dataclass(frozen=True)
class Section:
    title: str
    intro: str
    icon: str
    form_class: type
    uses_instance: bool = False  # ModelForm on the profile vs. onboarding-style form
    success: str = "Saved."


SECTIONS = {
    "about": Section("About you", "How you appear to partners.", "person",
                     forms.AboutForm, uses_instance=True, success="Profile updated."),
    "goals": Section("Goals", "What you want to work on.", "bullseye",
                     forms.GoalsForm, success="Goals updated."),
    "interests": Section("Interests", "Topics you enjoy talking about.", "heart",
                         forms.InterestsForm, success="Interests updated."),
    "practice-style": Section("Practice style", "How you're comfortable practising.", "chat-dots",
                              forms.CommunicationForm, success="Practice style updated."),
    "privacy": Section("Privacy", "Control who can find you.", "shield-lock",
                       forms.PrivacyForm, uses_instance=True, success="Privacy settings updated."),
}


class SectionEditView(ProfileMixin, FormView):
    template_name = "profiles/edit_section.html"

    def dispatch(self, request, *args, **kwargs):
        self.section = SECTIONS.get(kwargs["section"])
        if self.section is None:
            raise Http404("Unknown profile section.")
        return super().dispatch(request, *args, **kwargs)

    def get_form_class(self):
        return self.section.form_class

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.section.uses_instance:
            kwargs["instance"] = self.profile
        return kwargs

    def get_initial(self):
        if self.section.uses_instance:
            return {}
        return self.section.form_class.initial_for(self.profile)

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            **kwargs, section=self.section, slug=self.kwargs["section"], profile=self.profile
        )

    @transaction.atomic
    def form_valid(self, form):
        if isinstance(form, forms.AboutForm):
            form.save()
            replace_avatar(
                self.profile, form.cleaned_data.get("avatar_upload"),
                remove=form.cleaned_data.get("remove_avatar", False),
            )
        elif self.section.uses_instance:
            form.save()
        else:
            form.save(self.profile)
        messages.success(self.request, self.section.success)
        return redirect("profiles:detail")


# ---------------------------------------------------------------- languages
class LanguagesView(ProfileMixin, FormView):
    template_name = "profiles/languages.html"
    form_class = forms.AddLanguageForm

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "user": self.request.user}

    def get_context_data(self, **kwargs):
        form = kwargs.setdefault("form", self.get_form())
        rows = list(
            self.request.user.languages.select_related(
                "language", "self_declared_level", "assessed_level"
            ).order_by("-role", "language__sort_order")
        )
        items = [{"row": row, "removable": can_remove_language(row)} for row in rows]
        return super().get_context_data(
            **kwargs, items=items, max_per_role=MAX_LANGUAGES_PER_ROLE,
            can_add=form.fields["language"].queryset.exists(),
        )

    def form_valid(self, form):
        added = form.save()
        messages.success(self.request, f"{added.language.name} added.")
        return redirect("profiles:languages")


class LanguageLevelView(ProfileMixin, FormView):
    template_name = "profiles/edit_section.html"
    form_class = forms.LevelForm

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            # Scoped to the signed-in user: other people's rows are a 404.
            self.row = get_object_or_404(
                UserLanguage.objects.select_related("language"),
                pk=kwargs["pk"], user=request.user, role=UserLanguage.Role.LEARNING,
            )
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "instance": self.row}

    def get_context_data(self, **kwargs):
        section = Section(f"Your level in {self.row.language.name}",
                          "Update this as you improve.", "bar-chart", forms.LevelForm)
        return super().get_context_data(**kwargs, section=section, back_url_name="profiles:languages")

    def form_valid(self, form):
        form.save()
        messages.success(self.request, f"Level for {self.row.language.name} updated.")
        return redirect("profiles:languages")


class LanguageRemoveView(ProfileMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        row = get_object_or_404(UserLanguage.objects.select_related("language"),
                                pk=pk, user=request.user)
        try:
            remove_language(row)
        except ValidationError as error:
            messages.error(request, error.messages[0])
        else:
            messages.success(request, f"{row.language.name} removed.")
        return redirect("profiles:languages")


# ---------------------------------------------------------------- availability
class AvailabilityView(ProfileMixin, TemplateView):
    template_name = "profiles/availability.html"

    def get_forms(self):
        data = self.request.POST if self.request.method == "POST" else None
        return (
            forms.TimezoneForm(data, instance=self.profile, prefix="tz"),
            forms.SlotFormSet(data, instance=self.profile, prefix="slots"),
        )

    def get(self, request, *args, **kwargs):
        timezone_form, formset = self.get_forms()
        return self.render_to_response(
            self.get_context_data(timezone_form=timezone_form, formset=formset)
        )

    def post(self, request, *args, **kwargs):
        timezone_form, formset = self.get_forms()
        if timezone_form.is_valid() and formset.is_valid():
            with transaction.atomic():
                timezone_form.save()
                formset.save()
            messages.success(request, "Availability updated.")
            return redirect("profiles:detail")
        return self.render_to_response(
            self.get_context_data(timezone_form=timezone_form, formset=formset)
        )


# ---------------------------------------------------------------- account deletion
class DeleteAccountView(ProfileMixin, FormView):
    template_name = "profiles/delete_account.html"
    form_class = forms.DeleteAccountForm

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "user": self.request.user}

    def form_valid(self, form):
        user = self.request.user
        logout(self.request)
        delete_account(user)
        messages.success(self.request, "Your account and profile have been deleted.")
        return redirect("core:home")
