from rest_framework.routers import SimpleRouter

from .views import (
    QualificationTypeViewSet,
    SpecialtyViewSet,
    StaffCredentialViewSet,
    StaffMemberViewSet,
)

router = SimpleRouter()
router.register("staff", StaffMemberViewSet, basename="staff")
router.register("staff-credentials", StaffCredentialViewSet, basename="staff-credential")
router.register("specialties", SpecialtyViewSet, basename="specialty")
router.register("qualification-types", QualificationTypeViewSet, basename="qualification-type")

urlpatterns = router.urls
