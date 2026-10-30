from rest_framework.routers import SimpleRouter

from .views import AccessReviewViewSet, PermissionViewSet, RoleAssignmentViewSet, RoleViewSet

router = SimpleRouter()
router.register("permissions", PermissionViewSet, basename="permission")
router.register("roles", RoleViewSet, basename="role")
router.register("role-assignments", RoleAssignmentViewSet, basename="role-assignment")
router.register("access-reviews", AccessReviewViewSet, basename="access-review")

urlpatterns = router.urls
