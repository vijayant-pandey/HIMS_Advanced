"""Invented patients for each demo branch (HIMS-QA-004), ready for Phase 2.

HIMS has no patient tables yet: registration comes with HIMS-PAT-001 (Phase 2). Until then the
``demo_patients`` command shows the patients that will be registered, so the product owner can
see and check them. When HIMS-PAT-001 is built, ``seed.py`` registers them through the patient
service (the same names, every time).

No real identifiers: no Aadhaar, ABHA or Social Security numbers, only made-up phone numbers in
ranges kept for fiction or testing.
"""

import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .hospitals import Hospital
from .people import NameMaker

BLOOD_GROUPS = ("A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-")
ALLERGIES = ("No known allergies", "Penicillin", "Sulfa drugs", "Peanuts", "Latex", "Dust")


@dataclass(frozen=True)
class DemoPatient:
    branch: str
    given_name: str
    family_name: str
    sex: str
    date_of_birth: date
    phone: str
    city: str
    blood_group: str
    allergy: str


def patients_for(hospital: Hospital, per_branch: int = 40, today: date | None = None):
    # The hospital's own "today" (from its time zone), the anchor for invented birth dates.
    today = today or datetime.now(ZoneInfo(hospital.timezone)).date()
    names = NameMaker(hospital.country, f"{hospital.key}-patients")
    pick = random.Random(f"{hospital.key}-patients")  # noqa: S311 - demo data, not security
    for branch in hospital.branches:
        for n in range(per_branch):
            given, family, sex = names.person()
            age_days = pick.randint(0, 90 * 365) if n % 10 else pick.randint(1, 365)  # some babies
            if hospital.country == "IN":
                phone = f"+91 90000 {pick.randint(10000, 99999)}"
            else:
                phone = f"+1 555 01{pick.randint(0, 99):02d}"  # 555-0100..0199: fictional
            yield DemoPatient(
                branch=branch["code"],
                given_name=given,
                family_name=family,
                sex=sex,
                date_of_birth=today - timedelta(days=age_days),
                phone=phone,
                city=branch["city"],
                blood_group=pick.choice(BLOOD_GROUPS),
                allergy=pick.choice(ALLERGIES),
            )
