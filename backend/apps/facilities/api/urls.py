from rest_framework.routers import SimpleRouter

from .views import DepartmentViewSet, FacilityViewSet

router = SimpleRouter()
router.register("facilities", FacilityViewSet, basename="facility")
router.register("departments", DepartmentViewSet, basename="department")

urlpatterns = router.urls
