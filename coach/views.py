import dataclasses

from django.http import HttpResponse
from django.shortcuts import render
from django.utils.html import escape
from django.views.decorators.http import require_POST

from analyzer.pdf import PdfExtractionError, extract_text_from_pdf
from .coach_service import CoachParseError, get_coach_service


def _error(message: str, status: int = 400) -> HttpResponse:
    return HttpResponse(
        f'<div class="result-error">{escape(message)}</div>',
        status=status,
        content_type="text/html",
    )


def index(request):
    return render(request, "coach/index.html")


@require_POST
def parse(request):
    if request.FILES.get("resume_pdf"):
        try:
            cv_text = extract_text_from_pdf(request.FILES["resume_pdf"])
        except PdfExtractionError as e:
            return _error(str(e))
    else:
        cv_text = request.POST.get("cv_text", "").strip()
        if not cv_text:
            return _error("Please provide your CV (text or PDF).")

    try:
        experiences = get_coach_service().parse_cv(cv_text)
    except CoachParseError as e:
        return _error(str(e))

    request.session["coach"] = {
        "cv_text": cv_text,
        "experiences": [dataclasses.asdict(e) for e in experiences],
        "conversations": {},
    }

    return render(request, "coach/split_screen.html", {"cv_text": cv_text, "experiences": experiences})
