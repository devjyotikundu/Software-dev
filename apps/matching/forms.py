from django import forms

from apps.profiles.models import CommunicationMode, LearningGoal


class DiscoverFilterForm(forms.Form):
    """Four optional filters, submitted with GET so results can be bookmarked."""

    language = forms.TypedChoiceField(required=False, coerce=int, empty_value=None, label="Language")
    goal = forms.ModelChoiceField(
        queryset=LearningGoal.objects.filter(is_active=True), required=False,
        empty_label="Any goal", label="Goal",
    )
    mode = forms.ModelChoiceField(
        queryset=CommunicationMode.objects.filter(is_active=True), required=False,
        empty_label="Any way", label="Practice style",
    )
    overlap = forms.BooleanField(required=False, label="Free when I am")

    def __init__(self, *args, learning_languages=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["language"].choices = [("", "All my languages")] + [
            (lang.pk, lang.name) for lang in learning_languages
        ]
        self.show_language = len(learning_languages) > 1
        for name in ("language", "goal", "mode"):
            self.fields[name].widget.attrs["class"] = "form-select form-select-sm"

    @property
    def is_filtered(self):
        return self.is_bound and self.is_valid() and any(self.cleaned_data.values())
