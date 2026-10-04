"""Forms for onboarding (Phase 3) and profile editing (Phase 4).

Onboarding forms know how to load from and save to a profile, so the profile
pages reuse them for goals, interests and practice style.
"""
import zoneinfo
from datetime import time

from django import forms
from django.db import transaction
from django.forms import BaseInlineFormSet, inlineformset_factory

from apps.core.forms import BootstrapFormMixin
from apps.languages.models import Language, ProficiencyLevel

from .models import (
    AvailabilitySlot, CommunicationMode, Interest, LearningGoal, Profile, UserLanguage,
)
from .services import (
    AVATAR_MAX_BYTES, MAX_LANGUAGES_PER_ROLE, language_limits_reached, process_avatar,
)

# Broad times of day offered during onboarding. Exact ranges can be edited
# on the profile page later (Phase 4). Night ends at 23:59 because a slot
# must end on the same day it starts.
TIME_BLOCKS = {
    "morning": ("Morning", "6:00–12:00", time(6), time(12)),
    "afternoon": ("Afternoon", "12:00–17:00", time(12), time(17)),
    "evening": ("Evening", "17:00–21:00", time(17), time(21)),
    "night": ("Night", "21:00–24:00", time(21), time(23, 59)),
}

TIMEZONE_CHOICES = [(tz, tz.replace("_", " ")) for tz in sorted(zoneinfo.available_timezones())]


class LevelChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, level):
        return level.name  # the template shows the code as a badge


class OnboardingForm(BootstrapFormMixin, forms.Form):
    """Base: subclasses implement initial_for() and save()."""

    @classmethod
    def initial_for(cls, profile):
        return {}

    def save(self, profile):
        raise NotImplementedError


class LanguagesForm(OnboardingForm):
    native_language = forms.ModelChoiceField(
        queryset=Language.objects.active(), label="Language you speak natively",
        empty_label="Choose a language",
    )
    learning_language = forms.ModelChoiceField(
        queryset=Language.objects.active(), label="Language you want to learn",
        empty_label="Choose a language",
    )
    level = LevelChoiceField(
        queryset=ProficiencyLevel.objects.all(), widget=forms.RadioSelect,
        label="Your level in that language", empty_label=None,
        help_text="Your best guess is fine. Practice results will refine this estimate.",
    )

    @classmethod
    def initial_for(cls, profile):
        rows = {ul.role: ul for ul in profile.user.languages.all()}
        initial = {}
        if "native" in rows:
            initial["native_language"] = rows["native"].language_id
        if "learning" in rows:
            initial["learning_language"] = rows["learning"].language_id
            initial["level"] = rows["learning"].self_declared_level_id
        return initial

    def clean(self):
        cleaned = super().clean()
        native, learning = cleaned.get("native_language"), cleaned.get("learning_language")
        if native and learning and native == learning:
            self.add_error(
                "learning_language", "Choose a language different from the one you speak."
            )
        return cleaned

    @transaction.atomic
    def save(self, profile):
        # Onboarding sets exactly one of each. Adding more comes with Phase 4.
        user = profile.user
        UserLanguage.objects.filter(user=user).delete()
        UserLanguage.objects.bulk_create([
            UserLanguage(user=user, language=self.cleaned_data["native_language"],
                         role=UserLanguage.Role.NATIVE),
            UserLanguage(user=user, language=self.cleaned_data["learning_language"],
                         role=UserLanguage.Role.LEARNING,
                         self_declared_level=self.cleaned_data["level"]),
        ])


class GoalsForm(OnboardingForm):
    goals = forms.ModelMultipleChoiceField(
        queryset=LearningGoal.objects.filter(is_active=True),
        widget=forms.CheckboxSelectMultiple, label="What do you want to work on?",
        help_text="Choose all that apply.",
        error_messages={"required": "Choose at least one goal."},
    )

    @classmethod
    def initial_for(cls, profile):
        return {"goals": list(profile.goals.values_list("pk", flat=True))}

    def save(self, profile):
        profile.goals.set(self.cleaned_data["goals"])


