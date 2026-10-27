"""Feature catalog (HIMS-ORG-004, spec 4.1 "configuration and feature flags by organization,
country and facility", 31.4 "documented schema for settings such as feature flags").

Features are declared here, in code, with their defaults; each hospital's choices are stored in
``feature_flags`` (see models.py). Add a feature here when a module is built. A feature that is
not yet built is listed with ``available=False`` so hospitals can see what is coming, but it can
not be switched on.

How a feature's value is decided (first match wins):
1. Not available yet, or not offered in the hospital's country -> off.
2. The facility's own setting (only for features that apply per facility).
3. The hospital-wide setting.
4. The default for the hospital's country, else the general default.
"""

from dataclasses import dataclass, field

ORGANIZATION = "organization"  # one setting for the whole hospital
FACILITY = "facility"  # hospital-wide setting, which each facility may override


@dataclass(frozen=True)
class Feature:
    key: str
    name: str
    description: str
    category: str
    scope: str
    default: bool
    country_defaults: dict[str, bool] = field(default_factory=dict)
    countries: frozenset[str] | None = None  # None = offered in every country
    available: bool = True
    planned_phase: str = ""  # shown while not available, e.g. "Phase 2"
    public: bool = False  # readable before sign-in (e.g. to show "Forgot password?")


SECURITY = "Sign-in and security"
SETUP = "Hospital setup"
CLINICAL = "Clinical modules"
FINANCE = "Billing and insurance"
INTEGRATIONS = "Integrations"


def _planned(key, name, description, category, phase, countries=None) -> Feature:
    return Feature(
        key=key,
        name=name,
        description=description,
        category=category,
        scope=FACILITY,
        default=False,
        countries=frozenset(countries) if countries else None,
        available=False,
        planned_phase=phase,
    )


FEATURES: tuple[Feature, ...] = (
    # --- Live today ----------------------------------------------------------------------------
    Feature(
        key="auth.self_service_password_reset",
        name="Forgot-password emails",
        description="Staff can reset a forgotten password themselves from the sign-in page with "
        "an emailed link. When off, only an administrator can send a reset link (admin console).",
        category=SECURITY,
        scope=ORGANIZATION,
        default=True,
        public=True,
    ),
    Feature(
        key="auth.two_factor_for_everyone",
        name="Two-factor sign-in for all staff",
        description="Everyone must use an authenticator app to sign in, not only administrators "
        "(who always must). Staff without one are asked to set it up at their next sign-in.",
        category=SECURITY,
        scope=ORGANIZATION,
        default=False,
    ),
    Feature(
        key="locations.module",
        name="Locations and beds",
        description="Buildings, floors, wards, rooms and beds, and bed status. When off for a "
        "facility, its Locations page and API are closed (the admin console still shows them).",
        category=SETUP,
        scope=FACILITY,
        default=True,
    ),
    # --- Planned (spec 20): visible so hospitals can plan, not switchable until built -------------
    _planned(
        "patients.registration",
        "Patient registration",
        "Register patients, MRN, duplicate detection and patient search.",
        CLINICAL,
        "Phase 2",
    ),
    _planned(
        "outpatient.appointments",
        "Appointments and outpatient visits",
        "Doctor calendars, appointments, consultations and clinical notes.",
        CLINICAL,
        "Phase 2",
    ),
    _planned(
        "inpatient.admissions",
        "Admissions, transfers and discharge",
        "Admit patients to beds, transfer them and discharge them.",
        CLINICAL,
        "Phase 3",
    ),
    _planned(
        "nursing.care",
        "Nursing care",
        "Nursing assessments, daily care tasks, vital charts and handovers.",
        CLINICAL,
        "Phase 3",
    ),
    _planned(
        "pharmacy.module",
        "Pharmacy and medication",
        "Prescriptions, dispensing, pharmacy stock and medication administration records.",
        CLINICAL,
        "Phase 4",
    ),
    _planned(
        "laboratory.module",
        "Laboratory",
        "Lab orders, specimen tracking and results.",
        CLINICAL,
        "Phase 4",
    ),
    _planned(
        "radiology.module",
        "Imaging / radiology",
        "Imaging orders and reports.",
        CLINICAL,
        "Phase 4",
    ),
    _planned(
        "billing.module",
        "Billing and payments",
        "Charges, invoices, payments and reconciliation.",
        FINANCE,
        "Phase 5",
    ),
    _planned(
        "insurance.us_payers",
        "US insurance (Stedi)",
        "Eligibility checks, prior authorization and claims with US payers.",
        FINANCE,
        "Phase 5",
        countries={"US"},
    ),
    _planned(
        "insurance.india_tpa",
        "Indian insurers, TPAs and government schemes",
        "Pre-authorization and claims with Indian insurers, TPAs and schemes.",
        FINANCE,
        "Phase 5",
        countries={"IN"},
    ),
    _planned(
        "portal.patient",
        "Patient portal",
        "Patients see appointments, reports and bills online.",
        INTEGRATIONS,
        "Phase 6",
    ),
    _planned(
        "integrations.abdm",
        "ABDM (Ayushman Bharat Digital Mission)",
        "ABHA IDs and health-record exchange in India.",
        INTEGRATIONS,
        "Phase 6",
        countries={"IN"},
    ),
)

BY_KEY: dict[str, Feature] = {feature.key: feature for feature in FEATURES}


class F:
    """Keys used in code, so a typo fails at import time rather than silently."""

    SELF_SERVICE_PASSWORD_RESET = BY_KEY["auth.self_service_password_reset"].key
    TWO_FACTOR_FOR_EVERYONE = BY_KEY["auth.two_factor_for_everyone"].key
    LOCATIONS = BY_KEY["locations.module"].key
