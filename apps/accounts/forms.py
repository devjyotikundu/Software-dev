from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.forms import (
    AuthenticationForm, PasswordChangeForm, PasswordResetForm, SetPasswordForm,
)

from apps.core.forms import BootstrapFormMixin


class RegistrationForm(BootstrapFormMixin, forms.Form):
    display_name = forms.CharField(
        max_length=50, label="Your name",
        help_text="Shown to partners. You can use a first name only.",
        widget=forms.TextInput(attrs={"autocomplete": "name"}),
        error_messages={"required": "Enter the name partners will see."},
    )
    email = forms.EmailField(widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    password1 = forms.CharField(
        label="Password", strip=False,
        help_text="At least 10 characters. Avoid common passwords.",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="Confirm password", strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def clean_display_name(self):
        name = self.cleaned_data["display_name"].strip()
        if not name:
            raise forms.ValidationError("Enter the name partners will see.")
        return name

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if get_user_model().objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "An account with this email already exists. Log in instead."
            )
        return email

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "The two passwords don't match.")
        elif p1:
            candidate = get_user_model()(email=cleaned.get("email", ""))
            try:
                password_validation.validate_password(p1, candidate)
            except forms.ValidationError as error:
                self.add_error("password1", error)
        return cleaned


class EmailLoginForm(BootstrapFormMixin, AuthenticationForm):
    username = forms.EmailField(
        label="Email", widget=forms.EmailInput(attrs={"autocomplete": "email", "autofocus": True})
    )
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Email or password is incorrect. Passwords are case-sensitive.",
    }


class StyledPasswordChangeForm(BootstrapFormMixin, PasswordChangeForm):
    pass


class StyledPasswordResetForm(BootstrapFormMixin, PasswordResetForm):
    pass


class StyledSetPasswordForm(BootstrapFormMixin, SetPasswordForm):
    pass
