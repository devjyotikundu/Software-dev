from django.contrib import admin

from .models import ExchangeRoom, ExchangeSession, Message


@admin.register(ExchangeRoom)
class ExchangeRoomAdmin(admin.ModelAdmin):
    list_display = ("__str__", "is_active", "created_at")
    list_filter = ("is_active",)
    list_select_related = ("match__user_a", "match__user_b")


@admin.register(ExchangeSession)
class ExchangeSessionAdmin(admin.ModelAdmin):
    list_display = ("room", "status", "first_language", "second_language",
                    "minutes_per_language", "started_at", "ended_at")
    list_filter = ("status",)


# Messages are private conversations; admins see metadata only, not bodies.
@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("room", "sender", "language", "created_at")
    fields = ("room", "sender", "language", "created_at")
    readonly_fields = fields
    list_select_related = ("sender", "language")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
