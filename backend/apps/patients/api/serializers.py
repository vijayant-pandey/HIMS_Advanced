from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.audit import catalog as audit_catalog
from apps.facilities.models import Facility
from apps.organizations.dates import hospital_today

from .. import chart, demographics, restricted
from ..models import (
    EmergencyAccess,
    Patient,
    PatientAlias,
    PatientConsent,
    PatientContact,
    PatientIdentifier,
    PatientRelationship,
    Sex,
)


def _name(user) -> str | None:
    return user.display_name if user else None


# --- Reading ------------------------------------------------------------------------------------


class PatientListSerializer(serializers.ModelSerializer):
    """The short list (P0 part 01 §2, minimum necessary): no address, ID numbers or full phone."""

    name = serializers.CharField(source="full_name", read_only=True)
    age = serializers.SerializerMethodField()
    phone_last4 = serializers.SerializerMethodField(help_text="The mobile's last 4 digits")
    registered_facility_name = serializers.CharField(
        source="registered_facility.name", read_only=True
    )
    matched_on = serializers.SerializerMethodField(
        help_text="In a search: what found the patient (mrn, phone, id_number or name)"
    )
    hidden = serializers.SerializerMethodField(
        help_text="A restricted record you may not open (HIMS-PAT-006): found by its exact MRN "
        "only, with nothing about the patient; open it with emergency access"
    )

    class Meta:
        model = Patient
        fields = [
            "id",
            "mrn",
            "name",
            "sex",
            "age",
            "birth_date_estimated",
            "phone_last4",
            "is_unknown",
            "is_restricted",
            "hidden",
            "status",
            "registered_facility",
            "registered_facility_name",
            "created_at",
            "matched_on",
        ]
        read_only_fields = fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if data["hidden"]:
            # Only that a restricted record has this MRN: no name, age, sex or phone.
            data.update(name="", sex=Sex.UNKNOWN, age="", birth_date_estimated=False)
            data.update(phone_last4="", is_unknown=False)
        return data

    def get_hidden(self, obj) -> bool:
        return obj.is_restricted and self.context.get("hide_restricted", False)

    def get_age(self, obj) -> str:
        return demographics.age_text(obj.date_of_birth, hospital_today())

    def get_phone_last4(self, obj) -> str:
        mobiles = [c.phone for c in obj.contacts.all() if c.kind == "mobile" and c.is_active]
        return demographics.phone_last4(mobiles[0]) if mobiles else ""

    def get_matched_on(self, obj) -> str | None:
        return self.context.get("matched_on")


class PatientSearchQuerySerializer(serializers.Serializer):
    """What a patient search may ask (HIMS-PAT-002); see apps/patients/search.py."""

    search = serializers.CharField(max_length=200)
    sex = serializers.ChoiceField(choices=Sex.choices, required=False)
    age = serializers.IntegerField(
        min_value=0, max_value=demographics.MAX_AGE_YEARS, required=False
    )
    facility = serializers.UUIDField(required=False)


class ContactSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = PatientContact
        fields = [
            "id",
            "kind",
            "kind_label",
            "phone",
            "email",
            "address_line1",
            "address_line2",
            "city",
            "district",
            "state",
            "postal_code",
            "country",
            "is_primary",
            "is_active",
            "version",
            "created_at",
        ]
        read_only_fields = fields


class RelationshipSerializer(serializers.ModelSerializer):
    relation_label = serializers.CharField(source="get_relation_display", read_only=True)
    related_patient_mrn = serializers.CharField(
        source="related_patient.mrn", read_only=True, allow_null=True, default=None
    )

    class Meta:
        model = PatientRelationship
        fields = [
            "id",
            "relation",
            "relation_label",
            "name",
            "phone",
            "is_legal_guardian",
            "is_emergency_contact",
            "related_patient",
            "related_patient_mrn",
            "note",
            "is_active",
            "version",
            "created_at",
        ]
        read_only_fields = fields


