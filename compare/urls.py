from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="compare-index"),
    path("parse-resume/", views.parse_resume, name="compare-parse-resume"),
    path("add-jd/", views.add_jd, name="compare-add-jd"),
    path("stream/", views.stream, name="compare-stream"),
    path("remove-jd/", views.remove_jd, name="compare-remove-jd"),
]
