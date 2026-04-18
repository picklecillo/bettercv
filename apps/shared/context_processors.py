from django.conf import settings


def analytics(request):
    return {
        "google_analytics_id": getattr(settings, "GOOGLE_ANALYTICS_ID", ""),
    }
