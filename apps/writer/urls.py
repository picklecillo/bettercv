from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="writer-index"),
    path("parse/", views.parse, name="writer-parse"),
    path("stream/", views.stream, name="writer-stream"),
    path("build/", views.build, name="writer-build"),
]
