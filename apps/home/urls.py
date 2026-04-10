from django.urls import path
from . import views

urlpatterns = [
    path("", views.landing, name="landing"),
    path("robots.txt", views.robots_txt, name="robots-txt"),
    path("sitemap.xml", views.sitemap_xml, name="sitemap-xml"),
    path("home/", views.index, name="home"),
    path("resume/", views.submit_resume, name="submit-resume"),
    path("resume/build/", views.build_resume_pdf, name="resume-build"),
    path("resume/render/", views.render_resume_html, name="resume-render"),
    path("resume/upload/", views.show_resume_upload, name="resume-upload"),
    path("resume/editor/", views.show_resume_editor, name="resume-editor"),
    path("resume/preview/", views.render_preview_from_session, name="resume-preview"),
    path("resume/design/", views.apply_design, name="resume-design"),
]
