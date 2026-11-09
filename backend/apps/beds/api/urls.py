from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import BedBoardView, BedViewSet, FacilityLocationsView

router = SimpleRouter()
router.register("beds", BedViewSet, basename="bed")

urlpatterns = [
    path("bed-board/", BedBoardView.as_view(), name="bed-board"),
    path(
        "facilities/<uuid:pk>/locations/",
        FacilityLocationsView.as_view(),
        name="facility-locations",
    ),
    *router.urls,
]
