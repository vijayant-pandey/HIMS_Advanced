"""Patients in the admin console (HIMS-PAT-001; ADR-016).

The console shows patients only to people who may open them (``patients.view``) and changes them
only for people who may register them (``patients.register``): administrators look, the front
desk and medical records change (P0 part 04). Every change goes through the same services as the
app (MRN issued, phone and ID checks, audit); opening a patient's page is audited like opening the
record in the app. ID numbers are shown masked; the full number cannot be read here either.

Searching Patients uses the app's patient search (HIMS-PAT-002): MRN, phone, ID number or a
similar name, at most 50 results, audited. Patient identifiers can be searched by the number.
"""

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.access_control.catalog import P
from apps.access_control.selectors import has_permission
from apps.audit.services import AuditAction, record_audit_event
from apps.organizations.selectors import get_deployment_organization
from common.admin.options import HimsModelAdmin, ReadOnlyModelAdmin
from common.admin.site import can_use_console
from common.exceptions import DomainError

from . import demographics, identifiers, search, services
from .models import (
    Patient,
    PatientAlias,
    PatientConsent,
    PatientContact,
    PatientIdentifier,
    PatientRelationship,
)


def _may_view(request) -> bool:
    return can_use_console(request.user) and has_permission(request.user, P.PATIENTS_VIEW)


def _may_change(request) -> bool:
    return can_use_console(request.user) and has_permission(request.user, P.PATIENTS_REGISTER)


class PatientConsoleAccess:
    def has_module_permission(self, request):
        return _may_view(request)

    def has_view_permission(self, request, obj=None):
        return _may_view(request)

    def has_add_permission(self, request, *args):
        return _may_change(request)

    def has_change_permission(self, request, obj=None):
        return _may_change(request)

    def has_delete_permission(self, request, obj=None):
        return False


def _audit_search(request, matched_on: str, results: int) -> None:
    """A console search, like one in the app: its kind and count, never what was typed."""
    record_audit_event(
        action=AuditAction.PATIENT_LIST_SEARCHED,
        resource_type="patient",
        actor=request.user,
        request=request,
        metadata={"by": matched_on, "results": results, "in": "console"},
    )


def _service_error(model_admin, request, exc) -> None:
    if isinstance(exc, ValidationError):
        text = "; ".join(f"{k}: {', '.join(v)}" for k, v in exc.message_dict.items())
    else:
        text = str(exc.detail)
    model_admin.message_user(request, f"Not saved: {text}", messages.ERROR)


class _ReadOnlyInline(admin.TabularInline):
    extra = 0
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return _may_view(request)


class ContactInline(_ReadOnlyInline):
    model = PatientContact
    fields = ("kind", "phone", "email", "city", "state", "is_primary", "is_active")
    readonly_fields = fields


class RelationshipInline(_ReadOnlyInline):
    model = PatientRelationship
    fk_name = "patient"
    fields = ("relation", "name", "phone", "is_legal_guardian", "is_emergency_contact", "is_active")
    readonly_fields = fields


class IdentifierInline(_ReadOnlyInline):
    model = PatientIdentifier
    fields = ("kind", "value_display", "issuer", "verification", "is_active", "end_reason")
    readonly_fields = fields


class ConsentInline(_ReadOnlyInline):
    model = PatientConsent
    fields = ("created_at", "kind", "status", "method", "recorded_by", "note")
    readonly_fields = fields
    show_change_link = False


class AliasInline(_ReadOnlyInline):
    model = PatientAlias
    fields = ("created_at", "kind", "given_name", "middle_name", "family_name", "mrn")
    readonly_fields = fields
    show_change_link = False


class PatientForm(forms.ModelForm):
    """Adding registers through the service (MRN issued); age instead of a birth date is fine."""

    age_years = forms.IntegerField(
        required=False, min_value=1, help_text="Instead of the date of birth (estimated)"
    )
    mobile = forms.CharField(required=False, help_text="Or tick 'Has no phone'")

    class Meta:
        model = Patient
        fields = ("registered_facility", *services.EDITABLE_FIELDS)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "date_of_birth" in self.fields:
            self.fields["date_of_birth"].required = False
        if "given_name" in self.fields:
            self.fields["given_name"].required = False

    def clean(self):
        cleaned = super().clean()
        unknown = cleaned.get("is_unknown")
        if not cleaned.get("given_name") and not unknown:
            self.add_error("given_name", "Give at least one name.")
        if self.instance.pk is None:
            if not cleaned.get("date_of_birth") and not cleaned.get("age_years"):
                self.add_error("date_of_birth", "Give the date of birth or the age.")
            country = get_deployment_organization().country
            try:
                cleaned["mobile"] = demographics.normalise_phone(
                    cleaned.get("mobile", ""), country=country, mobile=True
                )
            except demographics.InvalidValue as exc:
                self.add_error("mobile", str(exc))
            if not cleaned.get("mobile") and not cleaned.get("has_no_phone") and not unknown:
                self.add_error("mobile", "Enter a mobile number, or tick 'Has no phone'.")
        return cleaned


