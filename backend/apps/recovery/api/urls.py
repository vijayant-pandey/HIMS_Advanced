from rest_framework.routers import SimpleRouter

from .views import BackupViewSet, RestoreDrillViewSet

router = SimpleRouter()
router.register("backups", BackupViewSet, basename="backup")
router.register("restore-drills", RestoreDrillViewSet, basename="restore-drill")

urlpatterns = router.urls
