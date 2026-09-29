from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import BlockedUser, Report, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    pass


@admin.register(BlockedUser)
class BlockedUserAdmin(admin.ModelAdmin):
    list_display = ("blocker", "blocked", "created_at")
    search_fields = ("blocker__username", "blocked__username")
    list_select_related = ("blocker", "blocked")


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("__str__", "reporter", "reported", "status", "created_at")
    list_filter = ("status", "reason")
    search_fields = ("reporter__username", "reported__username", "details")
    list_select_related = ("reporter", "reported")
    readonly_fields = ("reporter", "reported", "reason", "details", "created_at")
