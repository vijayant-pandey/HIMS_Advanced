from django.db.models import Prefetch, Q
from django.http import FileResponse, Http404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from apps.access_control.catalog import P
from apps.facilities.closing import current_postings_q
from apps.identity.invitations import issue_invitation
from common.exceptions import ConflictError
from common.idempotency.decorators import idempotent

from .. import catalogs, documents, expiry, services
from ..models import (
    CredentialExpiryAlert,
    Designation,
    QualificationType,
    Specialty,
    StaffCredential,
    StaffDocument,
    StaffMember,
)
from .serializers import (
    ArchiveSerializer,
    CredentialVerificationSerializer,
    DesignationCreateSerializer,
    DesignationSerializer,
    DesignationUpdateSerializer,
    EndAssignmentSerializer,
    ExpiringCredentialSerializer,
    InvitationSentSerializer,
    QualificationTypeCreateSerializer,
    QualificationTypeSerializer,
    QualificationTypeUpdateSerializer,
    SpecialtyCreateSerializer,
    SpecialtySerializer,
    SpecialtyUpdateSerializer,
    StaffCredentialSerializer,
    StaffDepartmentAssignmentSerializer,
    StaffDocumentSerializer,
    StaffDocumentUploadSerializer,
    StaffMemberCreateSerializer,
    StaffMemberDetailSerializer,
    StaffMemberSerializer,
    StaffMemberUpdateSerializer,
    StaffQualificationSerializer,
)


