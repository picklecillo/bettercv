from django.conf import settings

from .i18n import TRANSLATIONS


def analytics(request):
    env = getattr(settings, "ENV", "dev")
    sentry_dsn = getattr(settings, "SENTRY_DSN", "")
    return {
        "google_analytics_id": getattr(settings, "GOOGLE_ANALYTICS_ID", ""),
        "sentry_dsn": sentry_dsn if env == "production" else "",
    }


def lang_context(request):
    lang = request.session.get("lang", "en")
    return {
        "lang": lang,
        "ui": TRANSLATIONS.get(lang, TRANSLATIONS["en"]),
    }
