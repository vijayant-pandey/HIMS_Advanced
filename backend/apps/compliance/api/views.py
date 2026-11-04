"""Compliance registers API (spec 13, 23, 26.7; HIMS-COMP).

Seeing the registers needs ``compliance.view``; changing them needs ``compliance.manage``. Anyone
signed in may report a security incident (HIPAA 164.308(a)(5)/(6): staff must be able to report)
but only compliance staff can read the log.
"""

from django.db.models import Count, Q
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access_control.catalog import P
from apps.organizations.models import Organization
from common.idempotency.decorators import idempotent

from .. import incidents, services
from ..models import ComplianceRequirement, IncidentNotification, RiskEntry, SecurityIncident


def _deployment_country() -> str:
    organization = Organization.objects.only("country").first()
    return organization.country if organization else ""


# --- Requirements ---------------------------------------------------------------------------------


class ComplianceRequirementSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    reviewed_by_name = serializers.CharField(
        source="reviewed_by.display_name", read_only=True, default=None, allow_null=True
    )

    class Meta:
        model = ComplianceRequirement
        fields = [
            "id",
            "code",
            "jurisdiction",
            "regulation",
            "citation",
            "title",
            "summary",
            "hims_support",
            "status",
            "status_label",
            "owner",
            "evidence",
            "next_review_on",
            "reviewed_by_name",
            "reviewed_at",
            "version",
        ]
        read_only_fields = fields


class RequirementUpdateSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    status = serializers.ChoiceField(choices=ComplianceRequirement.Status.choices, required=False)
    owner = serializers.CharField(max_length=150, required=False, allow_blank=True)
    evidence = serializers.CharField(required=False, allow_blank=True)
    next_review_on = serializers.DateField(required=False, allow_null=True)


class ComplianceRequirementViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """The requirements that apply to this hospital's country."""

    serializer_class = ComplianceRequirementSerializer
    pagination_class = None
    required_permissions = {
        "list": P.COMPLIANCE_VIEW,
        "retrieve": P.COMPLIANCE_VIEW,
        "partial_update": P.COMPLIANCE_MANAGE,
    }

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # generating the API file: no database
            return ComplianceRequirement.objects.none()
        return ComplianceRequirement.objects.filter(
            is_active=True, jurisdiction__in=("ALL", _deployment_country())
        ).select_related("reviewed_by")

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "status", str, enum=[c for c, _ in ComplianceRequirement.Status.choices]
            ),
            OpenApiParameter("search", str, description="Part of the code, title or law"),
        ]
    )
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        if request.query_params.get("status"):
            queryset = queryset.filter(status=request.query_params["status"])
        term = request.query_params.get("search", "").strip()
        if term:
            queryset = queryset.filter(
                Q(code__icontains=term) | Q(title__icontains=term) | Q(regulation__icontains=term)
            )
        return Response(self.get_serializer(queryset, many=True).data)

    @extend_schema(request=RequirementUpdateSerializer, responses=ComplianceRequirementSerializer)
    def partial_update(self, request, pk=None):
        serializer = RequirementUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        item = services.update_requirement(
            actor=request.user,
            requirement_id=self.get_object().pk,
            version=data.pop("version"),
            request=request,
            **data,
        )
        return Response(ComplianceRequirementSerializer(item).data)


# --- Risks ----------------------------------------------------------------------------------------


class RiskEntrySerializer(serializers.ModelSerializer):
    score = serializers.IntegerField(read_only=True, help_text="Likelihood x impact, 1 to 25.")
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    treatment_label = serializers.CharField(source="get_treatment_display", read_only=True)

    class Meta:
        model = RiskEntry
        fields = [
            "id",
            "code",
            "title",
            "description",
            "category",
            "likelihood",
            "impact",
            "score",
            "treatment",
            "treatment_label",
            "mitigation",
            "status",
            "status_label",
            "owner",
            "review_on",
            "acceptance_reason",
            "version",
        ]
        read_only_fields = fields


class RiskWriteSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200, required=False)
    description = serializers.CharField(required=False)
    category = serializers.CharField(max_length=40, required=False)
    likelihood = serializers.IntegerField(min_value=1, max_value=5, required=False)
    impact = serializers.IntegerField(min_value=1, max_value=5, required=False)
    treatment = serializers.ChoiceField(choices=RiskEntry.Treatment.choices, required=False)
    mitigation = serializers.CharField(required=False, allow_blank=True)
    status = serializers.ChoiceField(choices=RiskEntry.Status.choices, required=False)
    owner = serializers.CharField(max_length=150, required=False, allow_blank=True)
    review_on = serializers.DateField(required=False, allow_null=True)
    acceptance_reason = serializers.CharField(required=False, allow_blank=True)


