import uuid

from django.http import HttpResponse, StreamingHttpResponse
from django.shortcuts import render
from django.utils.html import escape
from django.views.decorators.http import require_GET, require_POST

from apps.shared.pdf import PdfExtractionError, extract_text_from_pdf
from apps.shared.session import get_shared_resume

from .simple_resume_builder import SimpleResumeBuildError, get_builder
from .writer_service import get_writer_service


def _error(message: str, status: int = 400) -> HttpResponse:
    return HttpResponse(
        f'<div class="result-error">{escape(message)}</div>',
        status=status,
        content_type="text/html",
    )


def index(request):
    shared = get_shared_resume(request.session)
    return render(request, "writer/index.html", {"shared_resume": shared})


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

    nonce = str(uuid.uuid4())
    request.session[nonce] = {"resume_text": resume_text}
    request.session.modified = True

    return render(request, "writer/_step2.html", {"nonce": nonce})


@require_GET
def stream(request):
    key = request.GET.get("key", "")
    nonce_data = request.session.pop(key, None)
    if not nonce_data:
        return HttpResponse("Session expired. Please try again.", status=400)

    request.session.modified = True
    resume_text = nonce_data["resume_text"]

    def event_stream():
        errored = False
        try:
            for chunk in get_writer_service().stream_yaml(resume_text):
                lines = "\n".join(f"data: {line}" for line in chunk.split("\n"))
                yield f"event: chunk\n{lines}\n\n"
        except Exception as e:
            errored = True
            safe_msg = escape(str(e))
            yield f"event: error\ndata: {safe_msg}\n\n"

        yield "event: done\ndata: \n\n"

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


@require_POST
def build(request):
    yaml_content = request.POST.get("yaml_content", "").strip()
    if not yaml_content:
        return _error("No YAML content provided.")

    session_key = request.session.session_key or "default"

    try:
        pdf_bytes = get_builder().build_pdf(yaml_content, session_key)
    except SimpleResumeBuildError as e:
        return HttpResponse(
            f'<div class="result-error">{escape(str(e))}</div>',
            status=422,
            content_type="text/html",
        )

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="resume.pdf"'
    return response
