from rest_framework.routers import SimpleRouter

from .views import EmergencyAccessViewSet, PatientViewSet

router = SimpleRouter()
router.register("patients", PatientViewSet, basename="patient")
router.register(
    "patient-emergency-access", EmergencyAccessViewSet, basename="patient-emergency-access"
)

urlpatterns = router.urls
