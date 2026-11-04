from django.urls import path
from rest_framework.routers import SimpleRouter

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

urlpatterns = [
    path("compliance-summary/", ComplianceSummaryView.as_view(), name="compliance-summary"),
    *router.urls,
]
