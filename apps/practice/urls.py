from django.urls import path

from . import views

app_name = "practice"

urlpatterns = [
    path("", views.PracticeHomeView.as_view(), name="home"),
    path("start/", views.StartSessionView.as_view(), name="start"),
    path("session/<int:pk>/", views.SessionView.as_view(), name="session"),
    path("session/<int:pk>/answer/", views.AnswerView.as_view(), name="answer"),
    path("session/<int:pk>/question/<int:position>/", views.FeedbackView.as_view(), name="feedback"),
    path("session/<int:pk>/results/", views.ResultsView.as_view(), name="results"),
    path("session/<int:pk>/quit/", views.QuitView.as_view(), name="quit"),
]
