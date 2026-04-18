import sys

from .base import *  # noqa: F403
from .base import (
    INSTALLED_APPS,
    TEMPLATES,
    ALLOWED_HOSTS,
)
from .base import (
    MIDDLEWARE as BASE_MIDDLEWARE,
)

SECRET_KEY = "django-insecure-ri5q9--d-dfjhfbvhhd--r610hy_&0!2b+(=(tn@w1s$#_n48("  # noqa: S105

TESTING = "test" in sys.argv
DEBUG = True

if not TESTING:
    INSTALLED_APPS += [
        "django_browser_reload",
        "debug_toolbar",
        "template_profiler_panel",
    ]

    MIDDLEWARE = [
        "django_browser_reload.middleware.BrowserReloadMiddleware",
        "debug_toolbar.middleware.DebugToolbarMiddleware",
        *BASE_MIDDLEWARE,
    ]

INTERNAL_IPS = [
    "127.0.0.1",
]

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

TEMPLATES[0]["OPTIONS"]["debug"] = DEBUG

# debug toolbar config
DEBUG_TOOLBAR_PANELS = [
    # "debug_toolbar.panels.history.HistoryPanel",
    # "debug_toolbar.panels.versions.VersionsPanel",
    # "debug_toolbar.panels.timer.TimerPanel",
    # "debug_toolbar.panels.settings.SettingsPanel",
    # "debug_toolbar.panels.headers.HeadersPanel",
    "debug_toolbar.panels.request.RequestPanel",
    # "debug_toolbar.panels.sql.SQLPanel",
    "debug_toolbar.panels.staticfiles.StaticFilesPanel",
    "debug_toolbar.panels.templates.TemplatesPanel",
    "template_profiler_panel.panels.template.TemplateProfilerPanel",
    # "debug_toolbar.panels.alerts.AlertsPanel",
    # "debug_toolbar.panels.cache.CachePanel",
    # "debug_toolbar.panels.signals.SignalsPanel",
    "debug_toolbar.panels.redirects.RedirectsPanel",
    "debug_toolbar.panels.profiling.ProfilingPanel",
]

# Docker doesn't use 127.0.0.1 as the client IP, so bypass the IP check in DEBUG mode
DEBUG_TOOLBAR_CONFIG = {
    "SHOW_TOOLBAR_CALLBACK": lambda request: DEBUG,
}
