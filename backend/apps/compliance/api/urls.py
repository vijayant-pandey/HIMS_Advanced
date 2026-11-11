from django.urls import path
from rest_framework.routers import SimpleRouter

from .browser_views import (
    BrowserReportReceiveView,
    BrowserSecurityReportViewSet,
    SecurityStatusView,
)
from .console_views import ConsoleAccessBlockViewSet, ConsoleAccessView
from .database_views import DatabaseAccessView
from .hosting_views import HostingReadinessView
from .retention_views import (
    LegalHoldViewSet,
    RetentionPeriodView,
    RetentionPurgeRunViewSet,
    RetentionRunView,
    RetentionView,
)
from .review_views import SecurityReviewView
from .scanning_views import ScanDocumentsView, ScanningStatusView
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
router.register("console-access-blocks", ConsoleAccessBlockViewSet, basename="console-access-block")
router.register("legal-holds", LegalHoldViewSet, basename="legal-hold")
router.register("retention-runs", RetentionPurgeRunViewSet, basename="retention-run")

urlpatterns = [
    path("compliance-summary/", ComplianceSummaryView.as_view(), name="compliance-summary"),
    path("security/browser-reports/", BrowserReportReceiveView.as_view(), name="browser-report"),
    path("security/status/", SecurityStatusView.as_view(), name="security-status"),
    path("security/database-access/", DatabaseAccessView.as_view(), name="database-access"),
    path("security/console-access/", ConsoleAccessView.as_view(), name="console-access"),
    path("security/upload-scanning/", ScanningStatusView.as_view(), name="upload-scanning"),
    path("security/review/", SecurityReviewView.as_view(), name="security-review"),
    path("security/hosting/", HostingReadinessView.as_view(), name="hosting-readiness"),
    path(
        "security/upload-scanning/scan/",
        ScanDocumentsView.as_view(),
        name="upload-scanning-scan",
    ),
    path("retention/", RetentionView.as_view(), name="retention"),
    path("retention/run/", RetentionRunView.as_view(), name="retention-run-now"),
    path(
        "retention/periods/<str:category>/",
        RetentionPeriodView.as_view(),
        name="retention-period",
    ),
    *router.urls,
]
