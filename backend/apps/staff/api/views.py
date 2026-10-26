from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.access_control.catalog import P
from apps.identity.invitations import issue_invitation
from common.exceptions import ConflictError
from common.idempotency.decorators import idempotent

from .. import services
from ..models import QualificationType, Specialty, StaffCredential, StaffMember
from .serializers import (
    CredentialVerificationSerializer,
    InvitationSentSerializer,
    QualificationTypeSerializer,
    SpecialtySerializer,
    StaffCredentialSerializer,
    StaffDepartmentAssignmentSerializer,
    StaffMemberCreateSerializer,
    StaffMemberDetailSerializer,
    StaffMemberSerializer,
    StaffMemberUpdateSerializer,
    StaffQualificationSerializer,
)


class SpecialtyViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = SpecialtySerializer
    queryset = Specialty.objects.filter(is_active=True)
    pagination_class = None
    required_permissions = {"list": P.STAFF_VIEW}


class QualificationTypeViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = QualificationTypeSerializer
    queryset = QualificationType.objects.filter(is_active=True)
    pagination_class = None
    required_permissions = {"list": P.STAFF_VIEW}


class StaffMemberViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    required_permissions = {
        "list": P.STAFF_VIEW,
        "retrieve": P.STAFF_VIEW,
        "create": P.STAFF_MANAGE,
        "partial_update": P.STAFF_MANAGE,
        "add_department_assignment": P.STAFF_MANAGE,
        "add_qualification": P.STAFF_MANAGE,
        "add_credential": P.STAFF_MANAGE,
        "send_invitation": P.STAFF_MANAGE,
    }
    http_method_names = ["get", "post", "patch", "head"]

    def get_serializer_class(self):
        return StaffMemberDetailSerializer if self.action == "retrieve" else StaffMemberSerializer

    def get_queryset(self):
        queryset = StaffMember.objects.select_related("user")
        if self.action == "retrieve":
            queryset = queryset.prefetch_related(
                "department_assignments", "qualifications", "credentials"
            )
        search = self.request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(given_name__icontains=search)
                | Q(family_name__icontains=search)
                | Q(employee_number__iexact=search)
            )
        staff_type = self.request.query_params.get("staff_type")
        if staff_type:
            queryset = queryset.filter(staff_type=staff_type)
        return queryset

    @extend_schema(
        parameters=[
            OpenApiParameter("search", str, description="Name contains, or exact employee number"),
            OpenApiParameter("staff_type", str),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=StaffMemberCreateSerializer, responses={201: StaffMemberSerializer})
    @idempotent("staff.create")
    def create(self, request):
        serializer = StaffMemberCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        staff = services.create_staff_member(
            actor=request.user, email=data.pop("email", None), request=request, **data
        )
        return Response(StaffMemberSerializer(staff).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=StaffMemberUpdateSerializer, responses=StaffMemberSerializer)
    def partial_update(self, request, pk=None):
        staff = self.get_object()
        serializer = StaffMemberUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        staff = services.update_staff_member(
            actor=request.user,
            staff_id=staff.pk,
            version=data.pop("version"),
            request=request,
            **data,
        )
        return Response(StaffMemberSerializer(staff).data)

    @extend_schema(
        request=StaffDepartmentAssignmentSerializer,
        responses={201: StaffDepartmentAssignmentSerializer},
    )
    @action(detail=True, methods=["post"], url_path="department-assignments")
    @idempotent("staff.department_assignments.create")
    def add_department_assignment(self, request, pk=None):
        staff = self.get_object()
        serializer = StaffDepartmentAssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        department = data.pop("department")
        assignment = services.add_department_assignment(
            actor=request.user, staff=staff, department=department, request=request, **data
        )
        return Response(
            StaffDepartmentAssignmentSerializer(assignment).data, status=status.HTTP_201_CREATED
        )

    @extend_schema(
        request=StaffQualificationSerializer, responses={201: StaffQualificationSerializer}
    )
    @action(detail=True, methods=["post"], url_path="qualifications")
    @idempotent("staff.qualifications.create")
    def add_qualification(self, request, pk=None):
        staff = self.get_object()
        serializer = StaffQualificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        qualification = services.add_qualification(
            actor=request.user, staff=staff, request=request, **serializer.validated_data
        )
        return Response(
            StaffQualificationSerializer(qualification).data, status=status.HTTP_201_CREATED
        )

    @extend_schema(request=StaffCredentialSerializer, responses={201: StaffCredentialSerializer})
    @action(detail=True, methods=["post"], url_path="credentials")
    @idempotent("staff.credentials.create")
    def add_credential(self, request, pk=None):
        staff = self.get_object()
        serializer = StaffCredentialSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        credential = services.add_credential(
            actor=request.user, staff=staff, request=request, **serializer.validated_data
        )
        return Response(StaffCredentialSerializer(credential).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses={202: InvitationSentSerializer})
    @action(detail=True, methods=["post"], url_path="invitation")
    def send_invitation(self, request, pk=None):
        """(Re)send the account activation email. Any earlier open invitation stops working."""
        staff = self.get_object()
        if staff.user_id is None:
            raise ConflictError(
                "This staff member has no login account. Add an email first.", code="NO_LOGIN"
            )
        invitation = issue_invitation(user=staff.user, actor=request.user, request=request)
        return Response(
            InvitationSentSerializer(
                {"email": staff.user.email, "expires_at": invitation.expires_at}
            ).data,
            status=status.HTTP_202_ACCEPTED,
        )


class StaffCredentialViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = StaffCredentialSerializer
    queryset = StaffCredential.objects.all()
    required_permissions = {"retrieve": P.STAFF_VIEW, "verify": P.STAFF_CREDENTIALS_VERIFY}

    @extend_schema(request=CredentialVerificationSerializer, responses=StaffCredentialSerializer)
    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        credential = self.get_object()
        serializer = CredentialVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        credential = services.verify_credential(
            actor=request.user,
            credential_id=credential.pk,
            request=request,
            **serializer.validated_data,
        )
        return Response(StaffCredentialSerializer(credential).data)
