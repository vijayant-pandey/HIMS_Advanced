from django.http import FileResponse, Http404
from drf_spectacular.utils import extend_schema
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access_control.catalog import P

from ..logo import logo_type
from ..selectors import get_deployment_organization
from ..services import remove_logo, set_logo, update_organization
from .serializers import (
    LetterheadSerializer,
    LogoUploadSerializer,
    OrganizationSerializer,
    OrganizationUpdateSerializer,
)


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


class LetterheadView(APIView):
    """The hospital's letterhead, for anything that prints (HIMS-ORG-006; spec 4.1)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=LetterheadSerializer)
    def get(self, request):
        organization = get_deployment_organization()
        return Response(
            LetterheadSerializer(
                {
                    "display_name": organization.display_name,
                    "legal_name": organization.legal_name,
                    "lines": organization.letterhead_lines(),
                    "has_logo": bool(organization.logo),
                    "version": organization.version,
                }
            ).data
        )


class OrganizationLogoView(APIView):
    """Open the logo (anyone signed in; it has no public URL), or replace it."""

    parser_classes = [MultiPartParser]
    required_permissions = {"post": P.ORGANIZATION_MANAGE}

    def get_permissions(self):
        return [IsAuthenticated()] if self.request.method == "GET" else super().get_permissions()

    @extend_schema(responses={(200, "image/png"): bytes, (200, "image/jpeg"): bytes})
    def get(self, request):
        organization = get_deployment_organization()
        if not organization.logo:
            raise Http404
        try:
            stored = organization.logo.open("rb")
        except OSError:
            raise Http404 from None
        response = FileResponse(stored, content_type=logo_type(stored))
        response["Cache-Control"] = "private, no-cache"
        response["X-Content-Type-Options"] = "nosniff"
        return response

    @extend_schema(
        request={"multipart/form-data": LogoUploadSerializer},
        responses=OrganizationSerializer,
    )
    def post(self, request):
        serializer = LogoUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = set_logo(
            actor=request.user,
            organization_id=get_deployment_organization().pk,
            upload=serializer.validated_data["file"],
            request=request,
        )
        return Response(OrganizationSerializer(organization).data)


class OrganizationLogoRemoveView(APIView):
    required_permissions = {"post": P.ORGANIZATION_MANAGE}

    @extend_schema(request=None, responses=OrganizationSerializer)
    def post(self, request):
        organization = remove_logo(
            actor=request.user,
            organization_id=get_deployment_organization().pk,
            request=request,
        )
        return Response(OrganizationSerializer(organization).data)
