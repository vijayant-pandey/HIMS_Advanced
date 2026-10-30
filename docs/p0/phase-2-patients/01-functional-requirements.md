# 01 Functional requirements (P0-A)

DRAFT. Decision numbers (D1…) refer to the [README](README.md). Rules marked **[DR]** need the
reviewing doctor's confirmation; **[PO]** yours.

Common to every action below: the server checks the permission (part 04), writes an audit event
with who/when/what (before and after values), uses a version check on edits (a stale save is
refused with "This record changed since you loaded it"), and create requests accept an
`Idempotency-Key` so a double click never creates two records.

## 1. Patient registration (spec 4.5)

**Actors:** Receptionist; also nurse or doctor for walk-ins (D1).

**Main flow**
1. Search first (section 2). If the person is found, open them; do not register again.
2. "Register new patient": enter the details below → Save.
3. The duplicate check runs (section 3). If there are likely matches, the screen shows them; the
   receptionist opens one, or ticks "This is a different person" and gives a reason.
4. Saved: the **MRN** is issued from the hospital's MRN numbering scheme in the same transaction
   (already built: numbering, HIMS-ORG-003). The patient chart opens.

**Fields** (D2; required in bold)

| Group | Fields |
|---|---|
| Name | **Given name** (one name is enough), middle name, family name, preferred name, title |
| Birth | **Date of birth**, or **age** in years (then DOB is stored as estimated: 1 July of the birth year and marked "estimated"); for babies: age in months/days |
| Sex | **Sex** (male / female / intersex / unknown); US only, optional: gender identity, pronouns |
| Contact | **Mobile** (or tick "no phone"), alternate phone, email, preferred language |
| Address | Line 1, line 2, city/town, district (IN) / county (US), **state**, PIN/ZIP, country |
| People | Guardian/parent (required if under 18 **[DR]**), next of kin, emergency contact, caregiver: name, relation, phone, "also a patient here" link |
| ID numbers | Per country (part 05): ABHA number/address, last 4 of Aadhaar, passport, voter ID, driving licence, previous hospital's MRN; US: driver licence, passport, previous MRN |
| Other | Marital status, occupation, blood group (patient-reported, marked unverified), restricted-record flag (D23) |
| Consent | Privacy notice given and accepted (D9); SMS consent; email consent |

**Rules**
- Names: any script; trimmed; no digits. Date of birth not in the future, not more than 130 years
  ago. Phone normalised to international format (+91…, +1…) using the hospital's country.
- Unknown patient (D3): "Unknown" + sex + approximate age + arrival note; flagged until
  identified; the duplicate check runs again when real details are added.
- Editing demographics later: allowed for the same roles; every change audited with before/after.
  Name changes keep the old name as an **alias** (still searchable).
- Deceased: recorded by a doctor with date/time (and later the death workflow, Phase 3); the
  record becomes read-only except for corrections by medical records.

**Errors:** missing required field; impossible DOB; invalid phone; MRN scheme not set up
("Ask your administrator to set up MRN numbering"); duplicate ID number of the same unique type
already on another patient (blocked, shows that patient).

## 2. Patient search

- One search box: MRN (exact), phone (exact after normalising), ID number (exact), or name
  (similar spelling, any order) optionally with age/DOB or sex.
- Results show only: name, MRN, age and sex, phone (last 4 digits), last visit date and
  department. Restricted records (D23) appear only to those allowed.
- At most 50 results; a too-broad search asks for more detail.
- Every search and every chart opened is recorded in the audit log (spec 13.4 "viewing a patient
  record").

## 3. Duplicates and merging (D4, D5)

**Detection** (on registration and on demographic edits):

| Strength | Rule |
|---|---|
| Certain | Same unique ID number (ABHA, previous MRN, passport) → blocked |
| Likely | Similar name (≥ 0.6 similarity, either name order) **and** same DOB or birth year ±1 |
| Likely | Same phone **and** similar name (phones are shared in families, so phone alone is not enough) |

Overriding a warning needs a reason and is audited. Overridden pairs and pairs found later go to
the **Possible duplicates** list for medical records.

**Merge** (two-person rule): officer A picks the record to keep and the duplicate → reviews a
side-by-side comparison → requests merge with a reason → officer B (or an admin) approves. On
completion: all visits, appointments, notes, diagnoses, allergies, vitals and identifiers move to
the kept record; the duplicate's MRN becomes an alias of the kept record (old printouts still
find the patient); the duplicate is marked "merged into MRN …" and becomes read-only. Every moved
row is listed in the merge record, so the merge can be **undone within 30 days** (D5) by the same
two-person process. Merges never delete anything.

## 4. Doctor schedules and appointments (spec 4.6)

**Schedules:** per doctor, facility and department: weekday sessions (e.g. Mon 09:00–13:00), slot
length (default 10 min), maximum extra bookings (D11), valid from/to; exceptions for leave,
holidays and extra sessions. Managed by department admin/HOD or a scheduler role.

**Booking:** choose department (or service) → doctor → day → free slot → patient (search or
quick-register) → type (new / follow-up) → reason (short). Rescheduling keeps a link to the old
appointment. Cancellation needs a reason (patient request / hospital / doctor unavailable).
Booking a slot that is already taken is refused, even if two people try at the same moment
(database rule).

**Walk-ins and tokens (D10):** a walk-in is checked in directly and gets the next token number for
that doctor and day. Booked patients get their token at check-in. The **OPD queue** screen shows
tokens per doctor: waiting, with doctor, done.

**Day of visit:** check-in (front desk) → vitals (nurse, optional) → consultation (doctor) →
completed. Not checked in by the end of the session → **no-show** (D12).

