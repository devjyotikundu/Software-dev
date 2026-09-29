from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("", views.NotificationListView.as_view(), name="list"),
    path("<int:pk>/open/", views.OpenNotificationView.as_view(), name="open"),
    path("read-all/", views.MarkAllReadView.as_view(), name="read_all"),
]
