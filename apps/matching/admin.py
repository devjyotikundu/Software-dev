from django.contrib import admin

from .models import Match, MatchRequest, MatchSuggestion


@admin.register(MatchSuggestion)
class MatchSuggestionAdmin(admin.ModelAdmin):
    list_display = ("user", "candidate", "score", "computed_at")
    search_fields = ("user__username", "candidate__username")
    list_select_related = ("user", "candidate")
    readonly_fields = ("user", "candidate", "score", "breakdown", "computed_at")


@admin.register(MatchRequest)
class MatchRequestAdmin(admin.ModelAdmin):
    list_display = ("sender", "receiver", "status", "score_at_request", "created_at")
    list_filter = ("status",)
    search_fields = ("sender__username", "receiver__username")
    list_select_related = ("sender", "receiver")


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ("__str__", "status", "created_at", "ended_at")
    list_filter = ("status",)
    search_fields = ("user_a__username", "user_b__username")
    list_select_related = ("user_a", "user_b")
