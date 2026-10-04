from django.contrib import admin

from .models import SessionFeedback


@admin.register(SessionFeedback)
class SessionFeedbackAdmin(admin.ModelAdmin):
    list_display = ("reviewee", "reviewer", "usefulness", "would_practice_again",
                    "difficulty", "created_at")
    list_filter = ("usefulness", "would_practice_again", "difficulty")
    search_fields = ("reviewer__username", "reviewee__username")
    list_select_related = ("reviewer", "reviewee")
