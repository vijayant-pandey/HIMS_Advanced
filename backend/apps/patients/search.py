"""Patient search (HIMS-PAT-002; spec 4.5, 28.6; P0 part 01 section 2).

One search box. What was typed decides how it is matched:

* anything with a digit (or an ``@``) is first tried as an exact number: the MRN (or an earlier
  MRN kept as an alias; digits alone match the number part, e.g. ``123`` finds MRN-00000123), a
  phone number (normalised to international format, the patient's own phones only: a phone
  shared in a family finds every patient who gave it), or an ID number (compared by its keyed
  fingerprint, so the full number is never searched in plain text);
* otherwise it is a name, in any order, with or without earlier names: each word must match a
  word of the patient's names by similar spelling (PostgreSQL ``pg_trgm`` word similarity) or
  by sound (``demographics.sound_key``: Lakshmi / Laxmi), both served by indexes (ADR-037). A
  number among the words is an age in years (``sunita 45``).

Optional filters: sex and age in years (plus or minus one year). A date of birth is not a filter:
it would travel in the web address, which must not carry sensitive fields (spec 13.3,
``test_no_api_takes_a_secret_in_the_address``); the age does the same job. At most 50 results;
fewer than 3 letters of a name is too broad. The search itself is audited by the caller with
what kind of search it was and how many matched, never what was typed (it could identify
someone).
"""

import re
from dataclasses import dataclass
from datetime import date

from django.contrib.postgres.search import TrigramWordSimilarity
from django.core.exceptions import ValidationError
from django.db.models import Q, QuerySet

from apps.organizations.dates import hospital_today
from apps.organizations.selectors import get_deployment_organization

from . import demographics, identifiers
from .demographics import InvalidValue
from .models import Patient, PatientAlias, PatientContact, PatientIdentifier

MAX_RESULTS = 50
MIN_NAME_LETTERS = 3
MAX_MRN_DIGITS = 9  # longer runs of digits are phone or ID numbers


class MatchedOn:
    MRN = "mrn"
    PHONE = "phone"
    ID_NUMBER = "id_number"
    NAME = "name"

    LABELS = {MRN: "MRN", PHONE: "Phone", ID_NUMBER: "ID number", NAME: "Name"}


@dataclass(frozen=True)
class Filters:
    sex: str = ""
    age: int | None = None

    @property
    def used(self) -> list[str]:
        """The filter names used (for the audit log; never their values)."""
        names = (("sex", self.sex), ("age", self.age))
        return [name for name, value in names if value not in ("", None)]


@dataclass(frozen=True)
class Search:
    patients: QuerySet
    matched_on: str


def _shift_years(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year + years)
    except ValueError:  # 29 February in a year without one
        return day.replace(year=day.year + years, day=28)


def _filtered(queryset: QuerySet, filters: Filters, today: date) -> QuerySet:
    if filters.sex:
        queryset = queryset.filter(sex=filters.sex)
    if filters.age is not None:
        # Born between (age + 2) and (age - 1) years ago: the age give or take a year.
        queryset = queryset.filter(
            date_of_birth__gt=_shift_years(today, -(filters.age + 2)),
            date_of_birth__lte=_shift_years(today, -max(filters.age - 1, 0)),
        )
    return queryset


# --- Exact numbers ------------------------------------------------------------------------------


def _by_mrn(text: str) -> set:
    mrn = re.sub(r"\s", "", text).upper()
    ids = set(Patient.objects.filter(mrn=mrn).values_list("pk", flat=True))
    ids |= set(
        PatientAlias.objects.filter(kind=PatientAlias.Kind.MERGED_MRN, mrn=mrn).values_list(
            "patient_id", flat=True
        )
    )
    if not ids and mrn.isdigit() and len(mrn) <= MAX_MRN_DIGITS:
        # Only the number: MRN-00000123 from "123" (the number part, leading zeros optional).
        pattern = rf"(^|[^0-9])0*{int(mrn)}$"
        ids = set(Patient.objects.filter(mrn__regex=pattern).values_list("pk", flat=True))
    return ids


def _by_phone(text: str, country: str) -> set:
    if not re.fullmatch(r"[+\d\s().-]+", text) or len(re.sub(r"\D", "", text)) < 10:
        return set()
    try:
        number = demographics.normalise_phone(text, country=country)
    except InvalidValue:
        return set()
    return set(
        PatientContact.objects.filter(
            kind__in=(PatientContact.Kind.MOBILE, PatientContact.Kind.PHONE),
            is_active=True,
            phone=number,
        ).values_list("patient_id", flat=True)
    )


