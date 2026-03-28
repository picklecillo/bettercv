from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="coach-index"),
    path("parse/", views.parse, name="coach-parse"),
    path("chat/", views.chat, name="coach-chat"),
    path("stream/", views.stream, name="coach-stream"),
    path("conversation/<int:exp_index>/", views.conversation, name="coach-conversation"),
]
