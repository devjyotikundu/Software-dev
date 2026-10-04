from django.urls import path

from . import views, views_partners

app_name = "matching"

urlpatterns = [
    path("", views.DiscoverView.as_view(), name="discover"),
    path("<int:user_id>/", views.MatchDetailView.as_view(), name="detail"),
    path("<int:user_id>/request/", views_partners.SendRequestView.as_view(), name="request"),
]
