from django.http import HttpResponse
from django.shortcuts import render
from django.utils.html import escape
from django.views.decorators.http import require_POST

from analyzer.pdf import PdfExtractionError, extract_text_from_pdf


def _error(message: str, status: int = 400) -> HttpResponse:
    return HttpResponse(
        f'<div class="result-error">{escape(message)}</div>',
        status=status,
        content_type="text/html",
    )


def index(request):
    request.session.pop("compare", None)
    return render(request, "compare/index.html")


@require_POST
def parse_resume(request):
    if request.FILES.get("resume_pdf"):
        try:
            resume_text = extract_text_from_pdf(request.FILES["resume_pdf"])
        except PdfExtractionError as e:
            return _error(str(e))
    else:
        resume_text = request.POST.get("resume_text", "").strip()
        if not resume_text:
            return _error("Please provide your resume (text or PDF).")

    request.session["compare"] = {
        "resume_text": resume_text,
        "jds": {},
    }

    return render(request, "compare/workspace.html", {"resume_text": resume_text})