@admin.register(Patient)
class PatientAdmin(PatientConsoleAccess, HimsModelAdmin):
    """Patients (HIMS-PAT-001). Add registers through the service; the MRN is issued then."""

    form = PatientForm
    list_display = (
        "mrn",
        "full_name",
        "sex",
        "date_of_birth",
        "registered_facility",
        "is_unknown",
        "status",
        "created_at",
    )
    list_filter = ("sex", "is_unknown", "status", "registered_facility")
    search_fields = ("=mrn", "given_name", "family_name")  # replaced by patient search, below
    search_help_text = (
        "MRN, phone number, ID number or name (similar spelling, any order; add an age: "
        "'sunita 45'). At most 50 results. Every search is in the audit log."
    )
    inlines = (ContactInline, RelationshipInline, IdentifierInline, ConsentInline, AliasInline)

    def get_search_results(self, request, queryset, search_term):
        """The same patient search as the app (HIMS-PAT-002), audited the same way."""
        if not " ".join(search_term.split()):
            return queryset, False
        try:
            found = search.find(search_term, queryset=queryset)
        except ValidationError as exc:
            if not request.path.endswith("/autocomplete/"):
                self.message_user(request, " ".join(exc.messages), messages.WARNING)
            return queryset.none(), False
        ids = list(found.patients.values_list("pk", flat=True)[: search.MAX_RESULTS])
        _audit_search(request, found.matched_on, len(ids))
        return queryset.filter(pk__in=ids), False

    def get_fieldsets(self, request, obj=None):
        person = [
            "title",
            "given_name",
            "middle_name",
            "family_name",
            "preferred_name",
            "date_of_birth",
            "birth_date_estimated",
            "sex",
            "gender_identity",
            "pronouns",
        ]
        if obj is None:
            person.insert(6, "age_years")
        sets = [
            (None, {"fields": ("mrn", "status", "registered_facility")}),
            ("Person", {"fields": person}),
            (
                "More",
                {
                    "fields": (
                        "preferred_language",
                        "marital_status",
                        "occupation",
                        "blood_group_reported",
                        "has_no_phone",
                        *(("mobile",) if obj is None else ()),
                        "is_unknown",
                        "identification_note",
                    )
                },
            ),
            ("Record", {"fields": ("registered_by", "version", "created_at", "updated_at")}),
        ]
        return sets

    def get_readonly_fields(self, request, obj=None):
        readonly = [*super().get_readonly_fields(request, obj), "mrn", "status", "registered_by"]
        if obj is not None:
            readonly.append("registered_facility")
        return readonly

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        if object_id and request.method == "GET" and _may_view(request):
            patient = Patient.objects.filter(pk=object_id).first()
            if patient is not None:
                services.record_viewed(patient, actor=request.user, request=request)
        return super().changeform_view(request, object_id, form_url, extra_context)

    def save_model(self, request, obj, form, change):
        data = {f: form.cleaned_data.get(f) for f in services.EDITABLE_FIELDS}
        try:
            if change:
                current = Patient.objects.get(pk=obj.pk)
                changed = {f: v for f, v in data.items() if getattr(current, f) != v}
                services.update_patient(
                    actor=request.user,
                    patient_id=obj.pk,
                    version=current.version,
                    request=request,
                    **changed,
                )
                return
            age = form.cleaned_data.get("age_years")
            if age and not data.get("date_of_birth"):
                data.pop("date_of_birth")
                data.pop("birth_date_estimated")
                data["age_years"] = age
            patient = services.register_patient(
                actor=request.user,
                facility=form.cleaned_data["registered_facility"],
                data=data,
                mobile=form.cleaned_data.get("mobile", ""),
                request=request,
            )
            obj.pk, obj.mrn = patient.pk, patient.mrn
            obj._state.adding = False
        except (ValidationError, DomainError) as exc:
            _service_error(self, request, exc)


