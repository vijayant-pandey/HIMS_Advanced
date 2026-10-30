from rest_framework.routers import SimpleRouter

from .views import (
    DesignationViewSet,
    QualificationTypeViewSet,
    SpecialtyViewSet,
    StaffCredentialViewSet,
    StaffDocumentViewSet,
    StaffMemberViewSet,
)

router = SimpleRouter()
router.register("staff", StaffMemberViewSet, basename="staff")
router.register("staff-credentials", StaffCredentialViewSet, basename="staff-credential")
router.register("staff-documents", StaffDocumentViewSet, basename="staff-document")
router.register("designations", DesignationViewSet, basename="designation")
router.register("specialties", SpecialtyViewSet, basename="specialty")
router.register("qualification-types", QualificationTypeViewSet, basename="qualification-type")

urlpatterns = router.urls
