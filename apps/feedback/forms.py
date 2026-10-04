from django import forms

from apps.core.forms import BootstrapFormMixin

from .models import SessionFeedback


class FeedbackForm(BootstrapFormMixin, forms.Form):
    usefulness = forms.TypedChoiceField(
        coerce=int, widget=forms.RadioSelect, label="How useful was the exchange?",
        choices=[(1, "1, not useful"), (2, "2"), (3, "3, okay"), (4, "4"), (5, "5, very useful")],
        error_messages={"required": "Choose a rating from 1 to 5."},
    )
    would_practice_again = forms.TypedChoiceField(
        coerce=lambda v: v == "yes", widget=forms.RadioSelect, label="Would you practise with them again?",
        choices=[("yes", "Yes"), ("no", "No")],
        help_text="Private. If you say no, we won't suggest you to each other again.",
        error_messages={"required": "Choose yes or no."},
    )
    difficulty = forms.ChoiceField(
        choices=SessionFeedback.Difficulty.choices, widget=forms.RadioSelect,
        label="Was the difficulty comfortable?", error_messages={"required": "Choose one."},
    )
    comment = forms.CharField(
        required=False, max_length=1000, label="Anything else? (optional)",
        widget=forms.Textarea(attrs={"rows": 3, "maxlength": 1000}),
        help_text="Only our team sees comments. Your partner never sees your answers.",
    )
