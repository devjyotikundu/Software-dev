from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import TemplateView

from . import services
from .models import Notification


class NotificationListView(LoginRequiredMixin, TemplateView):
    template_name = "notifications/list.html"

    def get_context_data(self, **kwargs):
        notes = (Notification.objects.filter(recipient=self.request.user)
                 .select_related("actor__profile")[: services._setting("PAGE_SIZE")])
        return super().get_context_data(**kwargs, notes=notes)


class OpenNotificationView(LoginRequiredMixin, View):
    """Mark as read, then go to the notification's page (site-relative links only)."""

    def get(self, request, pk):
        note = get_object_or_404(Notification, pk=pk, recipient=request.user)
        services.mark_read(note)
        return redirect(services.safe_link(note.link) or "notifications:list")


class MarkAllReadView(LoginRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request):
        services.mark_all_read(request.user)
        return redirect("notifications:list")
