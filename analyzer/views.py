from django.shortcuts import render
from django.http import HttpResponse
from django.views.decorators.http import require_POST

from .claude import ClaudeServiceError, get_service
from .pdf import PdfExtractionError, extract_text_from_pdf


def index(request):
    return render(request, 'analyzer/index.html')


@require_POST
def analyze(request):
    jd_text = request.POST.get("jd_text", "").strip()

    if request.FILES.get("resume_pdf"):
        try:
            resume_text = extract_text_from_pdf(request.FILES["resume_pdf"])
        except PdfExtractionError as e:
            return HttpResponse(str(e), status=400)
    else:
        resume_text = request.POST.get("resume_text", "").strip()
        if not resume_text:
            return HttpResponse("Please provide a resume (text or PDF).", status=400)
    if not jd_text:
        return HttpResponse("Please provide a job description.", status=400)

    try:
        result = get_service().analyze(resume_text, jd_text)
    except ClaudeServiceError as e:
        return HttpResponse(e.message, status=e.status)
    except Exception as e:
        return HttpResponse(f"Unexpected error: {e}", status=500)

    return HttpResponse(result, content_type="text/plain")
