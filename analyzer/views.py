import anthropic
from django.shortcuts import render
from django.http import HttpResponse
from django.views.decorators.http import require_POST

from .claude import get_service
from .pdf import extract_text_from_pdf

_API_ERRORS = {
    "authentication_error": "Invalid API key. Check your ANTHROPIC_API_KEY.",
    "permission_error": "Your API key doesn't have permission to use this model.",
    "invalid_request_error": "Bad request sent to Claude API.",
    "not_found_error": "Claude model not found.",
    "rate_limit_error": "Rate limit hit. Please wait a moment and try again.",
    "api_error": "Claude API internal error. Please try again.",
    "overloaded_error": "Claude is currently overloaded. Please try again shortly.",
}

_CREDIT_MESSAGE = "Your Anthropic credit balance is too low. Please add credits at console.anthropic.com."


def index(request):
    return render(request, 'analyzer/index.html')


@require_POST
def analyze(request):
    jd_text = request.POST.get("jd_text", "").strip()

    if request.FILES.get("resume_pdf"):
        resume_text = extract_text_from_pdf(request.FILES["resume_pdf"])
    else:
        resume_text = request.POST.get("resume_text", "").strip()

    if not resume_text:
        return HttpResponse("Please provide a resume (text or PDF).", status=400)
    if not jd_text:
        return HttpResponse("Please provide a job description.", status=400)

    try:
        result = get_service().analyze(resume_text, jd_text)
    except anthropic.APIStatusError as e:
        if "credit balance is too low" in str(e):
            return HttpResponse(_CREDIT_MESSAGE, status=402)
        msg = _API_ERRORS.get(e.body.get("error", {}).get("type", ""), str(e))
        return HttpResponse(msg, status=502)
    except anthropic.APIConnectionError:
        return HttpResponse("Could not reach the Claude API. Check your internet connection.", status=503)
    except Exception as e:
        return HttpResponse(f"Unexpected error: {e}", status=500)

    return HttpResponse(result, content_type="text/plain")
