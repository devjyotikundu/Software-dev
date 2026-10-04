from django import forms

from apps.core.forms import BootstrapFormMixin

from .services.config import exchange_setting


class MessageForm(forms.Form):
    body = forms.CharField(max_length=exchange_setting("MESSAGE_MAX_LENGTH"), strip=True)


class StartSessionForm(BootstrapFormMixin, forms.Form):
    first_language = forms.TypedChoiceField(coerce=int, widget=forms.RadioSelect, label="Start with")
    minutes = forms.TypedChoiceField(coerce=int, label="Minutes per language",
                                     initial=exchange_setting("DEFAULT_MINUTES"))

    def __init__(self, *args, room, **kwargs):
        super().__init__(*args, **kwargs)
        match = room.match
        self.fields["first_language"].choices = [
            (match.user_a_learning_language_id, match.user_a_learning_language.name),
            (match.user_b_learning_language_id, match.user_b_learning_language.name),
        ]
        self.fields["first_language"].initial = match.user_a_learning_language_id
        self.fields["minutes"].choices = [(m, f"{m} minutes") for m in exchange_setting("MINUTES_CHOICES")]
