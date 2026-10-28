from django.conf import settings
from django.urls import include, path

from common import health

api_v1 = [
    path("auth/", include("apps.identity.api.urls")),
    path("", include("apps.identity.api.account_urls")),
    path("", include("apps.organizations.api.urls")),
    path("", include("apps.facilities.api.urls")),
    path("", include("apps.beds.api.urls")),
    path("", include("apps.numbering.api.urls")),
    path("", include("apps.features.api.urls")),
    path("", include("apps.access_control.api.urls")),
    path("", include("apps.staff.api.urls")),
    path("", include("apps.audit.api.urls")),
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
    from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

    urlpatterns += [
        path("api/schema/", SpectacularAPIView.as_view(), name="api-schema"),
        path("api/docs/", SpectacularSwaggerView.as_view(url_name="api-schema"), name="api-docs"),
    ]
