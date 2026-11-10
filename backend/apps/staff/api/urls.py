from rest_framework.routers import SimpleRouter

from .views import (
    ClinicalPrivilegeViewSet,
    DesignationViewSet,
    QualificationTypeViewSet,
    SpecialtyViewSet,
    StaffCredentialViewSet,
    StaffDocumentViewSet,
    StaffMemberViewSet,
    StaffPrivilegeViewSet,
)

router = SimpleRouter()
router.register("staff", StaffMemberViewSet, basename="staff")
router.register("staff-credentials", StaffCredentialViewSet, basename="staff-credential")
router.register("staff-documents", StaffDocumentViewSet, basename="staff-document")
router.register("staff-privileges", StaffPrivilegeViewSet, basename="staff-privilege")
router.register("clinical-privileges", ClinicalPrivilegeViewSet, basename="clinical-privilege")
router.register("designations", DesignationViewSet, basename="designation")
router.register("specialties", SpecialtyViewSet, basename="specialty")
router.register("qualification-types", QualificationTypeViewSet, basename="qualification-type")

urlpatterns = router.urls
