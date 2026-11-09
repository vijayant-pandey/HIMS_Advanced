from rest_framework.routers import SimpleRouter

from .template_views import MessageTemplateViewSet
from .views import NotificationViewSet

router = SimpleRouter()
router.register("notifications", NotificationViewSet, basename="notification")
router.register("message-templates", MessageTemplateViewSet, basename="message-template")

urlpatterns = router.urls