**Reminders:** email reminder the day before, if the patient agreed to email (D9). SMS/WhatsApp
come with an SMS vendor (blocked: DLT registration in India).

**Not in Phase 2:** waitlist [PO to confirm], online self-booking (portal, Phase 6), telemedicine.

## 5. Outpatient visit (encounter) (spec 4.7)

- Created at **check-in** (booked or walk-in) with a **visit number** from the encounter numbering
  scheme (already built). One visit per check-in.
- Holds: patient, facility, department, doctor, appointment (if any), reason/chief complaint,
  arrival time, start of consultation, end time, status (part 03).
- Doctor's worklist: "My patients today" from the queue; opening a patient starts the
  consultation.
- Finishing the visit requires the consultation note to be **signed** **[DR]**; otherwise the
  doctor can leave it "in progress" and the note stays a draft (D17).
- A visit created in error (wrong patient) is marked **entered in error** with a reason by
  medical records; its clinical entries are shown struck through, never deleted.

## 6. Clinical recording in the visit

**Vitals (D20)**

| Measurement | Unit | Refused if outside (impossible) | Flagged abnormal if outside **[DR to set]** |
|---|---|---|---|
| Systolic / diastolic BP | mmHg | 40–300 / 20–200; systolic > diastolic | 90–139 / 60–89 |
| Pulse | /min | 20–250 | 60–100 |
| Temperature | °C (°F shown in US) | 30–45 °C | 36.1–37.8 °C |
| Respiratory rate | /min | 4–80 | 12–20 |
| SpO₂ | % | 50–100 | ≥ 94 |
| Height | cm (in shown in US) | 30–250 | — |
| Weight | kg (lb shown in US) | 0.3–400 | — |
| BMI | kg/m² (calculated) | — | 18.5–24.9 |
| Pain score | 0–10 | outside 0–10 | ≥ 7 |

Children's normal ranges differ by age **[DR: provide or approve paediatric ranges; until then
no abnormal flags for under-18s]**. Corrections: a wrong value is marked "entered in error" with
a reason and re-entered; the original stays visible in history.

**Allergies (D19)** are recorded on the **patient** (not the visit): substance (text), category,
reaction(s), severity (mild/moderate/severe), status (active/inactive/resolved), verification
(unconfirmed/confirmed/refuted), onset, note. "No known allergies" is a separate explicit entry;
"Allergies not yet asked" is shown when nothing is recorded. The chart header always shows active
allergies in red.

**Diagnoses (D18):** searched from the ICD catalogue of the hospital's country; type
(working/provisional/final), primary or secondary for the visit, status (active/resolved),
onset date. Free text only with a reason (coded later by medical records).

**Consultation note (D15, D16):** sections Complaint, History, Examination, Assessment, Plan;
saved as a **draft** automatically; **sign** locks it; **amend** after signing creates a new
version with a reason (all versions kept and viewable); **addendum** adds text without changing
the original; **entered in error** for the wrong patient (reason; struck through).

**Patient-reported current medicines (D21, proposal):** name, dose, how often, since when, source
(patient / relative / previous prescription). Not orders; clearly labelled "as reported".

## 7. Patient chart (spec 15.3)

- **Header (always visible):** name, MRN, age/sex, active allergies (or "No known allergies" /
  "Not asked"), restricted flag, unknown-patient flag, deceased flag.
- Tabs: Overview (problems = active diagnoses, allergies, current medicines, last vitals, upcoming
  appointments), Visits (timeline), Notes, Vitals (table and trend), Demographics, Audit (for
  medical records/auditors).

## 8. Basic reports

- **Visit summary** (print/PDF): patient, visit, vitals, diagnoses, signed note, doctor's name and
  registration number.
- **OPD daily list** per department/doctor: booked, checked in, seen, no-show; counts.
- **Unsigned notes** older than 24 hours (D17); **possible duplicates** list.

## 9. Side effects (per action)

| Action | Audit event | Other effects |
|---|---|---|
| Register / edit patient | `patient.registered` / `patient.updated` | MRN issued; duplicate check; outbox `patient.registered` |
| Search / open chart | `patient.searched` / `patient.chart.viewed` | — |
| Merge requested / approved / undone | `patient.merge.*` | Records moved; email to approver |
| Book / reschedule / cancel / check in / no-show | `appointment.*` | Email confirmation/reminder if consented |
| Start / finish visit, entered in error | `encounter.*` | Visit number issued at check-in |
| Vitals / allergy / diagnosis / note sign / amend | `clinical.*` | Allergy header refresh |
| Emergency access | `access.emergency` | Email to medical records officer |

## 10. Exception cases that must work (spec 26.1)

| Case | Expected behaviour |
|---|---|
| Two receptionists book the same slot at the same moment | One succeeds; the other sees "This slot was just taken" |
| Registration double-click / network retry | One patient, one MRN (idempotency) |
| MRN numbering not configured for the hospital | Registration refused with a clear message; nothing half-saved |
| Patient arrives for an appointment that was cancelled | Front desk can check them in as a walk-in |
| Doctor goes on leave with bookings | Schedule exception lists affected appointments to reschedule/cancel (with reason, notification) |
| Note being edited in two tabs | Second save refused (version); no lost text without warning |
| Visit opened for the wrong patient | Entered in error by medical records; entries struck through; audit kept |
| Duplicate found after both records have visits | Merge (two-person), undo possible for 30 days |
| Unknown patient later identified as an existing patient | Merge into the existing record |
| Patient under 18 without guardian | Warning; allowed for emergencies with reason **[DR]** |
