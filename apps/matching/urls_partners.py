from django.urls import path

from . import views_partners as views

app_name = "partners"

urlpatterns = [
    path("", views.PartnersView.as_view(), name="list"),
    path("<int:match_id>/", views.PartnerDetailView.as_view(), name="detail"),
    path("requests/", views.RequestsView.as_view(), name="requests"),
    path("requests/<int:pk>/", views.RequestDetailView.as_view(), name="request_detail"),
    path("requests/<int:pk>/accept/", views.RespondView.as_view(action="accept"), name="accept"),
    path("requests/<int:pk>/decline/", views.RespondView.as_view(action="decline"), name="decline"),
    path("requests/<int:pk>/cancel/", views.RespondView.as_view(action="cancel"), name="cancel"),
    path("people/<int:user_id>/block/", views.BlockView.as_view(), name="block"),
    path("people/<int:user_id>/report/", views.ReportView.as_view(), name="report"),
    path("blocked/", views.BlockedListView.as_view(), name="blocked"),
    path("blocked/<int:user_id>/unblock/", views.UnblockView.as_view(), name="unblock"),
]
