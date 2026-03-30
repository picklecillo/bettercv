from django.http import HttpResponse
from django.shortcuts import render
from django.utils.html import escape
from django.views.decorators.http import require_POST

from apps.shared.pdf import PdfExtractionError, extract_text_from_pdf
from apps.shared.session import get_shared_resume, set_shared_resume


def index(request):
    shared = get_shared_resume(request.session)
    change = request.GET.get("change")
    return render(request, "home/index.html", {
        "shared_resume": shared,
        "show_cards": bool(shared) and not change,
    })


@require_POST
def submit_resume(request):
    if request.FILES.get("resume_pdf"):
        try:
            resume_text = extract_text_from_pdf(request.FILES["resume_pdf"])
        except PdfExtractionError as e:
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
            return HttpResponse(
                '<div class="result-error">Please provide a resume (text or PDF).</div>',
                status=400,
                content_type="text/html",
            )

    set_shared_resume(request.session, resume_text, filename)
    shared = get_shared_resume(request.session)

    source = request.POST.get("source", "")
    if source == "home":
        return render(request, "home/_tool_cards.html", {"shared_resume": shared})

    # From a tool page: redirect to home (HTMX handles the header)
    response = HttpResponse(status=204)
    response["HX-Redirect"] = "/"
    return response
