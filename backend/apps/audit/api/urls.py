from rest_framework.routers import SimpleRouter

from .integrity import AuditIntegrityCheckViewSet
from .views import AuditEventViewSet

router = SimpleRouter()
router.register("audit-events", AuditEventViewSet, basename="audit-event")
router.register(
    "audit-integrity-checks", AuditIntegrityCheckViewSet, basename="audit-integrity-check"
)

urlpatterns = router.urls
