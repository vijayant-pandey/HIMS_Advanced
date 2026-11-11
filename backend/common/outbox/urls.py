from django.urls import path
from rest_framework.routers import SimpleRouter

from .api import BackgroundJobViewSet
from .trigger import ScheduledJobsTriggerView

router = SimpleRouter()
router.register("background-jobs", BackgroundJobViewSet, basename="background-job")

urlpatterns = [
    path("scheduled-jobs/run/", ScheduledJobsTriggerView.as_view(), name="scheduled-jobs-run"),
    *router.urls,
]
