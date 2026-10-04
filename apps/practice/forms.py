from django import forms

from .models import AnswerOption


class StartForm(forms.Form):
    language = forms.CharField(max_length=10)


class AnswerForm(forms.Form):
    """Only the question id and the chosen letter are accepted from the browser.

    XP, correctness and anything else are decided on the server.
    """

    answer_id = forms.IntegerField(widget=forms.HiddenInput)
    option = forms.ChoiceField(
        choices=AnswerOption.choices, widget=forms.RadioSelect,
        error_messages={"required": "Choose an answer first."},
    )
