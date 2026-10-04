from django.contrib import admin

from .models import (
    AvailabilitySlot, CommunicationMode, Interest, LearningGoal, Profile, UserLanguage,
)


@admin.register(LearningGoal, Interest, CommunicationMode)
class ReferenceItemAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "sort_order")
    list_editable = ("is_active", "sort_order")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)


class AvailabilitySlotInline(admin.TabularInline):
    model = AvailabilitySlot
    extra = 0


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("display_name", "user", "is_discoverable", "onboarding_completed_at")
    list_filter = ("is_discoverable",)
    search_fields = ("display_name", "user__username", "user__email")
    list_select_related = ("user",)
    filter_horizontal = ("goals", "interests", "communication_modes")
    inlines = [AvailabilitySlotInline]


@admin.register(UserLanguage)
class UserLanguageAdmin(admin.ModelAdmin):
    list_display = ("user", "language", "role", "self_declared_level", "assessed_level", "assessment_confidence")
    list_filter = ("role", "language")
    search_fields = ("user__username",)
    list_select_related = ("user", "language", "self_declared_level", "assessed_level")
    readonly_fields = ("assessed_level", "assessment_confidence", "assessed_at")
