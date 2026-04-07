from django.http import HttpResponse, StreamingHttpResponse
from django.shortcuts import render
from django.utils.html import escape
from django.views.decorators.http import require_POST

from apps.accounts.credits import CreditCost
from apps.shared.pdf import PdfExtractionError, extract_text_from_pdf
from apps.shared import session as sess
from apps.shared.decorators import htmx_login_required
from apps.shared.sse import SseStream, no_credits_response

from .claude import ClaudeServiceError, get_service

STREAM_COST = CreditCost(amount=1, description='ATS analysis')


def _error(message: str, status: int = 400) -> HttpResponse:
    return HttpResponse(
        f'<div class="result-error">{escape(message)}</div>',
        status=status,
        content_type="text/html",
    )


@htmx_login_required
def index(request):
    return render(request, 'analyzer/index.html', {
        **sess.shared(request.session).panel_context(),
        "active_tool": "analyzer",
    })


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

    key = sess.nonce(request.session).put({"resume_text": resume_text, "jd_text": jd_text})

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


@htmx_login_required
def stream(request):
    key = request.GET.get("key", "")
    data = sess.nonce(request.session).pop(key)
    if not data:
        return HttpResponse("Session expired. Please submit the form again.", status=400)

    if resp := STREAM_COST.guard(request.user, no_credits_response):
        return resp

    return SseStream(
        source=get_service().stream(data["resume_text"], data["jd_text"]),
        known_errors=(ClaudeServiceError,),
    ).response()
