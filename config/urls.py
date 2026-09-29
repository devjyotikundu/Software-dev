"""Root URL configuration. Each app registers its own URLs."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Language Exchange Matcher admin"
admin.site.site_title = "Language Exchange Matcher admin"
admin.site.index_title = "Administration"

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("onboarding/", include("apps.profiles.urls")),
    path("profile/", include("apps.profiles.urls_profile")),
    path("practice/", include("apps.practice.urls")),
    path("discover/", include("apps.matching.urls")),
    path("partners/", include("apps.matching.urls_partners")),
    path("rooms/", include("apps.exchange.urls")),
    path("feedback/", include("apps.feedback.urls")),
    path("ai/", include("apps.ai_services.urls")),
    path("", include("apps.core.urls")),
]

if settings.DEBUG:
    # In production, user uploads are served by the storage backend (Phase 19).
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
