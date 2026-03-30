from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="home"),
    path("resume/", views.submit_resume, name="submit-resume"),
]
