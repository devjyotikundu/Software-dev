from django.urls import path

from . import views

app_name = "ai"

urlpatterns = [
    path("rooms/<int:room_id>/assist/", views.AssistView.as_view(), name="assist"),
    path("sessions/<int:session_id>/summary/", views.SessionSummaryView.as_view(), name="summary"),
]
