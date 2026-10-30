from rest_framework.routers import SimpleRouter

from .location_views import BuildingViewSet, FloorViewSet, RoomViewSet, WardViewSet
from .views import DepartmentServiceViewSet, DepartmentViewSet, FacilityViewSet

router = SimpleRouter()
router.register("facilities", FacilityViewSet, basename="facility")
router.register("departments", DepartmentViewSet, basename="department")
router.register("department-services", DepartmentServiceViewSet, basename="department-service")
router.register("buildings", BuildingViewSet, basename="building")
router.register("floors", FloorViewSet, basename="floor")
router.register("wards", WardViewSet, basename="ward")
router.register("rooms", RoomViewSet, basename="room")

urlpatterns = router.urls
