import logging

from django.http import HttpResponse
from django.shortcuts import render
from django.utils.html import escape
from django.views.decorators.http import require_GET, require_POST

from apps.shared.pdf import PdfExtractionError, extract_text_from_pdf
from apps.shared import session as sess
from apps.writer.rendercv_builder import RenderCVBuildError, get_builder
from apps.writer.writer_service import get_writer_service

logger = logging.getLogger(__name__)


def landing(request):
    return render(request, "home/landing.html")


def robots_txt(request):
    return render(request, "home/robots.txt", content_type="text/plain")


def sitemap_xml(request):
    return render(request, "home/sitemap.xml", content_type="application/xml")


def _panel_context(request) -> dict:
    return sess.shared(request.session).panel_context()


def index(request):
    return render(request, "home/index.html", _panel_context(request))


def _panel_error(request, message):
    shared = sess.shared(request.session).resume
    return render(
        request,
        "home/_panel_upload.html",
        {"shared_resume": shared, "error_message": message, "show_replace_form": True},
    )


@require_POST
def submit_resume(request):
    source = request.POST.get("source", "")

    if request.FILES.get("resume_pdf"):
        try:
            resume_text = extract_text_from_pdf(request.FILES["resume_pdf"])
        except PdfExtractionError as e:
            if source == "panel":
                return _panel_error(request, str(e))
            return HttpResponse(
                f'<div class="result-error">{escape(str(e))}</div>',
                status=400,
                content_type="text/html",
            )
        filename = request.FILES["resume_pdf"].name
    else:
        resume_text = request.POST.get("resume_text", "").strip()
        filename = None
        if not resume_text:
            if source == "panel":
                return _panel_error(request, "Please provide a resume (text or PDF).")
            return HttpResponse(
                '<div class="result-error">Please provide a resume (text or PDF).</div>',
                status=400,
                content_type="text/html",
            )

    shared_store = sess.shared(request.session)
    shared_store.set_resume(resume_text, filename)

    if source == "panel":
        # Generate YAML and render HTML preview synchronously.
        try:
            yaml_content = "".join(get_writer_service().stream_yaml(resume_text))
            html_content = get_builder().render_html(
                yaml_content, request.session.session_key or "panel"
            )
        except RenderCVBuildError as e:
            logger.warning("Panel render failed: %s", e)
            return _panel_error(request, str(e))
        except Exception as e:
            logger.error("Panel YAML/HTML generation failed: %s", e)
            return _panel_error(request, str(e))

        shared_store.set_yaml(yaml_content)
        shared_store.set_html(html_content)
        request.session.save()

        ctx = _panel_context(request)
        return render(request, "home/_panel_preview.html", ctx)

    # Legacy: from old tool-page resume forms — redirect to home
    response = HttpResponse(status=204)
    response["HX-Redirect"] = "/home/"
    return response


@require_POST
def build_resume_pdf(request):
    yaml_content = request.POST.get("yaml_content", "").strip() or sess.shared(request.session).yaml
    if not yaml_content:
        return HttpResponse("No YAML content available.", status=400, content_type="text/plain")

    try:
        pdf_bytes = get_builder().build_pdf(yaml_content, request.session.session_key or "panel")
    except RenderCVBuildError as e:
        return HttpResponse(str(e), status=422, content_type="text/plain")

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="resume.pdf"'
    return response


@require_GET
def render_preview_from_session(request):
    """Re-render the preview panel from the YAML already in session (no body needed)."""
    shared_store = sess.shared(request.session)
    yaml_content = shared_store.yaml
    if not yaml_content:
        return HttpResponse("No YAML in session.", status=400)

    try:
        html_content = get_builder().render_html(
            yaml_content, request.session.session_key or "panel"
        )
    except RenderCVBuildError as e:
        ctx = {**_panel_context(request), "render_error": str(e)}
        return render(request, "home/_panel_editor.html", ctx, status=422)

    shared_store.set_html(html_content)
    request.session.save()

    return render(request, "home/_panel_preview.html", _panel_context(request))


@require_GET
def show_resume_upload(request):
    shared = sess.shared(request.session).resume
    return render(request, "home/_panel_upload.html", {"shared_resume": shared, "show_replace_form": True})


def show_resume_editor(request):
    ctx = _panel_context(request)
    if not ctx["shared_yaml"]:
        ctx = {**ctx, "render_error": "No resume loaded. Please upload a resume first."}
    return render(request, "home/_panel_editor.html", ctx)


@require_POST
def render_resume_html(request):
    """Re-render HTML from submitted YAML and return the panel in preview state."""
    yaml_content = request.POST.get("yaml_content", "").strip()
    if not yaml_content:
        return _panel_error(request, "No YAML content provided.")

    try:
        html_content = get_builder().render_html(
            yaml_content, request.session.session_key or "panel"
        )
    except RenderCVBuildError as e:
        ctx = {
            **_panel_context(request),
            "shared_yaml": yaml_content,
            "render_error": str(e),
        }
        return render(request, "home/_panel_editor.html", ctx, status=422)

    shared_store = sess.shared(request.session)
    shared_store.set_yaml(yaml_content)
    shared_store.bump_resume_version()
    shared_store.set_html(html_content)
    request.session.save()

    ctx = _panel_context(request)
    return render(request, "home/_panel_preview.html", ctx)
