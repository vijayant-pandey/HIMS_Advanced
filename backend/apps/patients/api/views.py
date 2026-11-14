"""Patient API (HIMS-PAT-001; P0 part 06 section 2).

Patients belong to the whole hospital (one MRN in every facility), so a grant anywhere lets a
person look patients up and open them; registering checks the facility of registration. Every
opening of a record and every MRN look-up is in the audit log (spec 13.4); the list itself shows
only the minimum (P0 part 01 section 2).

The chart (HIMS-PAT-005): the record carries its header (allergy status, alerts) and the
``history`` action lists who opened and changed it, for medical records (``patients.history``).

Restricted records (HIMS-PAT-006; D23, D14): hidden from the list and from search for people
without ``patients.restricted`` (an exact MRN shows a row with nothing about the patient), and
every action on one is refused (``RESTRICTED_RECORD``) unless the person holds that permission or
has emergency access to it (``emergency-access``, 4 hours, reviewed by medical records under
``/patient-emergency-access/``).

Patient search (HIMS-PAT-002; spec endpoint ``GET /api/v1/patients/?search=``): one box for the
MRN, a phone number, an ID number or a name (similar spelling, any order, earlier names too),
with optional sex and age (a date of birth would travel in the address, so it is not a filter).
At most 50 results, best match first; ``count`` says
how many matched, so the screen can ask for more detail when it is more than 50. Every search is
audited with its kind and the number of results, never what was typed.
"""

from datetime import timedelta

from django.db.models import Prefetch
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.access_control.catalog import P
from apps.access_control.selectors import check_permission
from apps.audit.services import AuditAction, record_audit_event
from apps.features.catalog import F
from apps.features.services import require_enabled
from apps.organizations.selectors import get_deployment_organization
from common.idempotency.decorators import idempotent
from common.pagination import StandardPagination
from common.permissions import ANY_GRANT

from .. import chart, identifiers, restricted, search, services
from ..models import (
    UNIQUE_IDENTIFIER_KINDS,
    EmergencyAccess,
    Patient,
    PatientConsent,
    PatientContact,
    PatientIdentifier,
    PatientRelationship,
)
from .serializers import (
    ConsentCreateSerializer,
    ConsentSerializer,
    ContactCreateSerializer,
    ContactSerializer,
    ContactUpdateSerializer,
    EmergencyAccessOpenSerializer,
    EmergencyAccessReviewSerializer,
    EmergencyAccessSerializer,
    IdentifierEndSerializer,
    IdentifierInputSerializer,
    IdentifierSerializer,
    OwnEmergencyAccessSerializer,
    PatientDetailSerializer,
    PatientHistoryEventSerializer,
    PatientListSerializer,
    PatientRegisterSerializer,
    PatientSearchQuerySerializer,
    PatientUpdateSerializer,
    RegistrationOptionsSerializer,
    RelationshipCreateSerializer,
    RelationshipSerializer,
    RelationshipUpdateSerializer,
    RestrictedOpeningSerializer,
    RestrictionSerializer,
)

ADDRESS_FIELDS = (
    "address_line1",
    "address_line2",
    "city",
    "district",
    "state",
    "postal_code",
    "country",
)
REGISTRATION_EXTRAS = (
    "facility",
    "mobile",
    "alternate_phone",
    "email",
    "relationships",
    "identifiers",
    "privacy_notice",
    "sms_consent",
    "email_consent",
    "consent_method",
    "no_guardian_reason",
    *ADDRESS_FIELDS,
)


def _mobiles():
    """The active mobiles, main one first: the list shows its last 4 digits."""
    return PatientContact.objects.filter(kind="mobile", is_active=True).order_by(
        "-is_primary", "created_at"
    )


class PatientPagination(StandardPagination):
    max_page_size = 50  # P0 part 01 §2: at most 50 results


class PatientViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_scope = ANY_GRANT
    pagination_class = PatientPagination
    required_permissions = {
        "list": P.PATIENTS_SEARCH,
        "retrieve": P.PATIENTS_VIEW,
        "create": P.PATIENTS_REGISTER,
        "partial_update": P.PATIENTS_REGISTER,
        "registration_options": P.PATIENTS_REGISTER,
        "add_contact": P.PATIENTS_REGISTER,
        "update_contact": P.PATIENTS_REGISTER,
        "add_relationship": P.PATIENTS_REGISTER,
        "update_relationship": P.PATIENTS_REGISTER,
        "add_identifier": P.PATIENTS_REGISTER,
        "end_identifier": P.PATIENTS_REGISTER,
        "record_consent": P.PATIENTS_REGISTER,
        "history": P.PATIENTS_HISTORY,
        "restriction": P.PATIENTS_RESTRICTED,
        "emergency_access": P.EMERGENCY_ACCESS,
        "end_emergency_access": P.EMERGENCY_ACCESS,
        "restricted_openings": P.PATIENTS_RECORDS_CORRECT,
    }
    http_method_names = ["get", "post", "patch", "head"]
    opening = None

    def _hide_restricted(self) -> bool:
        return not restricted.may_see_restricted(self.request.user)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Patient.objects.none()
        queryset = Patient.objects.select_related("registered_facility")
        if self.action == "list":
            queryset = queryset.prefetch_related(Prefetch("contacts", queryset=_mobiles()))
            facility = self.request.query_params.get("facility")
            if facility:
                queryset = queryset.filter(registered_facility_id=facility)
            mrn = (self.request.query_params.get("mrn") or "").strip().upper()
            if mrn:
                queryset = queryset.filter(mrn=mrn)
            elif self._hide_restricted():
                queryset = queryset.filter(is_restricted=False)
        return queryset.order_by("-created_at")

    def get_serializer_class(self):
        return PatientListSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if getattr(self, "swagger_fake_view", False):
            return context
        return {**context, "hide_restricted": self._hide_restricted()}

    def _patient(self, pk) -> Patient:
        queryset = Patient.objects.select_related(
            "registered_facility", "registered_by", "merged_into"
        ).prefetch_related(
            "contacts",
            Prefetch(
                "relationships",
                queryset=PatientRelationship.objects.select_related("related_patient"),
            ),
            Prefetch("identifiers", queryset=PatientIdentifier.objects.select_related("ended_by")),
            Prefetch(
                "consents",
                queryset=PatientConsent.objects.select_related("recorded_by").order_by(
                    "-created_at"
                ),
            ),
            "aliases",
        )
        patient = get_object_or_404(queryset, pk=pk)
        self.check_object_permissions(self.request, patient)
        self.opening = restricted.opening(self.request.user, patient)
        return patient

    def _detail_data(self, patient) -> dict:
        return PatientDetailSerializer(patient, context={"opening": self.opening}).data

    def _detail(self, pk) -> Response:
        return Response(self._detail_data(self._patient(pk)))

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "search",
                str,
                description="MRN, phone number, ID number or name (similar spelling, any order; "
                "a number among the words is an age). At most 50 results, best match first. "
                "Audited.",
            ),
            OpenApiParameter("sex", str, description="With search: this sex only"),
            OpenApiParameter("age", int, description="With search: age in years, give or take 1"),
            OpenApiParameter("mrn", str, description="Exact MRN (look-up is audited)"),
            OpenApiParameter("facility", str, description="Registered at this facility"),
        ]
    )
    def list(self, request, *args, **kwargs):
        """Patients, newest registration first, or a patient search (``search``): the short list
        only (minimum necessary)."""
        if (request.query_params.get("search") or "").strip():
            return self._search(request)
        if request.query_params.get("mrn"):
            # What was looked up is not kept (it could identify someone); that a look-up happened
            # and how many matched is.
            response = super().list(request, *args, **kwargs)
            record_audit_event(
                action=AuditAction.PATIENT_LIST_SEARCHED,
                resource_type="patient",
                request=request,
                metadata={"by": "mrn", "results": response.data.get("count", 0)},
            )
            return response
        return super().list(request, *args, **kwargs)

    def _search(self, request) -> Response:
        params = PatientSearchQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        data = params.validated_data
        filters = search.Filters(sex=data.get("sex", ""), age=data.get("age"))
        queryset = Patient.objects.select_related("registered_facility").prefetch_related(
            Prefetch("contacts", queryset=_mobiles())
        )
        if data.get("facility"):
            queryset = queryset.filter(registered_facility_id=data["facility"])
        found = search.find(data["search"], filters, queryset=queryset)
        hide = self._hide_restricted()
        matches = found.patients
        if hide and found.matched_on != search.MatchedOn.MRN:
            matches = matches.filter(is_restricted=False)  # D23: only an exact MRN shows one
        patients = list(matches[: search.MAX_RESULTS])
        count = len(patients)
        if count == search.MAX_RESULTS:
            count = matches.count()
        record_audit_event(
            action=AuditAction.PATIENT_LIST_SEARCHED,
            resource_type="patient",
            request=request,
            metadata={"by": found.matched_on, "results": count, "filters": filters.used},
        )
        serializer = PatientListSerializer(
            patients,
            many=True,
            context={"request": request, "matched_on": found.matched_on, "hide_restricted": hide},
        )
        return Response(
            {"count": count, "next": None, "previous": None, "results": serializer.data}
        )

    @extend_schema(responses=PatientDetailSerializer)
    def retrieve(self, request, pk=None):
        """One patient's record: details, contacts, people, ID numbers (masked) and consents.
        Every opening is audited. A restricted record needs ``patients.restricted`` or
        emergency access (otherwise 403 ``RESTRICTED_RECORD``)."""
        patient = self._patient(pk)
        services.record_viewed(
            patient, actor=request.user, request=request, metadata=self.opening.metadata
        )
        return Response(self._detail_data(patient))

    @extend_schema(responses=PatientHistoryEventSerializer(many=True))
    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        """The record's history (HIMS-PAT-005): who opened it and who changed what, and when,
        newest first. Field names only, never their values. Viewing it is audited too."""
        patient = get_object_or_404(
            Patient.objects.only("pk", "registered_facility_id", "is_restricted"), pk=pk
        )
        self.check_object_permissions(request, patient)
        restricted.opening(request.user, patient)
        page = self.paginate_queryset(chart.history(patient))
        record_audit_event(
            action=AuditAction.PATIENT_HISTORY_VIEWED,
            resource_type="patient",
            resource_id=patient.pk,
            facility_id=patient.registered_facility_id,
            request=request,
        )
        return self.get_paginated_response(PatientHistoryEventSerializer(page, many=True).data)

    @extend_schema(request=PatientRegisterSerializer, responses={201: PatientDetailSerializer})
    @idempotent("patients.register")
    def create(self, request):
        """Register a patient; the MRN is issued in the same step."""
        serializer = PatientRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        facility = data.pop("facility")
        check_permission(request.user, P.PATIENTS_REGISTER, facility_id=facility.pk)
        require_enabled(F.PATIENTS, facility_id=facility.pk, request=request)
        extras = {name: data.pop(name) for name in REGISTRATION_EXTRAS if name in data}
        patient = services.register_patient(
            actor=request.user,
            facility=facility,
            data=data,
            mobile=extras.get("mobile", ""),
            alternate_phone=extras.get("alternate_phone", ""),
            email=extras.get("email", ""),
            address={name: extras.get(name, "") for name in ADDRESS_FIELDS},
            relationships=[dict(item) for item in extras.get("relationships", [])],
            identifier_items=[dict(item) for item in extras.get("identifiers", [])],
            privacy_notice=extras.get("privacy_notice", ""),
            sms_consent=extras.get("sms_consent"),
            email_consent=extras.get("email_consent"),
            consent_method=extras.get("consent_method", PatientConsent.Method.VERBAL),
            no_guardian_reason=extras.get("no_guardian_reason", ""),
            request=request,
        )
        return Response(
            self._detail_data(self._patient(patient.pk)), status=status.HTTP_201_CREATED
        )

    @extend_schema(request=PatientUpdateSerializer, responses=PatientDetailSerializer)
    def partial_update(self, request, pk=None):
        """Correct the patient's details; an old name stays findable as an alias."""
        patient = self._patient(pk)
        serializer = PatientUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        services.update_patient(
            actor=request.user,
            patient_id=patient.pk,
            version=data.pop("version"),
            request=request,
            **data,
        )
        return self._detail(patient.pk)

    @extend_schema(request=RestrictionSerializer, responses=PatientDetailSerializer)
    @action(detail=True, methods=["post"])
    def restriction(self, request, pk=None):
        """Restrict the record (VIP, member of staff, other) or lift the restriction, with a
        reason (HIMS-PAT-006). Medical records only (``patients.restricted``)."""
        patient = self._patient(pk)
        serializer = RestrictionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        restricted.set_restriction(
            actor=request.user,
            patient_id=patient.pk,
            version=data.pop("version"),
            request=request,
            **data,
        )
        return self._detail(patient.pk)

    @extend_schema(
        request=EmergencyAccessOpenSerializer, responses={201: OwnEmergencyAccessSerializer}
    )
    @action(detail=True, methods=["post"], url_path="emergency-access")
    def emergency_access(self, request, pk=None):
        """Emergency access to a restricted record (D14): 4 hours, with a reason; medical
        records are told at once and review it afterwards."""
        patient = get_object_or_404(Patient.objects.only("pk"), pk=pk)
        serializer = EmergencyAccessOpenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        access = restricted.open_emergency_access(
            actor=request.user, patient_id=patient.pk, request=request, **serializer.validated_data
        )
        return Response(OwnEmergencyAccessSerializer(access).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses=OwnEmergencyAccessSerializer)
    @action(detail=True, methods=["post"], url_path="emergency-access/end")
    def end_emergency_access(self, request, pk=None):
        """End your emergency access to this record early (done with it)."""
        patient = get_object_or_404(Patient.objects.only("pk"), pk=pk)
        access = restricted.end_emergency_access(
            actor=request.user, patient_id=patient.pk, request=request
        )
        return Response(OwnEmergencyAccessSerializer(access).data)

    @extend_schema(
        parameters=[
            OpenApiParameter("days", int, description="The last so many days (1 to 90; 7)")
        ],
        responses=RestrictedOpeningSerializer(many=True),
    )
    @action(detail=False, methods=["get"], url_path="restricted-openings")
    def restricted_openings(self, request):
        """Who opened restricted records, newest first (D23: reviewed by medical records).
        Viewing the list is audited."""
        try:
            days = min(max(int(request.query_params.get("days", 7)), 1), 90)
        except ValueError:
            days = 7
        page = self.paginate_queryset(
            restricted.restricted_openings(timezone.now() - timedelta(days=days))
        )
        ids = {event.resource_id for event in page}
        mrns = {
            str(pk): mrn for pk, mrn in Patient.objects.filter(pk__in=ids).values_list("pk", "mrn")
        }
        record_audit_event(
            action=AuditAction.RESTRICTED_OPENINGS_VIEWED,
            resource_type="patient",
            request=request,
            metadata={"days": days},
        )
        serializer = RestrictedOpeningSerializer(page, many=True, context={"mrns": mrns})
        return self.get_paginated_response(serializer.data)

    @extend_schema(responses=RegistrationOptionsSerializer)
    @action(detail=False, methods=["get"], url_path="registration-options", pagination_class=None)
    def registration_options(self, request):
        """What the registration form offers in this hospital's country (ID number kinds)."""
        country = get_deployment_organization().country
        kinds = [
            {
                "kind": kind,
                "label": PatientIdentifier.Kind(kind).label,
                "example": identifiers.RULES[kind].example,
                "needs_issuer": identifiers.RULES[kind].needs_issuer,
                "one_per_person": kind in UNIQUE_IDENTIFIER_KINDS,
            }
            for kind in identifiers.kinds_for(country)
        ]
        return Response(
            RegistrationOptionsSerializer({"country": country, "identifier_kinds": kinds}).data
        )

    @extend_schema(request=ContactCreateSerializer, responses={201: ContactSerializer})
    @action(detail=True, methods=["post"], url_path="contacts")
    @idempotent("patients.contacts.add")
    def add_contact(self, request, pk=None):
        """Add a phone, email or address."""
        patient = self._patient(pk)
        serializer = ContactCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        contact = services.add_contact(
            actor=request.user, patient_id=patient.pk, request=request, **serializer.validated_data
        )
        return Response(ContactSerializer(contact).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=ContactUpdateSerializer, responses=ContactSerializer)
    @action(detail=True, methods=["patch"], url_path=r"contacts/(?P<contact_id>[0-9a-f-]+)")
    def update_contact(self, request, pk=None, contact_id=None):
        """Correct a contact, make it the main one, or end it (kept on record)."""
        patient = self._patient(pk)
        contact = patient.contacts.filter(pk=contact_id).first()
        if contact is None:
            raise Http404
        serializer = ContactUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        contact = services.update_contact(
            actor=request.user,
            contact_id=contact.pk,
            version=data.pop("version"),
            request=request,
            **data,
        )
        return Response(ContactSerializer(contact).data)

    @extend_schema(request=RelationshipCreateSerializer, responses={201: RelationshipSerializer})
    @action(detail=True, methods=["post"], url_path="relationships")
    @idempotent("patients.relationships.add")
    def add_relationship(self, request, pk=None):
        """Add a parent, guardian, next of kin, emergency contact or caregiver."""
        patient = self._patient(pk)
        serializer = RelationshipCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        relationship = services.add_relationship(
            actor=request.user, patient_id=patient.pk, request=request, **serializer.validated_data
        )
        return Response(RelationshipSerializer(relationship).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=RelationshipUpdateSerializer, responses=RelationshipSerializer)
    @action(
        detail=True, methods=["patch"], url_path=r"relationships/(?P<relationship_id>[0-9a-f-]+)"
    )
    def update_relationship(self, request, pk=None, relationship_id=None):
        """Correct a relationship or end it (kept on record)."""
        patient = self._patient(pk)
        relationship = patient.relationships.filter(pk=relationship_id).first()
        if relationship is None:
            raise Http404
        serializer = RelationshipUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        relationship = services.update_relationship(
            actor=request.user,
            relationship_id=relationship.pk,
            version=data.pop("version"),
            request=request,
            **data,
        )
        return Response(RelationshipSerializer(relationship).data)

    @extend_schema(request=IdentifierInputSerializer, responses={201: IdentifierSerializer})
    @action(detail=True, methods=["post"], url_path="identifiers")
    @idempotent("patients.identifiers.add")
    def add_identifier(self, request, pk=None):
        """Add an ID number: checked, stored encrypted, shown masked; one-per-person kinds are
        refused when another patient has the number."""
        patient = self._patient(pk)
        serializer = IdentifierInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = services.add_identifier(
            actor=request.user, patient_id=patient.pk, request=request, **serializer.validated_data
        )
        return Response(IdentifierSerializer(row).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=IdentifierEndSerializer, responses=IdentifierSerializer)
    @action(
        detail=True,
        methods=["post"],
        url_path=r"identifiers/(?P<identifier_id>[0-9a-f-]+)/end",
    )
    def end_identifier(self, request, pk=None, identifier_id=None):
        """End a wrong or replaced ID number, with a reason (kept on record, never deleted)."""
        patient = self._patient(pk)
        row = patient.identifiers.filter(pk=identifier_id).first()
        if row is None:
            raise Http404
        serializer = IdentifierEndSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = services.end_identifier(
            actor=request.user, identifier_id=row.pk, request=request, **serializer.validated_data
        )
        return Response(IdentifierSerializer(row).data)

    @extend_schema(request=ConsentCreateSerializer, responses={201: ConsentSerializer})
    @action(detail=True, methods=["post"], url_path="consents")
    @idempotent("patients.consents.record")
    def record_consent(self, request, pk=None):
        """Record a consent decision (privacy notice, SMS, email); earlier ones stay as history."""
        patient = self._patient(pk)
        serializer = ConsentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        consent = services.record_consent(
            actor=request.user, patient_id=patient.pk, request=request, **serializer.validated_data
        )
        return Response(ConsentSerializer(consent).data, status=status.HTTP_201_CREATED)


class EmergencyAccessViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Emergency access to patient records, for medical records to review (HIMS-PAT-006; D14).

    ``state``: ``active`` (open now), ``to_review`` (ended, waiting) or ``reviewed``. Reviewing
    needs someone other than the person who used it.
    """

    permission_scope = ANY_GRANT
    serializer_class = EmergencyAccessSerializer
    required_permissions = {
        "list": P.PATIENTS_RECORDS_CORRECT,
        "retrieve": P.PATIENTS_RECORDS_CORRECT,
        "review": P.PATIENTS_RECORDS_CORRECT,
    }
    http_method_names = ["get", "post", "head"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return EmergencyAccess.objects.none()
        queryset = EmergencyAccess.objects.select_related("patient", "user", "reviewed_by")
        if self.action == "list":
            queryset = restricted.in_state(queryset, self.request.query_params.get("state", ""))
            patient = self.request.query_params.get("patient_id")
            if patient:
                queryset = queryset.filter(patient_id=patient)
        return queryset.order_by("-created_at")

    @extend_schema(
        parameters=[
            OpenApiParameter("state", str, enum=[code for code, _ in restricted.State.CHOICES]),
            OpenApiParameter("patient_id", str, description="This patient only"),
        ]
    )
    def list(self, request, *args, **kwargs):
        """Emergency access, newest first."""
        return super().list(request, *args, **kwargs)

    @extend_schema(request=EmergencyAccessReviewSerializer, responses=EmergencyAccessSerializer)
    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        """Review an ended emergency access: appropriate, or not appropriate with a note."""
        access = self.get_object()
        serializer = EmergencyAccessReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        access = restricted.review_emergency_access(
            actor=request.user,
            access_id=access.pk,
            version=data.pop("version"),
            request=request,
            **data,
        )
        return Response(EmergencyAccessSerializer(access).data)