class InterestsForm(OnboardingForm):
    interests = forms.ModelMultipleChoiceField(
        queryset=Interest.objects.filter(is_active=True),
        widget=forms.CheckboxSelectMultiple, label="What do you like talking about?",
        help_text="Shared interests make conversations easier.",
        error_messages={"required": "Choose at least one interest."},
    )

    @classmethod
    def initial_for(cls, profile):
        return {"interests": list(profile.interests.values_list("pk", flat=True))}

    def save(self, profile):
        profile.interests.set(self.cleaned_data["interests"])


class AvailabilityForm(OnboardingForm):
    timezone = forms.ChoiceField(
        choices=TIMEZONE_CHOICES, label="Your time zone",
        widget=forms.Select(attrs={"data-detect-timezone": "true"}),
    )
    days = forms.TypedMultipleChoiceField(
        choices=AvailabilitySlot.Weekday.choices, coerce=int,
        widget=forms.CheckboxSelectMultiple, label="Days you can usually practise",
        error_messages={"required": "Choose at least one day."},
    )
    times = forms.MultipleChoiceField(
        choices=[(key, f"{label} ({span})") for key, (label, span, _, _) in TIME_BLOCKS.items()],
        widget=forms.CheckboxSelectMultiple, label="Times of day",
        error_messages={"required": "Choose at least one time of day."},
    )

    @classmethod
    def initial_for(cls, profile):
        slots = list(profile.availability_slots.all())
        block_by_range = {(s, e): key for key, (_, _, s, e) in TIME_BLOCKS.items()}
        return {
            "timezone": profile.timezone,
            "days": sorted({slot.weekday for slot in slots}),
            "times": sorted({
                block_by_range[(slot.start_time, slot.end_time)]
                for slot in slots if (slot.start_time, slot.end_time) in block_by_range
            }),
        }

    @transaction.atomic
    def save(self, profile):
        profile.timezone = self.cleaned_data["timezone"]
        profile.save(update_fields=["timezone", "updated_at"])
        profile.availability_slots.all().delete()
        AvailabilitySlot.objects.bulk_create([
            AvailabilitySlot(
                profile=profile, weekday=day,
                start_time=TIME_BLOCKS[key][2], end_time=TIME_BLOCKS[key][3],
            )
            for day in self.cleaned_data["days"]
            for key in self.cleaned_data["times"]
        ])


class CommunicationForm(OnboardingForm):
    communication_modes = forms.ModelMultipleChoiceField(
        queryset=CommunicationMode.objects.filter(is_active=True),
        widget=forms.CheckboxSelectMultiple, label="How would you like to practise?",
        help_text="Text chat is available first; voice and video help us find partners who share your preference.",
        error_messages={"required": "Choose at least one."},
    )

    @classmethod
    def initial_for(cls, profile):
        return {"communication_modes": list(profile.communication_modes.values_list("pk", flat=True))}

    def save(self, profile):
        profile.communication_modes.set(self.cleaned_data["communication_modes"])


# ======================================================================
# Profile editing (Phase 4)
# ======================================================================


class AboutForm(BootstrapFormMixin, forms.ModelForm):
    avatar_upload = forms.ImageField(
        required=False, label="Profile photo",
        help_text="JPEG, PNG or WebP, up to 2 MB. We crop it to a square and remove location data.",
        widget=forms.FileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}),
    )
    remove_avatar = forms.BooleanField(required=False, label="Remove current photo")

    class Meta:
        model = Profile
        fields = ["display_name", "bio"]
        labels = {"display_name": "Name shown to partners", "bio": "About you"}
        help_texts = {"bio": "A few lines partners see on your profile. Up to 500 characters."}
        widgets = {"bio": forms.Textarea(attrs={"rows": 4, "maxlength": 500})}
        # Spaces are stripped before validation, so "   " arrives as empty and
        # fails as "required"; give that case the same clear message.
        error_messages = {"display_name": {"required": "Enter the name partners will see."}}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.avatar:
            del self.fields["remove_avatar"]

    def clean_display_name(self):
        name = self.cleaned_data["display_name"].strip()
        if not name:
            raise forms.ValidationError("Enter the name partners will see.")
        return name

    def clean_avatar_upload(self):
        upload = self.cleaned_data.get("avatar_upload")
        if not upload:
            return None
        if upload.size > AVATAR_MAX_BYTES:
            raise forms.ValidationError("Choose an image smaller than 2 MB.")
        return process_avatar(upload)


