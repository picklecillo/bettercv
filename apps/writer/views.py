from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.utils.html import escape
from django.views.decorators.http import require_GET, require_POST

from apps.shared.pdf import PdfExtractionError, extract_text_from_pdf
from apps.shared import session as sess
from apps.shared.decorators import htmx_login_required
from apps.shared.sse import make_sse_response, no_credits_response

from .rendercv_builder import RenderCVBuildError, get_builder
from .writer_service import get_writer_service


def _error(message: str, status: int = 400) -> HttpResponse:
    return HttpResponse(
        f'<div class="result-error">{escape(message)}</div>',
        status=status,
        content_type="text/html",
    )


@htmx_login_required
def index(request):
    return render(request, "writer/index.html", {
        **sess.shared(request.session).panel_context(),
        "active_tool": "writer",
    })


@require_POST
def parse(request):
    if request.FILES.get("resume_pdf"):
        try:
            resume_text = extract_text_from_pdf(request.FILES["resume_pdf"])
        except PdfExtractionError as e:
            return _error(str(e))
    else:
        resume_text = request.POST.get("resume_text", "").strip()
        if not resume_text:
            return _error("Please provide your resume (text or PDF).")

    nonce_key = sess.nonce(request.session).put({"resume_text": resume_text})
    return render(request, "writer/_step2.html", {"nonce": nonce_key})


@htmx_login_required
@require_GET
def stream(request):
    key = request.GET.get("key", "")
    nonce_data = sess.nonce(request.session).pop(key)
    if not nonce_data:
        return HttpResponse("Session expired. Please try again.", status=400)

    from apps.accounts.credits import deduct_credit
    if not deduct_credit(request.user, 1, 'Resume Writer — YAML generation'):
        return no_credits_response()

    resume_text = nonce_data["resume_text"]

    def event_stream():
        try:
            for chunk in get_writer_service().stream_yaml(resume_text):
                lines = "\n".join(f"data: {line}" for line in chunk.split("\n"))
                yield f"event: chunk\n{lines}\n\n"
        except Exception as e:
            safe_msg = escape(str(e))
            yield f"event: error\ndata: {safe_msg}\n\n"

        yield "event: done\ndata: \n\n"

    return make_sse_response(event_stream())


@require_POST
def build(request):
    yaml_content = request.POST.get("yaml_content", "").strip()
    if not yaml_content:
        return _error("No YAML content provided.")

    session_key = request.session.session_key or "default"

    try:
        pdf_bytes = get_builder().build_pdf(yaml_content, session_key)
    except RenderCVBuildError as e:
        return HttpResponse(
            f'<div class="result-error">{escape(str(e))}</div>',
            status=422,
            content_type="text/html",
        )

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="resume.pdf"'
    return response


@require_POST
def render_preview(request):
    yaml_content = request.POST.get("yaml_content", "").strip()
    if not yaml_content:
        return JsonResponse({"error": "No YAML content provided."}, status=400)

    session_key = request.session.session_key or "default"

    try:
        html = get_builder().render_html(yaml_content, session_key)
    except RenderCVBuildError as e:
        return JsonResponse({"error": str(e)}, status=422)

    return JsonResponse({"html": html})
