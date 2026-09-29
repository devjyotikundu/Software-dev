from django.urls import path

from . import views

app_name = "feedback"

urlpatterns = [
    path("session/<int:session_id>/", views.SessionFeedbackView.as_view(), name="session"),
]
