from django.urls import path

from . import views

app_name = "onboarding"

urlpatterns = [
    path("", views.OnboardingStartView.as_view(), name="start"),
    path("<slug:step>/", views.OnboardingStepView.as_view(), name="step"),
]
