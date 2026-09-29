from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.shortcuts import redirect
from django.views import View
from django.views.generic import FormView

from . import onboarding


class OnboardingStartView(LoginRequiredMixin, View):
    """Send the user to the first step they haven't completed."""

    def get(self, request):
        profile = onboarding.get_or_create_profile(request.user)
        step = onboarding.first_incomplete_step(profile)
        if step is None:
            onboarding.complete_if_finished(profile)
            return redirect("core:home")
        return redirect("onboarding:step", step=step.slug)


class OnboardingStepView(LoginRequiredMixin, FormView):
    template_name = "profiles/onboarding_step.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        self.step = onboarding.STEP_BY_SLUG.get(kwargs["step"])
        if self.step is None:
            raise Http404("Unknown onboarding step.")
        self.profile = onboarding.get_or_create_profile(request.user)
        if self.profile.is_onboarded:
            return redirect("core:home")  # editing happens on the profile page
        # Earlier steps can be revisited; later ones can't be reached early.
        first_open = onboarding.first_incomplete_step(self.profile)
        if first_open and onboarding.step_number(self.step) > onboarding.step_number(first_open):
            return redirect("onboarding:step", step=first_open.slug)
        return super().dispatch(request, *args, **kwargs)

    def get_form_class(self):
        return self.step.form_class

    def get_initial(self):
        return self.step.form_class.initial_for(self.profile)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        total = len(onboarding.STEPS)
        number = onboarding.step_number(self.step)
        stepper = [
            {"step": step, "state": "done" if i < number else "current" if i == number else "todo"}
            for i, step in enumerate(onboarding.STEPS, 1)
        ]
        context.update(
            step=self.step, step_number=number, total_steps=total, stepper=stepper,
            progress_percent=round((number - 1) / total * 100),
            previous_step=onboarding.previous_step(self.step),
            is_last_step=onboarding.next_step(self.step) is None,
        )
        return context

    def form_valid(self, form):
        form.save(self.profile)
        if onboarding.complete_if_finished(self.profile):
            return redirect("core:home")
        following = onboarding.next_step(self.step) or onboarding.first_incomplete_step(self.profile)
        return redirect("onboarding:step", step=following.slug)
