from rest_framework.routers import SimpleRouter

from .views import PerformanceCheckViewSet

router = SimpleRouter()
router.register("performance-checks", PerformanceCheckViewSet, basename="performance-check")

urlpatterns = router.urls
