from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
    AppointmentViewSet,
    DoctorAvailabilityView,
    DoctorScheduleViewSet,
    MyOpdSessionsView,
    ScheduleExceptionViewSet,
)

router = SimpleRouter()
router.register("doctor-schedules", DoctorScheduleViewSet, basename="doctor-schedule")
router.register("schedule-exceptions", ScheduleExceptionViewSet, basename="schedule-exception")
router.register("appointments", AppointmentViewSet, basename="appointment")

urlpatterns = [
    path("availability/", DoctorAvailabilityView.as_view(), name="doctor-availability"),
    path("my-opd-sessions/", MyOpdSessionsView.as_view(), name="my-opd-sessions"),
    *router.urls,
]
