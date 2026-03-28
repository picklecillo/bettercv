from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="coach-index"),
    path("parse/", views.parse, name="coach-parse"),
]
