from django.urls import path
from . import views

app_name = 'learning'

urlpatterns = [
    path('profile/', views.profile_setup, name='profile_setup'),
    path('next-lesson/', views.next_lesson, name='next_lesson'),
    path('progress/', views.mark_progress, name='mark_progress'),
]
