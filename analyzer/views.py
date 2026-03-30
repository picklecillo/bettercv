import uuid
import markdown as md
from django.http import HttpResponse, StreamingHttpResponse
from django.shortcuts import render
from django.utils.html import escape
from django.views.decorators.http import require_POST

from .claude import ClaudeServiceError, get_service
from shared.pdf import PdfExtractionError, extract_text_from_pdf
from shared.session import get_shared_resume


def _error(message: str, status: int = 400) -> HttpResponse:
    return HttpResponse(
        f'<div class="result-error">{escape(message)}</div>',
        status=status,
        content_type="text/html",
    )


def index(request):
    shared = get_shared_resume(request.session)
    return render(request, 'analyzer/index.html', {'shared_resume': shared})


@require_POST
def analyze(request):
    jd_text = request.POST.get("jd_text", "").strip()

    if request.FILES.get("resume_pdf"):
        try:
            resume_text = extract_text_from_pdf(request.FILES["resume_pdf"])
        except PdfExtractionError as e:
            return _error(str(e))
    else:
        resume_text = request.POST.get("resume_text", "").strip()
        if not resume_text:
            return _error("Please provide a resume (text or PDF).")

    if not jd_text:
        return _error("Please provide a job description.")

    key = str(uuid.uuid4())
    request.session[key] = {"resume_text": resume_text, "jd_text": jd_text}

    return HttpResponse(
        f'<div id="sse-container"'
        f'     hx-ext="sse"'
        f'     sse-connect="/analyzer/analyze/stream/?key={key}"'
        f'     sse-close="done">'
        f'  <div id="stream-output"'
        f'       sse-swap="chunk"'
        f'       hx-swap="beforeend"></div>'
        f'  <div class="stream-status">Analyzing<span class="dots">...</span></div>'
        f'  <div sse-swap="render"'
        f'       hx-target="#stream-output"'
        f'       hx-swap="innerHTML"></div>'
        f'</div>',
        content_type="text/html",
    )


def stream(request):
    key = request.GET.get("key", "")
    data = request.session.pop(key, None)
    if not data:
        return HttpResponse("Session expired. Please submit the form again.", status=400)

    def event_stream():
        accumulated = []
        errored = False
        try:
            for chunk in get_service().stream(data["resume_text"], data["jd_text"]):
                accumulated.append(chunk)
                safe = escape(chunk).replace("\n", "<br>")
                yield f"event: chunk\ndata: <span>{safe}</span>\n\n"
        except ClaudeServiceError as e:
            errored = True
            safe_msg = escape(e.message)
            yield f"event: chunk\ndata: <div class='result-error'>{safe_msg}</div>\n\n"
        except Exception as e:
            errored = True
            safe_msg = escape(str(e))
            yield f"event: chunk\ndata: <div class='result-error'>Unexpected error: {safe_msg}</div>\n\n"

        if not errored and accumulated:
            rendered = md.markdown("".join(accumulated), extensions=["tables"])
            data_lines = "\n".join(f"data: {line}" for line in rendered.splitlines())
            yield f"event: render\n{data_lines}\n\n"

        yield "event: done\ndata: \n\n"

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
