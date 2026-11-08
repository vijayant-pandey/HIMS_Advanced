from django.urls import path
from rest_framework.routers import SimpleRouter

from .browser_views import (
    BrowserReportReceiveView,
    BrowserSecurityReportViewSet,
    SecurityStatusView,
)
from .database_views import DatabaseAccessView
from .views import (
    ComplianceRequirementViewSet,
    ComplianceSummaryView,
    RiskEntryViewSet,
    SecurityIncidentViewSet,
)

router = SimpleRouter()
router.register(
    "compliance-requirements", ComplianceRequirementViewSet, basename="compliance-requirement"
)
router.register("compliance-risks", RiskEntryViewSet, basename="compliance-risk")
router.register("security-incidents", SecurityIncidentViewSet, basename="security-incident")
router.register(
    "browser-security-reports", BrowserSecurityReportViewSet, basename="browser-security-report"
)

urlpatterns = [
    path("compliance-summary/", ComplianceSummaryView.as_view(), name="compliance-summary"),
    path("security/browser-reports/", BrowserReportReceiveView.as_view(), name="browser-report"),
    path("security/status/", SecurityStatusView.as_view(), name="security-status"),
    path("security/database-access/", DatabaseAccessView.as_view(), name="database-access"),
    *router.urls,
]
