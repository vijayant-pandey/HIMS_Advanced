"""Audit log search and export for auditors (spec 13.4, 4.25; HIMS-AUD-001/003).

Only ``audit.view`` holders (auditors) can search; administrators cannot (separation of duties).
Every search and every export is itself written to the audit log.
"""

import csv
from datetime import datetime, time

from django.db.models import OuterRef, Q, Subquery
from django.http import StreamingHttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.access_control.catalog import P

from .. import catalog
from ..models import AuditEvent
from ..services import AuditAction, record_audit_event

# Most rows one export may contain; narrow the filters for more (keeps exports reviewable).
EXPORT_LIMIT = 5000


class AuditSearchSerializer(serializers.Serializer):
    """Search filters. Invalid values give a clear 400, never a server error."""

    actor_id = serializers.UUIDField(required=False)
    person = serializers.CharField(
        required=False, max_length=200, help_text="Part of a person's name or email."
    )
    action = serializers.CharField(required=False, max_length=100)
    category = serializers.ChoiceField(
        choices=sorted(set(catalog.CATEGORIES)),
        required=False,
        help_text="First part of the action, e.g. auth, access, staff, admin.",
    )
    resource_type = serializers.CharField(required=False, max_length=100)
    resource_id = serializers.CharField(required=False, max_length=64)
    outcome = serializers.ChoiceField(choices=AuditEvent.Outcome.choices, required=False)
    facility_id = serializers.UUIDField(required=False)
    request_id = serializers.CharField(
        required=False, max_length=64, help_text="Reference number shown on an error screen."
    )
    occurred_after = serializers.DateTimeField(required=False)
    occurred_before = serializers.DateTimeField(required=False)
    date_from = serializers.DateField(required=False, help_text="From this day (inclusive).")
    date_to = serializers.DateField(required=False, help_text="Up to this day (inclusive).")

    def filters(self) -> Q:
        data = self.validated_data
        q = Q()
        exact = {
            "actor_id": "actor_id",
            "action": "action",
            "resource_type": "resource_type",
            "resource_id": "resource_id",
            "outcome": "outcome",
            "facility_id": "facility_id",
        }
        for name, field in exact.items():
            if data.get(name) not in (None, ""):
                q &= Q(**{field: data[name]})
        if data.get("request_id"):
            q &= Q(request_id__iexact=data["request_id"].strip())
        if data.get("category"):
            q &= Q(action__startswith=f"{data['category']}.")
        if data.get("person"):
            from apps.identity.models import User

            term = data["person"].strip()
            ids = User.objects.filter(
                Q(display_name__icontains=term) | Q(email__icontains=term)
            ).values("pk")
            q &= Q(actor_id__in=ids)
        if data.get("occurred_after"):
            q &= Q(occurred_at__gte=data["occurred_after"])
        if data.get("occurred_before"):
            q &= Q(occurred_at__lt=data["occurred_before"])
        zone = timezone.get_current_timezone()
        if data.get("date_from"):
            q &= Q(occurred_at__gte=datetime.combine(data["date_from"], time.min, zone))
        if data.get("date_to"):
            q &= Q(occurred_at__lte=datetime.combine(data["date_to"], time.max, zone))
        return q


class AuditEventSerializer(serializers.ModelSerializer):
    action_label = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()
    actor_name = serializers.CharField(read_only=True, allow_null=True, default=None)
    actor_email = serializers.CharField(read_only=True, allow_null=True, default=None)
    facility_name = serializers.CharField(read_only=True, allow_null=True, default=None)

    def get_action_label(self, event) -> str:
        return catalog.label(event.action)

    def get_category(self, event) -> str:
        return catalog.category(event.action)

    class Meta:
        model = AuditEvent
        fields = [
            "id",
            "occurred_at",
            "facility_id",
            "facility_name",
            "actor_type",
            "actor_id",
            "actor_name",
            "actor_email",
            "action",
            "action_label",
            "category",
            "resource_type",
            "resource_id",
            "outcome",
            "reason",
            "request_id",
            "ip_address",
            "changes",
            "metadata",
        ]
        read_only_fields = fields