class IdentifierSerializer(serializers.ModelSerializer):
    """Masked only: the full number never leaves the server."""

    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    verification_label = serializers.CharField(source="get_verification_display", read_only=True)
    ended_by_name = serializers.SerializerMethodField()

    class Meta:
        model = PatientIdentifier
        fields = [
            "id",
            "kind",
            "kind_label",
            "value_display",
            "issuer",
            "verification",
            "verification_label",
            "valid_until",
            "is_active",
            "ended_at",
            "ended_by_name",
            "end_reason",
            "version",
            "created_at",
        ]
        read_only_fields = fields

    def get_ended_by_name(self, obj) -> str | None:
        return _name(obj.ended_by)


class ConsentSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    method_label = serializers.CharField(source="get_method_display", read_only=True)
    recorded_by_name = serializers.SerializerMethodField()

    class Meta:
        model = PatientConsent
        fields = [
            "id",
            "kind",
            "kind_label",
            "status",
            "status_label",
            "method",
            "method_label",
            "note",
            "recorded_by_name",
            "created_at",
        ]
        read_only_fields = fields

    def get_recorded_by_name(self, obj) -> str | None:
        return _name(obj.recorded_by)


class AliasSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    name = serializers.CharField(source="__str__", read_only=True)

    class Meta:
        model = PatientAlias
        fields = ["id", "kind", "kind_label", "name", "mrn", "created_at"]
        read_only_fields = fields


class ChartAlertSerializer(serializers.Serializer):
    code = serializers.CharField()
    severity = serializers.ChoiceField(choices=chart.Severity.choices)
    message = serializers.CharField()


class OwnEmergencyAccessSerializer(serializers.ModelSerializer):
    """The reader's own emergency access to this record (HIMS-PAT-006)."""

    class Meta:
        model = EmergencyAccess
        fields = ["id", "reason", "created_at", "expires_at"]
        read_only_fields = fields


class PatientDetailSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="full_name", read_only=True)
    age = serializers.SerializerMethodField()
    registered_facility_name = serializers.CharField(
        source="registered_facility.name", read_only=True
    )
    registered_by_name = serializers.SerializerMethodField()
    merged_into_mrn = serializers.CharField(
        source="merged_into.mrn", read_only=True, allow_null=True, default=None
    )
    contacts = ContactSerializer(many=True, read_only=True)
    relationships = RelationshipSerializer(many=True, read_only=True)
    identifiers = IdentifierSerializer(many=True, read_only=True)
    consents = ConsentSerializer(
        many=True, read_only=True, help_text="Every decision, newest first"
    )
    aliases = AliasSerializer(many=True, read_only=True)
    needs_guardian = serializers.SerializerMethodField(
        help_text="Under 18 with no current parent or guardian recorded"
    )
    allergy_status = serializers.SerializerMethodField(
        help_text="For the chart header; HIMS-CLIN-003 adds recorded allergies"
    )
    alerts = serializers.SerializerMethodField(
        help_text="What staff must notice on opening the record, most important first"
    )
    restriction_label = serializers.CharField(source="get_restriction_display", read_only=True)
    emergency_access = serializers.SerializerMethodField(
        help_text="Opened with your emergency access: until when (HIMS-PAT-006)"
    )

    class Meta:
        model = Patient
        fields = [
            "id",
            "mrn",
            "status",
            "merged_into",
            "merged_into_mrn",
            "name",
            "title",
            "given_name",
            "middle_name",
            "family_name",
            "preferred_name",
            "date_of_birth",
            "birth_date_estimated",
            "age",
            "sex",
            "gender_identity",
            "pronouns",
            "preferred_language",
            "marital_status",
            "occupation",
            "blood_group_reported",
            "has_no_phone",
            "is_unknown",
            "identification_note",
            "is_restricted",
            "restriction",
            "restriction_label",
            "emergency_access",
            "registered_facility",
            "registered_facility_name",
            "registered_by_name",
            "needs_guardian",
            "allergy_status",
            "alerts",
            "contacts",
            "relationships",
            "identifiers",
            "consents",
            "aliases",
            "version",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_age(self, obj) -> str:
        return demographics.age_text(obj.date_of_birth, hospital_today())

    def get_registered_by_name(self, obj) -> str | None:
        return _name(obj.registered_by)

    def get_needs_guardian(self, obj) -> bool:
        return chart.needs_guardian(obj)

    @extend_schema_field(serializers.ChoiceField(choices=chart.AllergyStatus.choices))
    def get_allergy_status(self, obj) -> str:
        return chart.AllergyStatus.NOT_ASKED  # recorded allergies come with HIMS-CLIN-003

    @extend_schema_field(ChartAlertSerializer(many=True))
    def get_alerts(self, obj) -> list[dict]:
        return ChartAlertSerializer(chart.alerts(obj), many=True).data

    @extend_schema_field(OwnEmergencyAccessSerializer(allow_null=True))
    def get_emergency_access(self, obj) -> dict | None:
        opening = self.context.get("opening")
        if opening is None or opening.access is None:
            return None
        return OwnEmergencyAccessSerializer(opening.access).data


class PatientHistoryEventSerializer(serializers.Serializer):
    """One event in the record's history (HIMS-PAT-005): what, who, where and when; for a
    correction the names of the fields that changed, never their values."""

    id = serializers.UUIDField()
    occurred_at = serializers.DateTimeField()
    action = serializers.CharField()
    action_label = serializers.SerializerMethodField()
    actor_name = serializers.CharField(allow_null=True)
    facility_name = serializers.CharField(allow_null=True)
    outcome = serializers.CharField()
    changed = serializers.SerializerMethodField(help_text="Fields corrected (names only)")
    reason = serializers.CharField()

    def get_action_label(self, event) -> str:
        return audit_catalog.label(event.action)

    def get_changed(self, event) -> list[str]:
        return chart.changed_fields(event)


class EmergencyAccessSerializer(serializers.ModelSerializer):
    """Emergency access for medical records to review (HIMS-PAT-006)."""

    patient_mrn = serializers.CharField(source="patient.mrn", read_only=True)
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    user_name = serializers.CharField(source="user.display_name", read_only=True)
    user_email = serializers.CharField(source="user.email", read_only=True)
    ends_at = serializers.DateTimeField(read_only=True)
    state = serializers.SerializerMethodField()
    reviewed_by_name = serializers.SerializerMethodField()
    outcome_label = serializers.CharField(source="get_outcome_display", read_only=True)

    class Meta:
        model = EmergencyAccess
        fields = [
            "id",
            "patient",
            "patient_mrn",
            "patient_name",
            "user",
            "user_name",
            "user_email",
            "reason",
            "created_at",
            "expires_at",
            "ended_at",
            "ends_at",
            "state",
            "reviewed_at",
            "reviewed_by_name",
            "outcome",
            "outcome_label",
            "review_note",
            "version",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.ChoiceField(choices=restricted.State.CHOICES))
    def get_state(self, obj) -> str:
        return restricted.state_of(obj)

    def get_reviewed_by_name(self, obj) -> str | None:
        return _name(obj.reviewed_by)


class RestrictedOpeningSerializer(serializers.Serializer):
    """One opening of a restricted record: who, when, where and how (HIMS-PAT-006)."""

    id = serializers.UUIDField()
    occurred_at = serializers.DateTimeField()
    patient = serializers.UUIDField(source="resource_id")
    patient_mrn = serializers.SerializerMethodField()
    actor_name = serializers.CharField(allow_null=True)
    facility_name = serializers.CharField(allow_null=True)
    via = serializers.SerializerMethodField(
        help_text="restricted_permission (medical records) or emergency_access"
    )

    def get_patient_mrn(self, event) -> str:
        return self.context.get("mrns", {}).get(event.resource_id, "")

    def get_via(self, event) -> str:
        return (event.metadata or {}).get("via", "")


# --- Writing ------------------------------------------------------------------------------------

_NAME = {"max_length": 150, "required": False, "allow_blank": True, "default": ""}


class RelationshipInputSerializer(serializers.Serializer):
    relation = serializers.ChoiceField(PatientRelationship.Relation.choices)
    name = serializers.CharField(max_length=200)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    is_legal_guardian = serializers.BooleanField(required=False, default=False)
    is_emergency_contact = serializers.BooleanField(required=False, default=False)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class IdentifierInputSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(PatientIdentifier.Kind.choices)
    value = serializers.CharField(max_length=64, help_text="As typed; stored encrypted")
    issuer = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    valid_until = serializers.DateField(required=False, allow_null=True, default=None)


class AddressInputSerializer(serializers.Serializer):
    address_line1 = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )
    address_line2 = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )
    city = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    district = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    state = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    postal_code = serializers.CharField(max_length=10, required=False, allow_blank=True, default="")
    country = serializers.CharField(max_length=2, required=False, allow_blank=True, default="")


