from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access_control.catalog import P

from ..selectors import get_deployment_organization
from ..services import update_organization
from .serializers import OrganizationSerializer, OrganizationUpdateSerializer


class OrganizationView(APIView):
    """The deployment's single organization. Creation happens through provisioning
    (``manage.py provision_organization``), not this API (ADR-009)."""

    required_permissions = {"get": P.ORGANIZATION_VIEW, "patch": P.ORGANIZATION_MANAGE}

    @extend_schema(responses=OrganizationSerializer)
    def get(self, request):
        return Response(OrganizationSerializer(get_deployment_organization()).data)

    @extend_schema(request=OrganizationUpdateSerializer, responses=OrganizationSerializer)
    def patch(self, request):
        serializer = OrganizationUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        organization = update_organization(
            actor=request.user,
            organization_id=get_deployment_organization().pk,
            version=data.pop("version"),
            request=request,
            **data,
        )
        return Response(OrganizationSerializer(organization).data)