def _by_id_number(text: str, country: str) -> set:
    return set(
        PatientIdentifier.objects.filter(identifier_query(text, country)).values_list(
            "patient_id", flat=True
        )
    )


def identifier_query(text: str, country: str) -> Q:
    """The active ID-number rows whose number is ``text``, as any kind used in ``country``
    (compared by fingerprint; matches nothing when it is no valid number)."""
    wanted = Q(pk__in=[])
    for kind in identifiers.kinds_for(country):
        try:
            number = identifiers.check(kind, text, country=country)
        except identifiers.InvalidIdentifier:
            continue
        if kind == PatientIdentifier.Kind.PREVIOUS_MRN:
            # Its fingerprint includes the hospital it is from: try each one on record.
            issuers = (
                PatientIdentifier.objects.filter(kind=kind)
                .values_list("issuer", flat=True)
                .distinct()
            )
            hashes = [identifiers.fingerprint(kind, number, issuer=i) for i in issuers]
        else:
            hashes = [identifiers.fingerprint(kind, number)]
        wanted |= Q(kind=kind, value_hash__in=hashes)
    return wanted & Q(is_active=True)


# --- Names --------------------------------------------------------------------------------------


def _by_name(queryset: QuerySet, words: list[str]) -> QuerySet:
    for word in words:
        if len(word) < 2:
            continue  # an initial ("R Kumar"): too short to match on its own
        queryset = queryset.filter(
            Q(search_name__trigram_word_similar=word)
            | Q(search_sounds__contains=[demographics.sound_key(word)])
        )
    return queryset.annotate(
        closeness=TrigramWordSimilarity(" ".join(words), "search_name")
    ).order_by("-closeness", "given_name", "family_name", "mrn")


def _name_words(text: str) -> tuple[list[str], int | None]:
    words, ages = [], []
    for word in demographics.search_name(text).split():
        (ages if word.isdigit() else words).append(word)
    if len(ages) > 1:
        raise ValidationError({"search": "Give one age only, e.g. 'sunita 45'."})
    age = int(ages[0]) if ages else None
    if age is not None and age > demographics.MAX_AGE_YEARS:
        raise ValidationError({"search": "That age is too high; give the age in years."})
    return words, age


def _number_kind(text: str, country: str) -> str:
    """For the audit log, what an unmatched number most likely was."""
    if len(re.sub(r"\D", "", text)) <= MAX_MRN_DIGITS:
        return MatchedOn.MRN
    try:
        demographics.normalise_phone(text, country=country)
    except InvalidValue:
        return MatchedOn.ID_NUMBER
    return MatchedOn.PHONE


def find(text: str, filters: Filters | None = None, *, queryset=None) -> Search:
    """Patients matching what was typed, best match first (not yet limited to 50)."""
    filters = filters or Filters()
    text = " ".join((text or "").split())
    if not text:
        raise ValidationError({"search": "Type an MRN, phone number, ID number or name."})
    queryset = Patient.objects.all() if queryset is None else queryset
    today = hospital_today()
    country = get_deployment_organization().country
    looks_like_number = any(char.isdigit() for char in text) or "@" in text
    if looks_like_number:
        for matched_on, ids in (
            (MatchedOn.MRN, lambda: _by_mrn(text)),
            (MatchedOn.PHONE, lambda: _by_phone(text, country)),
            (MatchedOn.ID_NUMBER, lambda: _by_id_number(text, country)),
        ):
            found = ids()
            if found:
                patients = _filtered(queryset.filter(pk__in=found), filters, today)
                return Search(patients.order_by("-created_at"), matched_on)
        if not re.search(r"[^\W\d_]", text):
            # Only a number, and nobody has it: say so, rather than read it as a name and age.
            return Search(queryset.none(), _number_kind(text, country))
    words, age = _name_words(text)
    letters = sum(len(re.sub(r"[\W\d_]", "", word)) for word in words)
    if letters < MIN_NAME_LETTERS:
        raise ValidationError(
            {
                "search": f"Type at least {MIN_NAME_LETTERS} letters of the name, or the MRN, "
                "phone number or ID number."
            }
        )
    if age is not None and filters.age is None:
        filters = Filters(sex=filters.sex, age=age)
    patients = _by_name(_filtered(queryset, filters, today), words)
    return Search(patients, MatchedOn.NAME)
