from rest_framework.routers import SimpleRouter

from .api import BackgroundJobViewSet

router = SimpleRouter()
router.register("background-jobs", BackgroundJobViewSet, basename="background-job")

urlpatterns = router.urls
