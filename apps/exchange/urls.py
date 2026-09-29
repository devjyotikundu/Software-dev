from django.urls import path

from . import views

app_name = "exchange"

urlpatterns = [
    path("<int:room_id>/", views.RoomView.as_view(), name="room"),
    path("<int:room_id>/messages/", views.PostMessageView.as_view(), name="post_message"),
    path("<int:room_id>/session/start/", views.StartSessionView.as_view(), name="start_session"),
    path("<int:room_id>/session/end/", views.EndSessionView.as_view(), name="end_session"),
]
