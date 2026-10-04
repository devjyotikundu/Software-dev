from django import forms

from apps.accounts.models import Report
from apps.core.forms import BootstrapFormMixin

from .services.config import matching_setting


class RequestForm(BootstrapFormMixin, forms.Form):
    message = forms.CharField(
        required=False, label="Add a note (optional)",
        max_length=matching_setting("REQUEST_MESSAGE_MAX"),
        widget=forms.Textarea(attrs={"rows": 3, "maxlength": matching_setting("REQUEST_MESSAGE_MAX"),
                                     "placeholder": "Hi! I'd love to practise English with you and help with Bengali."}),
        help_text="Say hello and what you'd like to practise.",
    )


class ReportForm(BootstrapFormMixin, forms.Form):
    reason = forms.ChoiceField(choices=Report.Reason.choices, widget=forms.RadioSelect, label="What's wrong?")
    details = forms.CharField(
        required=False, label="Details (optional)", max_length=2000,
        widget=forms.Textarea(attrs={"rows": 4, "maxlength": 2000}),
        help_text="Only our moderators see this. The person isn't told who reported them.",
    )
    also_block = forms.BooleanField(required=False, initial=True, label="Also block this person")
