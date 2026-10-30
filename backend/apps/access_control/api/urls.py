from django.urls import path
from rest_framework.routers import SimpleRouter

from .delegation_views import AccessDelegationViewSet, MyDelegationsView
from .views import AccessReviewViewSet, PermissionViewSet, RoleAssignmentViewSet, RoleViewSet

router = SimpleRouter()
router.register("permissions", PermissionViewSet, basename="permission")
router.register("roles", RoleViewSet, basename="role")
router.register("role-assignments", RoleAssignmentViewSet, basename="role-assignment")
router.register("access-reviews", AccessReviewViewSet, basename="access-review")
router.register("access-delegations", AccessDelegationViewSet, basename="access-delegation")

urlpatterns = [
    path("my-delegations/", MyDelegationsView.as_view(), name="my-delegations"),
    *router.urls,
]
