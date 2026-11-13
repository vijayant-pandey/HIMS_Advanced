from django.conf import settings
from django.urls import include, path, re_path

from common import health, screens

api_v1 = [
    path("auth/", include("apps.identity.api.urls")),
    path("", include("apps.identity.api.account_urls")),
    path("", include("apps.organizations.api.urls")),
    path("", include("apps.facilities.api.urls")),
    path("", include("apps.beds.api.urls")),
    path("", include("apps.equipment.api.urls")),
    path("", include("apps.patients.api.urls")),
    path("", include("apps.numbering.api.urls")),
    path("", include("apps.features.api.urls")),
    path("", include("apps.access_control.api.urls")),
    path("", include("apps.staff.api.urls")),
    path("", include("apps.rosters.api.urls")),
    path("", include("apps.audit.api.urls")),
    path("", include("apps.notifications.api.urls")),
    path("", include("apps.compliance.api.urls")),
    path("", include("apps.recovery.api.urls")),
    path("", include("apps.performance.api.urls")),
    path("", include("common.outbox.urls")),
    path("", include("common.contracts.api")),
]

urlpatterns = [
    path("health/live/", health.live, name="health-live"),
    path("health/ready/", health.ready, name="health-ready"),
    path("api/v1/", include(api_v1)),
]

if settings.HIMS_ENABLE_ADMIN:
    from django.contrib import admin

    urlpatterns += [path("admin/", admin.site.urls)]

if settings.HIMS_ENABLE_API_DOCS:
    from drf_spectacular import views as spectacular

    urlpatterns += [
        path("api/schema/", spectacular.SpectacularAPIView.as_view(), name="api-schema"),
        # The split view serves its start-up script as a file, so no inline script is needed.
        path(
            "api/docs/",
            spectacular.SpectacularSwaggerSplitView.as_view(url_name="api-schema"),
            name="api-docs",
        ),
    ]

# The screens, when this server serves them (HIMS_FRONTEND_DIST; HIMS-OPS-022). Last, so it never
# hides an API, console or health address; answers 404 when the screens are not served here.
urlpatterns += [
    re_path(
        # Not the server's own areas, so "/admin" or "/api/v1/staff" still get their missing slash.
        r"^(?!(api|admin|health|static|assets|media-not-served)(/|$))(?P<path>.*)$",
        screens.index,
        name="screens",
    )
]
