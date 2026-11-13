# Patient registration (HIMS-PAT-001)

Phase 2 → Spec §4.5, §13 → Slice 2A. Rules: [Phase 2 P0 part 01](../p0/phase-2-patients/01-functional-requirements.md)
section 1. Tables: [patients](../architecture/data-architecture/patients.md). ID numbers:
[ADR-036](../decisions/ADR-036-patient-id-numbers.md).

**Synthetic data only** until LEGAL closes D6, D7, D9 and D24 and the paid hosting stage is done.

## Who can do what

| Role | Patients menu | Register and correct | Open a record |
|---|---|---|---|
| Receptionist / front desk (assign at a facility) | ✅ | ✅ at that facility | ✅ any patient of the hospital |
| Medical records officer | ✅ | ✅ | ✅ |
| Hospital administrator, head of department | ✅ | — (P0 part 04: administrators run the hospital, they do not register) | ✅ |
| Auditor, basic staff | — | — | — |

To let someone register: **Staff → (person) → Access → Give access → Receptionist / front desk**,
at their branch.

## Register a patient (screens)

1. **Patients → look the person up first** by MRN (search by phone and name comes with
   HIMS-PAT-002).
2. **Register new patient.** Required: a name (one name is enough), sex, the date of birth **or**
   the age (years, months for babies, days for newborns), and a mobile **or** "No phone".
   An age gives an estimated date of birth (1 July of the birth year), marked "~" in the list.
3. Optional: address (give the state), people (a child under 18 needs a mother, father or
   guardian, or a reason why not), ID numbers, consent (privacy notice, SMS, email).
4. **Register.** The MRN is given at once (e.g. `MRN-00000123`) and the record opens.

Unknown or unconscious patient: tick it, give the sex, an approximate age and how they arrived.
The name is "Unknown" until corrected.

## On the record

* **Correct details**: a changed name keeps the old one under "Earlier names" (still found).
* **Contact**: add, change, make the main one, or **End** (kept as ended).
* **People**: add, change or end.
* **ID numbers**: shown masked (`XXXX XXXX 1234`); a wrong one is **ended with a reason** and the
  right one added. The same Aadhaar, ABHA, passport or SSN on a second patient is refused with the
  first patient's MRN.
* **Consent**: record a new decision; earlier ones stay, greyed.

Every opening of a record is in the **Audit log** ("Patient record opened").

## Admin console

**Patients** section: Patients, Patient contacts, Patient relationships, Patient identifiers
(masked; add one by typing the number, end one with a reason), Patient consents, Patient aliases
(read only). The console shows patients to people who may open them, and changes them only for
people who may register them; every change goes through the same rules and audit as the screens.
Opening a patient's page in the console is audited too.

## Feature switch

**Features → Patient registration** (on by default). Off for a facility: nobody registers
there; patients already registered are still found and opened.

## Demo hospitals

Each demo branch has 40 invented patients and one unknown patient, registered by
`frontdesk.<branch>@<key>.demo.test`; `records@<key>.demo.test` is the medical records officer.
After this merge run the demo set-up again with `--reset` ([demo hospitals](../testing/demo-hospitals.md)).

**Update 2026-11-13 (HIMS-PAT-002):** step 1 now has the full search: the MRN (or only its
number), a phone number, an ID number or a name in any spelling and order, with sex and age. See
[patient search](patient-search.md).

**Note (2026-11-12):** administrators cannot register patients, but they can give the Receptionist / front desk role (anyone who may open patient records may hand out patient roles; decisions log row 21). The supplier's support account cannot.