class RiskCreateSerializer(RiskWriteSerializer):
    title = serializers.CharField(max_length=200)
    description = serializers.CharField()
    category = serializers.CharField(max_length=40)


class RiskUpdateSerializer(RiskWriteSerializer):
    version = serializers.IntegerField(min_value=1)


class RiskEntryViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = RiskEntrySerializer
    pagination_class = None
    queryset = RiskEntry.objects.all()
    required_permissions = {
        "list": P.COMPLIANCE_VIEW,
        "retrieve": P.COMPLIANCE_VIEW,
        "create": P.COMPLIANCE_MANAGE,
        "partial_update": P.COMPLIANCE_MANAGE,
    }

    @extend_schema(request=RiskCreateSerializer, responses={201: RiskEntrySerializer})
    @idempotent("compliance_risks.create")
    def create(self, request):
        serializer = RiskCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        risk = services.create_risk(
            actor=request.user, request=request, **serializer.validated_data
        )
        return Response(RiskEntrySerializer(risk).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=RiskUpdateSerializer, responses=RiskEntrySerializer)
    def partial_update(self, request, pk=None):
        serializer = RiskUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        risk = services.update_risk(
            actor=request.user,
            risk_id=self.get_object().pk,
            version=data.pop("version"),
            request=request,
            **data,
        )
        return Response(RiskEntrySerializer(risk).data)


# --- Incidents ------------------------------------------------------------------------------------


class IncidentNotificationSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    done_by_name = serializers.CharField(
        source="done_by.display_name", read_only=True, default=None, allow_null=True
    )
    is_overdue = serializers.SerializerMethodField()

    def get_is_overdue(self, row) -> bool:
        return row.status == IncidentNotification.Status.PENDING and row.due_at <= timezone.now()

    class Meta:
        model = IncidentNotification
        fields = [
            "id",
            "kind",
            "kind_label",
            "due_at",
            "status",
            "status_label",
            "is_overdue",
            "done_at",
            "done_by_name",
            "reference",
            "note",
        ]
        read_only_fields = fields


class SecurityIncidentSerializer(serializers.ModelSerializer):
    severity_label = serializers.CharField(source="get_severity_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    reported_by_name = serializers.CharField(
        source="reported_by.display_name", read_only=True, default=None, allow_null=True
    )
    notifications = IncidentNotificationSerializer(many=True, read_only=True)

    class Meta:
        model = SecurityIncident
        fields = [
            "id",
            "title",
            "description",
            "severity",
            "severity_label",
            "status",
            "status_label",
            "detected_at",
            "occurred_at",
            "personal_data_affected",
            "people_affected",
            "actions_taken",
            "closure_summary",
            "closed_at",
            "reported_by_name",
            "notifications",
            "version",
        ]
        read_only_fields = fields


class IncidentReportSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(help_text="What happened. No patient details.")
    severity = serializers.ChoiceField(
        choices=SecurityIncident.Severity.choices, required=False, default="medium"
    )
    personal_data_affected = serializers.BooleanField(required=False, default=False)
    people_affected = serializers.IntegerField(min_value=0, required=False, allow_null=True)


class IncidentReceiptSerializer(serializers.Serializer):
    """What the person reporting gets back (they may not be allowed to read the log)."""

    id = serializers.UUIDField()
    title = serializers.CharField()
    detected_at = serializers.DateTimeField()


class IncidentUpdateSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    severity = serializers.ChoiceField(choices=SecurityIncident.Severity.choices, required=False)
    status = serializers.ChoiceField(choices=SecurityIncident.Status.choices, required=False)
    detected_at = serializers.DateTimeField(required=False)
    occurred_at = serializers.DateTimeField(required=False, allow_null=True)
    personal_data_affected = serializers.BooleanField(required=False)
    people_affected = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    actions_taken = serializers.CharField(required=False, allow_blank=True)
    closure_summary = serializers.CharField(required=False, allow_blank=True)


class NotificationRecordSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=[
            IncidentNotification.Status.DONE,
            IncidentNotification.Status.NOT_REQUIRED,
        ]
    )
    reference = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    note = serializers.CharField(required=False, allow_blank=True, default="")


class SecurityIncidentViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    serializer_class = SecurityIncidentSerializer
    pagination_class = None
    required_permissions = {
        "list": P.COMPLIANCE_VIEW,
        "retrieve": P.COMPLIANCE_VIEW,
        "partial_update": P.COMPLIANCE_MANAGE,
        "record_notification": P.COMPLIANCE_MANAGE,
    }

    def get_permissions(self):
        if self.action == "create":
            return [IsAuthenticated()]  # every member of staff can report
        return super().get_permissions()

    def get_queryset(self):
        return SecurityIncident.objects.select_related("reported_by").prefetch_related(
            "notifications__done_by"
        )

    @extend_schema(
        parameters=[OpenApiParameter("open", str, description="'true' = not closed yet")],
    )
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        if request.query_params.get("open") == "true":
            queryset = queryset.exclude(status=SecurityIncident.Status.CLOSED)
        return Response(self.get_serializer(queryset[:200], many=True).data)

    @extend_schema(request=IncidentReportSerializer, responses={201: IncidentReceiptSerializer})
    @idempotent("security_incidents.create")
    def create(self, request):
        serializer = IncidentReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        incident = incidents.report_incident(
            actor=request.user, request=request, **serializer.validated_data
        )
        return Response(IncidentReceiptSerializer(incident).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=IncidentUpdateSerializer, responses=SecurityIncidentSerializer)
    def partial_update(self, request, pk=None):
        serializer = IncidentUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        incident = incidents.update_incident(
            actor=request.user,
            incident_id=self.get_object().pk,
            version=data.pop("version"),
            request=request,
            **data,
        )
        return Response(SecurityIncidentSerializer(self.get_queryset().get(pk=incident.pk)).data)

    @extend_schema(
        request=NotificationRecordSerializer,
        responses=SecurityIncidentSerializer,
        parameters=[OpenApiParameter("notification_id", OpenApiTypes.UUID, OpenApiParameter.PATH)],
    )
    @action(detail=True, methods=["post"], url_path=r"notifications/(?P<notification_id>[^/.]+)")
    def record_notification(self, request, pk=None, notification_id=None):
        incident = self.get_object()
        row = incident.notifications.filter(pk=notification_id).first()
        if row is None:
            raise serializers.ValidationError({"notification": "Not part of this incident."})
        serializer = NotificationRecordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        incidents.record_notification(
            actor=request.user, notification_id=row.pk, request=request, **serializer.validated_data
        )
        return Response(SecurityIncidentSerializer(self.get_queryset().get(pk=incident.pk)).data)


# --- Summary --------------------------------------------------------------------------------------


class ComplianceSummarySerializer(serializers.Serializer):
    country = serializers.CharField()
    requirements_total = serializers.IntegerField()
    requirements_by_status = serializers.DictField(child=serializers.IntegerField())
    risks_open = serializers.IntegerField()
    risks_high = serializers.IntegerField(help_text="Open risks scoring 15 or more.")
    incidents_open = serializers.IntegerField()
    notifications_overdue = serializers.IntegerField()


class ComplianceSummaryView(APIView):
    required_permissions = {"get": P.COMPLIANCE_VIEW}

    @extend_schema(responses=ComplianceSummarySerializer)
    def get(self, request):
        country = _deployment_country()
        requirements = ComplianceRequirement.objects.filter(
            is_active=True, jurisdiction__in=("ALL", country)
        )
        by_status = dict(requirements.order_by().values_list("status").annotate(total=Count("id")))
        open_risks = [
            risk
            for risk in RiskEntry.objects.exclude(status=RiskEntry.Status.CLOSED)
            if risk.status != RiskEntry.Status.ACCEPTED
        ]
        return Response(
            {
                "country": country,
                "requirements_total": requirements.count(),
                "requirements_by_status": by_status,
                "risks_open": len(open_risks),
                "risks_high": sum(1 for risk in open_risks if risk.score >= 15),
                "incidents_open": SecurityIncident.objects.exclude(
                    status=SecurityIncident.Status.CLOSED
                ).count(),
                "notifications_overdue": IncidentNotification.objects.filter(
                    status=IncidentNotification.Status.PENDING, due_at__lte=timezone.now()
                ).count(),
            }
        )