class PatientRegisterSerializer(AddressInputSerializer):
    """Register a patient: name, sex, date of birth **or** age, mobile **or** "no phone" (D2)."""

    facility = serializers.PrimaryKeyRelatedField(
        queryset=Facility.objects.all(), help_text="Where the patient is registered"
    )
    title = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    given_name = serializers.CharField(**_NAME)
    middle_name = serializers.CharField(**_NAME)
    family_name = serializers.CharField(**_NAME)
    preferred_name = serializers.CharField(**_NAME)
    date_of_birth = serializers.DateField(required=False, allow_null=True, default=None)
    age_years = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    age_months = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    age_days = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    sex = serializers.ChoiceField(Patient._meta.get_field("sex").choices)
    gender_identity = serializers.CharField(
        max_length=60, required=False, allow_blank=True, default=""
    )
    pronouns = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")
    preferred_language = serializers.CharField(
        max_length=35, required=False, allow_blank=True, default=""
    )
    marital_status = serializers.ChoiceField(
        Patient.MaritalStatus.choices, required=False, allow_blank=True, default=""
    )
    occupation = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    blood_group_reported = serializers.ChoiceField(
        Patient.BloodGroup.choices, required=False, allow_blank=True, default=""
    )
    is_unknown = serializers.BooleanField(required=False, default=False)
    identification_note = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )
    mobile = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    has_no_phone = serializers.BooleanField(required=False, default=False)
    alternate_phone = serializers.CharField(
        max_length=30, required=False, allow_blank=True, default=""
    )
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    relationships = RelationshipInputSerializer(many=True, required=False, default=list)
    identifiers = IdentifierInputSerializer(many=True, required=False, default=list)
    privacy_notice = serializers.ChoiceField(
        [("given", "Given"), ("refused", "Refused")],
        required=False,
        allow_blank=True,
        default="",
        help_text="Privacy notice given and the patient agrees to processing for care (D9)",
    )
    sms_consent = serializers.BooleanField(required=False, allow_null=True, default=None)
    email_consent = serializers.BooleanField(required=False, allow_null=True, default=None)
    consent_method = serializers.ChoiceField(
        PatientConsent.Method.choices, required=False, default=PatientConsent.Method.VERBAL
    )
    no_guardian_reason = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        default="",
        help_text="Under 18 without a parent or guardian: why (e.g. emergency)",
    )


class PatientUpdateSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    title = serializers.CharField(max_length=20, required=False, allow_blank=True)
    given_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    middle_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    family_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    preferred_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    date_of_birth = serializers.DateField(required=False)
    birth_date_estimated = serializers.BooleanField(required=False)
    sex = serializers.ChoiceField(Patient._meta.get_field("sex").choices, required=False)
    gender_identity = serializers.CharField(max_length=60, required=False, allow_blank=True)
    pronouns = serializers.CharField(max_length=60, required=False, allow_blank=True)
    preferred_language = serializers.CharField(max_length=35, required=False, allow_blank=True)
    marital_status = serializers.ChoiceField(
        Patient.MaritalStatus.choices, required=False, allow_blank=True
    )
    occupation = serializers.CharField(max_length=100, required=False, allow_blank=True)
    blood_group_reported = serializers.ChoiceField(
        Patient.BloodGroup.choices, required=False, allow_blank=True
    )
    has_no_phone = serializers.BooleanField(required=False)
    is_unknown = serializers.BooleanField(required=False)
    identification_note = serializers.CharField(max_length=255, required=False, allow_blank=True)


class ContactCreateSerializer(AddressInputSerializer):
    kind = serializers.ChoiceField(PatientContact.Kind.choices)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    is_primary = serializers.BooleanField(required=False, default=False)


class ContactUpdateSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    address_line1 = serializers.CharField(max_length=255, required=False, allow_blank=True)
    address_line2 = serializers.CharField(max_length=255, required=False, allow_blank=True)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    district = serializers.CharField(max_length=100, required=False, allow_blank=True)
    state = serializers.CharField(max_length=100, required=False, allow_blank=True)
    postal_code = serializers.CharField(max_length=10, required=False, allow_blank=True)
    country = serializers.CharField(max_length=2, required=False, allow_blank=True)
    is_primary = serializers.BooleanField(required=False)
    is_active = serializers.BooleanField(required=False, help_text="False ends it (kept on record)")


class RelationshipCreateSerializer(RelationshipInputSerializer):
    related_patient = serializers.PrimaryKeyRelatedField(
        queryset=Patient.objects.all(), required=False, allow_null=True, default=None
    )


class RelationshipUpdateSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    relation = serializers.ChoiceField(PatientRelationship.Relation.choices, required=False)
    name = serializers.CharField(max_length=200, required=False)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True)
    is_legal_guardian = serializers.BooleanField(required=False)
    is_emergency_contact = serializers.BooleanField(required=False)
    related_patient = serializers.PrimaryKeyRelatedField(
        queryset=Patient.objects.all(), required=False, allow_null=True
    )
    note = serializers.CharField(max_length=255, required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False, help_text="False ends it (kept on record)")


class IdentifierEndSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=255)


class ConsentCreateSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(PatientConsent.Kind.choices)
    status = serializers.ChoiceField(PatientConsent.Status.choices)
    method = serializers.ChoiceField(PatientConsent.Method.choices)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class RestrictionSerializer(serializers.Serializer):
    """Restrict a record or lift the restriction (HIMS-PAT-006)."""

    restricted = serializers.BooleanField()
    restriction = serializers.ChoiceField(
        Patient.Restriction.choices, required=False, allow_blank=True, default=""
    )
    reason = serializers.CharField(max_length=255)
    version = serializers.IntegerField(min_value=1)


class EmergencyAccessOpenSerializer(serializers.Serializer):
    reason = serializers.CharField(
        max_length=500, help_text=f"Why (at least {restricted.MIN_REASON} characters)"
    )


class EmergencyAccessReviewSerializer(serializers.Serializer):
    outcome = serializers.ChoiceField(EmergencyAccess.Outcome.choices)
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    version = serializers.IntegerField(min_value=1)


class IdentifierKindSerializer(serializers.Serializer):
    kind = serializers.CharField()
    label = serializers.CharField()
    example = serializers.CharField()
    needs_issuer = serializers.BooleanField()
    one_per_person = serializers.BooleanField(
        help_text="The same number on a second patient is refused"
    )


class RegistrationOptionsSerializer(serializers.Serializer):
    country = serializers.CharField()
    identifier_kinds = IdentifierKindSerializer(many=True)
