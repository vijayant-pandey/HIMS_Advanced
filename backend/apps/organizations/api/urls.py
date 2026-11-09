from django.urls import path

from .views import (
    LetterheadView,
    OrganizationLogoRemoveView,
    OrganizationLogoView,
    OrganizationView,
)

urlpatterns = [
    path("organization/", OrganizationView.as_view(), name="organization"),
    path("organization/letterhead/", LetterheadView.as_view(), name="organization-letterhead"),
    path("organization/logo/", OrganizationLogoView.as_view(), name="organization-logo"),
    path(
        "organization/logo/remove/",
        OrganizationLogoRemoveView.as_view(),
        name="organization-logo-remove",
    ),
]
