from django.urls import path
from . import views

urlpatterns = [
    path("", views.landing, name="landing"),
    path("home/", views.index, name="home"),
    path("resume/", views.submit_resume, name="submit-resume"),
    path("resume/build/", views.build_resume_pdf, name="resume-build"),
    path("resume/render/", views.render_resume_html, name="resume-render"),
    path("resume/editor/", views.show_resume_editor, name="resume-editor"),
    path("resume/preview/", views.render_preview_from_session, name="resume-preview"),
]
