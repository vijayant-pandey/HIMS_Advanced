from django.urls import path
from rest_framework.routers import SimpleRouter

from .staffing_views import (
    LeaveAdjustmentViewSet,
    LeaveBalancesView,
    LeaveEntitlementViewSet,
    StaffingRequirementViewSet,
)
from .views import (
    LeaveRequestViewSet,
    MyLeaveCancelView,
    MyLeaveRequestsView,
    MyScheduleView,
    RotaNowView,
    RotaWeekView,
    ShiftTypeViewSet,
    ShiftViewSet,
)

router = SimpleRouter()
router.register("shift-types", ShiftTypeViewSet, basename="shift-type")
router.register("shifts", ShiftViewSet, basename="shift")
router.register("leave-requests", LeaveRequestViewSet, basename="leave-request")
router.register(
    "staffing-requirements", StaffingRequirementViewSet, basename="staffing-requirement"
)
router.register("leave-entitlements", LeaveEntitlementViewSet, basename="leave-entitlement")
router.register("leave-adjustments", LeaveAdjustmentViewSet, basename="leave-adjustment")

urlpatterns = [
    path("rota/", RotaWeekView.as_view(), name="rota-week"),
    path("rota/now/", RotaNowView.as_view(), name="rota-now"),
    path("leave-balances/", LeaveBalancesView.as_view(), name="leave-balances"),
    path("my-schedule/", MyScheduleView.as_view(), name="my-schedule"),
    path("my-leave-requests/", MyLeaveRequestsView.as_view(), name="my-leave-requests"),
    path(
        "my-leave-requests/<uuid:pk>/cancel/",
        MyLeaveCancelView.as_view(),
        name="my-leave-request-cancel",
    ),
    *router.urls,
]
