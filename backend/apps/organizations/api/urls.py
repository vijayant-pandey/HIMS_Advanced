from django.urls import path

from .views import OrganizationView

urlpatterns = [path("organization/", OrganizationView.as_view(), name="organization")]
