from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="compare-index"),
    path("parse-resume/", views.parse_resume, name="compare-parse-resume"),
]
