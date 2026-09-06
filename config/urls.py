"""
Root URL configuration.

Maps directly onto the API contract from Lab 3 / the Exercise C2 table:
    POST /auth/register/
    POST /auth/login/
    GET  /auth/logout/
    POST /learning/profile/
    GET  /learning/next-lesson/
    POST /learning/progress/
    GET, POST /translate/
"""
from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', TemplateView.as_view(template_name='home.html'), name='home'),
    path('auth/', include('accounts.urls')),
    path('learning/', include('learning.urls')),
    path('translate/', include('translator.urls')),
]
