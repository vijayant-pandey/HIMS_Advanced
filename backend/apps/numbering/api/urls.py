from rest_framework.routers import SimpleRouter

from .views import IssuedNumberViewSet, NumberingSchemeViewSet

router = SimpleRouter()
router.register("numbering-schemes", NumberingSchemeViewSet, basename="numbering-scheme")
router.register("issued-numbers", IssuedNumberViewSet, basename="issued-number")

urlpatterns = router.urls
