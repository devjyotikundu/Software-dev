from django.urls import path

from .views import profile as views

app_name = "profiles"

urlpatterns = [
    path("", views.ProfileView.as_view(), name="detail"),
    path("languages/", views.LanguagesView.as_view(), name="languages"),
    path("languages/<int:pk>/level/", views.LanguageLevelView.as_view(), name="language_level"),
    path("languages/<int:pk>/remove/", views.LanguageRemoveView.as_view(), name="language_remove"),
    path("availability/", views.AvailabilityView.as_view(), name="availability"),
    path("delete-account/", views.DeleteAccountView.as_view(), name="delete_account"),
    path("edit/<slug:section>/", views.SectionEditView.as_view(), name="edit"),
]
