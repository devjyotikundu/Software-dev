from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import FormView
from django.utils.decorators import method_decorator

from apps.core.ratelimit import rate_limited

from .forms import (
    EmailLoginForm, RegistrationForm, StyledPasswordChangeForm,
    StyledPasswordResetForm, StyledSetPasswordForm,
)
from .services import register_user

BACKEND = "apps.accounts.backends.EmailOrUsernameBackend"


@method_decorator(rate_limited("register", redirect_to="accounts:register", message="Too many sign-ups from your network. Try again in an hour."), name="post")
class RegisterView(FormView):
    template_name = "accounts/register.html"
    form_class = RegistrationForm

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("core:home")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        data = form.cleaned_data
        user = register_user(
            email=data["email"], password=data["password1"], display_name=data["display_name"]
        )
        login(self.request, user, backend=BACKEND)
        return redirect("onboarding:start")


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    authentication_form = EmailLoginForm
    redirect_authenticated_user = True


class LogoutView(auth_views.LogoutView):
    """POST only (Django's default), so a link or image can't sign people out."""


class PasswordChangeView(auth_views.PasswordChangeView):
    template_name = "accounts/password_change.html"
    form_class = StyledPasswordChangeForm
    success_url = reverse_lazy("accounts:password_change_done")


class PasswordChangeDoneView(auth_views.PasswordChangeDoneView):
    template_name = "accounts/password_change_done.html"


@method_decorator(rate_limited("password_reset", redirect_to="accounts:password_reset", message="Too many reset requests. Try again in an hour."), name="post")
class PasswordResetView(auth_views.PasswordResetView):
    """Always shows the same confirmation, so it never reveals whether an email is registered."""

    template_name = "accounts/password_reset.html"
    form_class = StyledPasswordResetForm
    email_template_name = "accounts/email/password_reset.txt"
    subject_template_name = "accounts/email/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:password_reset_done")


class PasswordResetDoneView(auth_views.PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    form_class = StyledSetPasswordForm
    success_url = reverse_lazy("accounts:password_reset_complete")


class PasswordResetCompleteView(auth_views.PasswordResetCompleteView):
    template_name = "accounts/password_reset_complete.html"