class AuditActionSerializer(serializers.Serializer):
    action = serializers.CharField()
    label = serializers.CharField()
    category = serializers.CharField()


def with_names(queryset):
    """Add who did it and where, in the same query (audit rows have no foreign keys)."""
    from apps.facilities.models import Facility
    from apps.identity.models import User

    user = User.objects.filter(pk=OuterRef("actor_id"))
    return queryset.annotate(
        actor_name=Subquery(user.values("display_name")[:1]),
        actor_email=Subquery(user.values("email")[:1]),
        facility_name=Subquery(
            Facility.objects.filter(pk=OuterRef("facility_id")).values("name")[:1]
        ),
    )


def _cell(value) -> str:
    """Spreadsheet-safe text: a leading = + - @ would otherwise run as a formula."""
    text = "" if value is None else str(value)
    return f"'{text}" if text[:1] in ("=", "+", "-", "@") else text


SEARCH_PARAMETERS = [
    OpenApiParameter(name, OpenApiTypes.STR, description=str(field.help_text or ""))
    for name, field in AuditSearchSerializer().fields.items()
]


class AuditEventViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Audit search for auditors. Searching and exporting the audit log are themselves audited."""

    serializer_class = AuditEventSerializer
    required_permissions = {"list": P.AUDIT_VIEW, "export": P.AUDIT_VIEW, "actions": P.AUDIT_VIEW}

    def _search(self) -> AuditSearchSerializer:
        search = AuditSearchSerializer(data=self.request.query_params)
        search.is_valid(raise_exception=True)
        return search

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return AuditEvent.objects.none()
        filters = self._search().filters()
        return with_names(AuditEvent.objects.filter(filters)).order_by("-occurred_at")

    def _record(self, action_name: str, **metadata) -> None:
        params = {
            k: v
            for k, v in self.request.query_params.items()
            if k in AuditSearchSerializer().fields
        }
        record_audit_event(
            action=action_name,
            resource_type="audit_event",
            request=self.request,
            metadata={"filters": params, **metadata},
        )

    @extend_schema(parameters=SEARCH_PARAMETERS)
    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        self._record(AuditAction.AUDIT_SEARCHED)
        return response

    @extend_schema(
        parameters=SEARCH_PARAMETERS,
        responses={(200, "text/csv"): OpenApiResponse(OpenApiTypes.STR, description="CSV file")},
    )
    @action(detail=False, methods=["get"])
    def export(self, request):
        """Download matching events as CSV (newest first, at most 5,000 rows)."""
        rows = list(self.get_queryset()[: EXPORT_LIMIT + 1])
        truncated = len(rows) > EXPORT_LIMIT
        rows = rows[:EXPORT_LIMIT]
        self._record(AuditAction.AUDIT_EXPORTED, rows=len(rows), truncated=truncated)

        class Echo:
            def write(self, value):
                return value

        writer = csv.writer(Echo())
        header = [
            "When (UTC)",
            "What happened",
            "Action code",
            "Outcome",
            "Who",
            "Email",
            "Facility",
            "Record type",
            "Record id",
            "Reason",
            "Reference number",
            "IP address",
        ]

        def lines():
            yield writer.writerow(header)
            for event in rows:
                yield writer.writerow(
                    [
                        _cell(value)
                        for value in (
                            event.occurred_at.isoformat(),
                            catalog.label(event.action),
                            event.action,
                            event.outcome,
                            event.actor_name or event.actor_type,
                            event.actor_email,
                            event.facility_name,
                            event.resource_type,
                            event.resource_id,
                            event.reason,
                            event.request_id,
                            event.ip_address,
                        )
                    ]
                )

        stamp = timezone.now().strftime("%Y%m%d-%H%M")
        response = StreamingHttpResponse(lines(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="audit-log-{stamp}.csv"'
        response["X-Export-Truncated"] = "true" if truncated else "false"
        return response

    @extend_schema(responses=AuditActionSerializer(many=True))
    @action(detail=False, methods=["get"], pagination_class=None)
    def actions(self, request):
        """Every known event type with a plain-language name, for the filter list."""
        return Response(AuditActionSerializer(catalog.all_actions(), many=True).data)
