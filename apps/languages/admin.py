from django.contrib import admin

from .models import Language, ProficiencyLevel


@admin.register(Language)
class LanguageAdmin(admin.ModelAdmin):
    list_display = ("name", "native_name", "code", "is_active", "sort_order")
    list_editable = ("is_active", "sort_order")
    search_fields = ("name", "native_name", "code")


@admin.register(ProficiencyLevel)
class ProficiencyLevelAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "rank")
    ordering = ("rank",)