class ContactForm(forms.ModelForm):
    class Meta:
        model = PatientContact
        fields = (
            "patient",
            "kind",
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
        )

    def clean(self):
        cleaned = super().clean()
        kind = cleaned.get("kind") or getattr(self.instance, "kind", "")
        if kind in ("mobile", "phone"):
            try:
                cleaned["phone"] = demographics.normalise_phone(
                    cleaned.get("phone", ""),
                    country=get_deployment_organization().country,
                    mobile=kind == "mobile",
                )
            except demographics.InvalidValue as exc:
                self.add_error("phone", str(exc))
        return cleaned


@admin.register(PatientContact)
class PatientContactAdmin(PatientConsoleAccess, HimsModelAdmin):
    """Phones, emails and addresses. Ending one (untick 'is active') keeps it on record."""

    form = ContactForm
    list_display = ("patient", "kind", "phone", "email", "city", "is_primary", "is_active")
    list_filter = ("kind", "is_active")
    search_fields = ("=patient__mrn", "=phone", "email")
    raw_id_fields = ("patient",)

    def get_readonly_fields(self, request, obj=None):
        readonly = [*super().get_readonly_fields(request, obj), "created_by"]
        return [*readonly, "patient", "kind"] if obj else readonly

    def save_model(self, request, obj, form, change):
        values = {f: form.cleaned_data.get(f) for f in services.CONTACT_FIELDS}
        try:
            if change:
                current = PatientContact.objects.get(pk=obj.pk)
                services.update_contact(
                    actor=request.user,
                    contact_id=obj.pk,
                    version=current.version,
                    request=request,
                    **values,
                )
                return
            values.pop("is_active")
            contact = services.add_contact(
                actor=request.user,
                patient_id=form.cleaned_data["patient"].pk,
                kind=form.cleaned_data["kind"],
                request=request,
                **values,
            )
            obj.pk = contact.pk
            obj._state.adding = False
        except (ValidationError, DomainError) as exc:
            _service_error(self, request, exc)


@admin.register(PatientRelationship)
class PatientRelationshipAdmin(PatientConsoleAccess, HimsModelAdmin):
    """Parents, guardians, next of kin, emergency contacts and caregivers."""

    list_display = ("patient", "relation", "name", "phone", "is_legal_guardian", "is_active")
    list_filter = ("relation", "is_legal_guardian", "is_active")
    search_fields = ("=patient__mrn", "name")
    raw_id_fields = ("patient", "related_patient")
    fields = (
        "patient",
        "relation",
        "name",
        "phone",
        "is_legal_guardian",
        "is_emergency_contact",
        "related_patient",
        "note",
        "is_active",
        "created_by",
        "version",
        "created_at",
        "updated_at",
    )

    def get_readonly_fields(self, request, obj=None):
        readonly = [*super().get_readonly_fields(request, obj), "created_by"]
        return [*readonly, "patient"] if obj else readonly

    def save_model(self, request, obj, form, change):
        values = {f: form.cleaned_data.get(f) for f in services.RELATIONSHIP_FIELDS}
        try:
            if change:
                current = PatientRelationship.objects.get(pk=obj.pk)
                services.update_relationship(
                    actor=request.user,
                    relationship_id=obj.pk,
                    version=current.version,
                    request=request,
                    **values,
                )
                return
            values.pop("is_active")
            relationship = services.add_relationship(
                actor=request.user,
                patient_id=form.cleaned_data["patient"].pk,
                request=request,
                **values,
            )
            obj.pk = relationship.pk
            obj._state.adding = False
        except (ValidationError, DomainError) as exc:
            _service_error(self, request, exc)


class IdentifierForm(forms.ModelForm):
    """Adding: the number is typed here, checked, encrypted and masked by the service. An existing
    number is never shown or edited: end it with a reason, then add the right one."""

    number = forms.CharField(required=False, max_length=64, help_text="Stored encrypted")
    end_reason_text = forms.CharField(
        required=False,
        max_length=255,
        label="End this number: reason",
        help_text="e.g. 'Typing mistake'. It stays on record as ended.",
    )

    class Meta:
        model = PatientIdentifier
        fields = ("patient", "kind", "issuer", "valid_until")

    def clean(self):
        cleaned = super().clean()
        if self.instance.pk is None:
            try:
                identifiers.check(
                    cleaned.get("kind", ""),
                    cleaned.get("number", ""),
                    country=get_deployment_organization().country,
                )
            except identifiers.InvalidIdentifier as exc:
                self.add_error("number", str(exc))
        return cleaned