class _CatalogViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """A hospital-maintained catalog (HIMS-STAFF-010): list for drop-downs (active entries) or,
    with ?include_inactive=true, everything for the catalog screen; add and change entries."""

    kind = ""
    model = None
    create_serializer = None
    update_serializer = None
    pagination_class = None
    required_permissions = {
        "list": P.STAFF_VIEW,
        "create": P.CATALOGS_MANAGE,
        "partial_update": P.CATALOGS_MANAGE,
    }
    http_method_names = ["get", "post", "patch", "head"]

    def get_queryset(self):
        queryset = self.model.objects.all()
        # Drop-down lists show active entries only; switched-off ones stay editable (and can be
        # switched back on) and are listed with ?include_inactive=true.
        listing_active_only = self.action == "list" and (
            self.request.query_params.get("include_inactive") != "true"
        )
        return queryset.filter(is_active=True) if listing_active_only else queryset

    def create(self, request):
        serializer = self.create_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = catalogs.create_catalog_item(
            self.kind, actor=request.user, request=request, **serializer.validated_data
        )
        return Response(self.get_serializer(item).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        item = self.get_object()
        serializer = self.update_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        item = catalogs.update_catalog_item(
            self.kind,
            actor=request.user,
            item_id=item.pk,
            version=data.pop("version"),
            request=request,
            **data,
        )
        return Response(self.get_serializer(item).data)


INCLUDE_INACTIVE = OpenApiParameter(
    "include_inactive", str, description="'true' = also switched-off entries"
)


class DesignationViewSet(_CatalogViewSet):
    """Job-title catalog (junior to senior). Filter with ?country=IN|US and ?category=."""

    kind = "designation"
    model = Designation
    serializer_class = DesignationSerializer
    create_serializer = DesignationCreateSerializer
    update_serializer = DesignationUpdateSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        country = self.request.query_params.get("country")
        if country:
            queryset = queryset.filter(country__in=[country, ""])
        category = self.request.query_params.get("category")
        if category:
            queryset = queryset.filter(category=category)
        return queryset

    @extend_schema(
        parameters=[
            OpenApiParameter("country", str, description="IN or US (shared titles included)"),
            OpenApiParameter("category", str),
            INCLUDE_INACTIVE,
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=DesignationCreateSerializer, responses={201: DesignationSerializer})
    @idempotent("catalogs.designations.create")
    def create(self, request):
        return super().create(request)

    @extend_schema(request=DesignationUpdateSerializer, responses=DesignationSerializer)
    def partial_update(self, request, pk=None):
        return super().partial_update(request, pk)


class SpecialtyViewSet(_CatalogViewSet):
    kind = "specialty"
    model = Specialty
    serializer_class = SpecialtySerializer
    create_serializer = SpecialtyCreateSerializer
    update_serializer = SpecialtyUpdateSerializer

    @extend_schema(parameters=[INCLUDE_INACTIVE])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=SpecialtyCreateSerializer, responses={201: SpecialtySerializer})
    @idempotent("catalogs.specialties.create")
    def create(self, request):
        return super().create(request)

    @extend_schema(request=SpecialtyUpdateSerializer, responses=SpecialtySerializer)
    def partial_update(self, request, pk=None):
        return super().partial_update(request, pk)


class QualificationTypeViewSet(_CatalogViewSet):
    kind = "qualification_type"
    model = QualificationType
    serializer_class = QualificationTypeSerializer
    create_serializer = QualificationTypeCreateSerializer
    update_serializer = QualificationTypeUpdateSerializer

    @extend_schema(parameters=[INCLUDE_INACTIVE])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        request=QualificationTypeCreateSerializer, responses={201: QualificationTypeSerializer}
    )
    @idempotent("catalogs.qualification_types.create")
    def create(self, request):
        return super().create(request)

    @extend_schema(request=QualificationTypeUpdateSerializer, responses=QualificationTypeSerializer)
    def partial_update(self, request, pk=None):
        return super().partial_update(request, pk)


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
        "end_department_assignment": P.STAFF_MANAGE,
        "verify_qualification": P.STAFF_CREDENTIALS_VERIFY,
        "documents": P.STAFF_VIEW,
        "upload_document": P.STAFF_MANAGE,
    }
    http_method_names = ["get", "post", "patch", "head"]

    def get_serializer_class(self):
        return StaffMemberDetailSerializer if self.action == "retrieve" else StaffMemberSerializer

    def get_parsers(self):
        # File uploads arrive as multipart form data; everything else stays JSON-only.
        if getattr(self, "action", None) == "upload_document" or (
            self.request is not None
            and self.request.method == "POST"
            and self.request.path.rstrip("/").endswith("/documents")
        ):
            return [MultiPartParser(), FormParser()]
        return super().get_parsers()

    def get_queryset(self):
        queryset = StaffMember.objects.select_related("user")
        if self.action == "retrieve":
            queryset = queryset.prefetch_related(
                "department_assignments__designation",
                "department_assignments__department__facility",
                "department_assignments__specialty",
                "qualifications__qualification_type",
                "qualifications__specialty",
                "qualifications__verified_by",
                "credentials__verified_by",
                Prefetch("documents", StaffDocument.objects.select_related("uploaded_by")),
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
        employment_status = self.request.query_params.get("employment_status")
        if employment_status:
            queryset = queryset.filter(employment_status=employment_status)
        department = self.request.query_params.get("department")
        if department:
            # People posted there now (or starting later), as counted on the Departments page.
            queryset = queryset.filter(
                current_postings_q("department_assignments__"),
                department_assignments__department_id=department,
            ).distinct()
        return queryset

    @extend_schema(
        parameters=[
            OpenApiParameter("search", str, description="Name contains, or exact employee number"),
            OpenApiParameter("staff_type", str),
            OpenApiParameter("employment_status", str),
            OpenApiParameter("department", str, description="Posted in this department now"),
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

    @extend_schema(request=EndAssignmentSerializer, responses=StaffDepartmentAssignmentSerializer)
    @action(
        detail=True,
        methods=["post"],
        url_path=r"department-assignments/(?P<assignment_id>[0-9a-f-]+)/end",
    )
    def end_department_assignment(self, request, pk=None, assignment_id=None):
        """End a posting (transfer, resignation, end of rotation). History is kept."""
        staff = self.get_object()
        serializer = EndAssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assignment = services.end_department_assignment(
            actor=request.user,
            staff=staff,
            assignment_id=_existing(staff.department_assignments, assignment_id),
            request=request,
            **serializer.validated_data,
        )
        return Response(StaffDepartmentAssignmentSerializer(assignment).data)

    @extend_schema(request=CredentialVerificationSerializer, responses=StaffQualificationSerializer)
    @action(
        detail=True,
        methods=["post"],
        url_path=r"qualifications/(?P<qualification_id>[0-9a-f-]+)/verify",
    )
    def verify_qualification(self, request, pk=None, qualification_id=None):
        """Mark a qualification as checked against the original certificate, or rejected."""
        staff = self.get_object()
        serializer = CredentialVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        qualification = services.verify_qualification(
            actor=request.user,
            staff=staff,
            qualification_id=_existing(staff.qualifications, qualification_id),
            request=request,
            **serializer.validated_data,
        )
        return Response(StaffQualificationSerializer(qualification).data)

    @extend_schema(responses=StaffDocumentSerializer(many=True))
    @action(detail=True, methods=["get"])
    def documents(self, request, pk=None):
        """This person's licence and qualification documents (archived ones included)."""
        staff = self.get_object()
        rows = staff.documents.select_related("uploaded_by")
        return Response(StaffDocumentSerializer(rows, many=True).data)

    @extend_schema(
        request={"multipart/form-data": StaffDocumentUploadSerializer},
        responses={201: StaffDocumentSerializer},
    )
    @documents.mapping.post
    def upload_document(self, request, pk=None):
        """Attach a PDF/JPG/PNG to one of this person's licences or qualifications."""
        staff = self.get_object()
        serializer = StaffDocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        credential = qualification = None
        if data.get("credential"):
            credential = staff.credentials.filter(pk=data["credential"]).first()
            if credential is None:
                raise Http404
        else:
            qualification = staff.qualifications.filter(pk=data["qualification"]).first()
            if qualification is None:
                raise Http404
        document = documents.upload_document(
            actor=request.user,
            staff=staff,
            upload=data["file"],
            credential=credential,
            qualification=qualification,
            request=request,
        )
        return Response(StaffDocumentSerializer(document).data, status=status.HTTP_201_CREATED)

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


def _existing(related_manager, item_id):
    """The id if it belongs to this staff member, else 404 (never another person's record)."""
    if not related_manager.filter(pk=item_id).exists():
        raise Http404
    return item_id


class StaffCredentialViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = StaffCredentialSerializer
    queryset = StaffCredential.objects.all()
    required_permissions = {
        "retrieve": P.STAFF_VIEW,
        "verify": P.STAFF_CREDENTIALS_VERIFY,
        "expiring": P.STAFF_VIEW,
    }

    @extend_schema(
        parameters=[
            OpenApiParameter("within", int, description="Days ahead to include (default 60)"),
            OpenApiParameter("include_expired", str, description="'false' hides expired"),
        ],
        responses=ExpiringCredentialSerializer(many=True),
    )
    @action(detail=False, methods=["get"], pagination_class=None)
    def expiring(self, request):
        """Licences of working staff that are expired or expire soon, soonest first."""
        try:
            within = max(0, min(int(request.query_params.get("within", 60)), 365))
        except ValueError:
            within = 60
        rows = expiry.watched_credentials(within_days=within).prefetch_related(
            Prefetch("expiry_alerts", CredentialExpiryAlert.objects.all())
        )
        if request.query_params.get("include_expired") == "false":
            rows = rows.filter(expires_at__gte=timezone.localdate())
        return Response(ExpiringCredentialSerializer(rows[:500], many=True).data)

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


class StaffDocumentViewSet(viewsets.GenericViewSet):
    """Open/download or archive one document. Files have no public URL (ADR-020)."""

    queryset = StaffDocument.objects.select_related("staff")
    serializer_class = StaffDocumentSerializer
    required_permissions = {"download": P.STAFF_VIEW, "archive": P.STAFF_MANAGE}

    @extend_schema(
        parameters=[OpenApiParameter("inline", str, description="'true' = open in the browser")],
        responses={(200, "application/octet-stream"): bytes},
    )
    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        document = self.get_object()
        documents.record_download(actor=request.user, document=document, request=request)
        response = FileResponse(
            document.file.open("rb"),
            content_type=document.content_type,
            as_attachment=request.query_params.get("inline") != "true",
            filename=document.original_name,
        )
        # The file is shown as-is: no scripts, no caching of personal documents.
        response["Content-Security-Policy"] = "default-src 'none'; img-src 'self'; sandbox"
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response

    @extend_schema(request=ArchiveSerializer, responses=StaffDocumentSerializer)
    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        """A wrong or outdated file is archived with a reason, never deleted."""
        document = self.get_object()
        serializer = ArchiveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document = documents.archive_document(
            actor=request.user,
            document_id=document.pk,
            reason=serializer.validated_data["reason"],
            request=request,
        )
        return Response(StaffDocumentSerializer(document).data)
