from django.conf import settings


def analytics(request):
    env = getattr(settings, "ENV", "dev")
    sentry_dsn = getattr(settings, "SENTRY_DSN", "")
    return {
        "google_analytics_id": getattr(settings, "GOOGLE_ANALYTICS_ID", ""),
        "sentry_dsn": sentry_dsn if env == "production" else "",
    }
