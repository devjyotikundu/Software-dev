from django import forms
from .models import Language, LearningProfile


class ProfileSetupForm(forms.ModelForm):
    language = forms.ModelChoiceField(queryset=Language.objects.all(), empty_label='Select a language')

    class Meta:
        model = LearningProfile
        fields = ['language', 'proficiency']
