from django.urls import path
from rest_framework.routers import SimpleRouter

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

urlpatterns = [
    path("rota/", RotaWeekView.as_view(), name="rota-week"),
    path("rota/now/", RotaNowView.as_view(), name="rota-now"),
    path("my-schedule/", MyScheduleView.as_view(), name="my-schedule"),
    path("my-leave-requests/", MyLeaveRequestsView.as_view(), name="my-leave-requests"),
    path(
        "my-leave-requests/<uuid:pk>/cancel/",
        MyLeaveCancelView.as_view(),
        name="my-leave-request-cancel",
    ),
    *router.urls,
]