class AddLanguageForm(BootstrapFormMixin, forms.Form):
    language = forms.ModelChoiceField(queryset=Language.objects.none(), empty_label="Choose a language")
    role = forms.ChoiceField(
        choices=UserLanguage.Role.choices, widget=forms.RadioSelect, label="I…",
        initial=UserLanguage.Role.LEARNING,
    )
    level = LevelChoiceField(
        queryset=ProficiencyLevel.objects.all(), required=False,
        label="Your level (for a language you're learning)", empty_label="Choose a level",
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        taken = user.languages.values_list("language_id", flat=True)
        self.fields["language"].queryset = Language.objects.active().exclude(pk__in=taken)
        self.fields["role"].choices = [("native", "speak it natively"), ("learning", "am learning it")]

    def clean(self):
        cleaned = super().clean()
        role, level = cleaned.get("role"), cleaned.get("level")
        if role == UserLanguage.Role.LEARNING and not level:
            self.add_error("level", "Choose your level for a language you're learning.")
        if role and language_limits_reached(self.user).get(role):
            label = "native" if role == UserLanguage.Role.NATIVE else "learning"
            raise forms.ValidationError(
                f"You can have up to {MAX_LANGUAGES_PER_ROLE} {label} languages."
            )
        return cleaned

    def save(self):
        role = self.cleaned_data["role"]
        return UserLanguage.objects.create(
            user=self.user, language=self.cleaned_data["language"], role=role,
            self_declared_level=self.cleaned_data["level"] if role == UserLanguage.Role.LEARNING else None,
        )


class LevelForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = UserLanguage
        fields = ["self_declared_level"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["self_declared_level"] = LevelChoiceField(
            queryset=ProficiencyLevel.objects.all(), widget=forms.RadioSelect, empty_label=None,
            label="Your level",
            help_text="Your own estimate. Practice results add an assessed level alongside it.",
        )


class TimezoneForm(BootstrapFormMixin, forms.ModelForm):
    timezone = forms.ChoiceField(choices=TIMEZONE_CHOICES, label="Your time zone")

    class Meta:
        model = Profile
        fields = ["timezone"]


class SlotForm(BootstrapFormMixin, forms.ModelForm):
    weekday = forms.TypedChoiceField(
        choices=[("", "Day")] + list(AvailabilitySlot.Weekday.choices), coerce=int, label="Day",
    )

    class Meta:
        model = AvailabilitySlot
        fields = ["weekday", "start_time", "end_time"]
        labels = {"start_time": "From", "end_time": "To"}
        widgets = {
            "start_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "end_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
        }

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_time"), cleaned.get("end_time")
        if start and end and end <= start:
            self.add_error("end_time", "End time must be after the start time. For late nights, end at 23:59 and add the next day separately.")
        return cleaned


class BaseSlotFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        by_day = {}
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue
            data = form.cleaned_data
            by_day.setdefault(data["weekday"], []).append((data["start_time"], data["end_time"]))
        if not by_day:
            raise forms.ValidationError("Add at least one time when you're free.")
        names = dict(AvailabilitySlot.Weekday.choices)
        for day, ranges in by_day.items():
            ranges.sort()
            for (s1, e1), (s2, e2) in zip(ranges, ranges[1:]):
                if s2 < e1:
                    raise forms.ValidationError(
                        f"{names[day]} has overlapping times: "
                        f"{s1:%H:%M}–{e1:%H:%M} and {s2:%H:%M}–{e2:%H:%M}."
                    )


SlotFormSet = inlineformset_factory(
    Profile, AvailabilitySlot, form=SlotForm, formset=BaseSlotFormSet,
    extra=1, can_delete=True, max_num=21, validate_max=True,
)


class PrivacyForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["is_discoverable"]
        labels = {"is_discoverable": "Show me in partner suggestions"}
        help_texts = {
            "is_discoverable": "When off, nobody new can find you. Existing partners can still message you.",
        }


class DeleteAccountForm(BootstrapFormMixin, forms.Form):
    password = forms.CharField(
        label="Your password", strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_password(self):
        password = self.cleaned_data["password"]
        if not self.user.check_password(password):
            raise forms.ValidationError("That password is incorrect.")
        return password
