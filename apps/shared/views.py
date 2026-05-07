from django.http import HttpResponse
from django.views.decorators.http import require_POST


@require_POST
def set_language(request):
    lang = request.POST.get("lang", "en")
    if lang not in ("en", "es"):
        lang = "en"
    request.session["lang"] = lang
    request.session.save()
    return HttpResponse("", status=204)