@admin.register(PatientIdentifier)
class PatientIdentifierAdmin(PatientConsoleAccess, HimsModelAdmin):
    """ID numbers, masked. Encrypted value and fingerprint are never shown."""

    form = IdentifierForm
    list_display = ("patient", "kind", "value_display", "verification", "is_active", "created_at")
    list_filter = ("kind", "verification", "is_active")
    search_fields = ("=patient__mrn",)
    search_help_text = "The patient's MRN, or the whole ID number (found by its fingerprint)."
    raw_id_fields = ("patient",)

    def get_search_results(self, request, queryset, search_term):
        """By MRN, or by the number itself (HIMS-PAT-002): compared by fingerprint, audited."""
        term = " ".join(search_term.split())
        if not term:
            return queryset, False
        by_mrn, _ = super().get_search_results(request, queryset, term)
        country = get_deployment_organization().country
        rows = queryset.filter(search.identifier_query(term, country)) | by_mrn
        _audit_search(request, search.MatchedOn.ID_NUMBER, rows.count())
        return rows, False

    def get_fields(self, request, obj=None):
        if obj is None:
            return ("patient", "kind", "number", "issuer", "valid_until")
        return (
            "patient",
            "kind",
            "value_display",
            "issuer",
            "valid_until",
            "verification",
            "is_active",
            "ended_at",
            "ended_by",
            "end_reason",
            "end_reason_text",
            "created_by",
            "version",
            "created_at",
            "updated_at",
        )

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj is None:
            return readonly
        return [
            *readonly,
            "patient",
            "kind",
            "value_display",
            "issuer",
            "valid_until",
            "verification",
            "is_active",
            "ended_at",
            "ended_by",
            "end_reason",
            "created_by",
        ]

    def save_model(self, request, obj, form, change):
        try:
            if change:
                reason = form.cleaned_data.get("end_reason_text", "").strip()
                if reason and obj.is_active:
                    services.end_identifier(
                        actor=request.user,
                        identifier_id=obj.pk,
                        version=PatientIdentifier.objects.get(pk=obj.pk).version,
                        reason=reason,
                        request=request,
                    )
                return
            row = services.add_identifier(
                actor=request.user,
                patient_id=form.cleaned_data["patient"].pk,
                kind=form.cleaned_data["kind"],
                value=form.cleaned_data["number"],
                issuer=form.cleaned_data.get("issuer", ""),
                valid_until=form.cleaned_data.get("valid_until"),
                request=request,
            )
            obj.pk = row.pk
            obj._state.adding = False
        except (ValidationError, DomainError) as exc:
            _service_error(self, request, exc)


@admin.register(PatientConsent)
class PatientConsentAdmin(PatientConsoleAccess, HimsModelAdmin):
    """Consent decisions. A new decision is a new row; earlier rows never change."""

    list_display = ("created_at", "patient", "kind", "status", "method", "recorded_by")
    list_filter = ("kind", "status", "method")
    search_fields = ("=patient__mrn",)
    raw_id_fields = ("patient",)
    fields = ("patient", "kind", "status", "method", "note", "recorded_by", "created_at")
    readonly_fields = ("recorded_by", "created_at")

    def has_change_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        try:
            consent = services.record_consent(
                actor=request.user,
                patient_id=form.cleaned_data["patient"].pk,
                kind=form.cleaned_data["kind"],
                status=form.cleaned_data["status"],
                method=form.cleaned_data["method"],
                note=form.cleaned_data.get("note", ""),
                request=request,
            )
            obj.pk, obj.created_at = consent.pk, consent.created_at or timezone.now()
            obj._state.adding = False
        except (ValidationError, DomainError) as exc:
            _service_error(self, request, exc)


@admin.register(PatientAlias)
class PatientAliasAdmin(PatientConsoleAccess, ReadOnlyModelAdmin):
    """Earlier names (and merged MRNs) that still find the patient. Written by the services."""

    list_display = ("created_at", "patient", "kind", "given_name", "family_name", "mrn")
    list_filter = ("kind",)
    search_fields = ("=patient__mrn", "=mrn")

    def has_add_permission(self, request, *args):
        return False

    def has_change_permission(self, request, obj=None):
        return False
