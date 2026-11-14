# Patient chart: header, overview and record history (HIMS-PAT-005)

Phase 2 → Spec §4.5, §13 → Slice 2A. Rules: [Phase 2 P0 part 01](../p0/phase-2-patients/01-functional-requirements.md)
section 7 (spec 15.3) and [part 04](../p0/phase-2-patients/04-roles-and-permissions.md) ("see who
opened a chart"). Finding the patient: [patient search](patient-search.md). Registering and
correcting: [patient registration](patient-registration.md).

**Synthetic data only** until LEGAL closes D6, D7, D9 and D24 and the paid hosting stage is done.

## Open a chart

**Patients → search → click the MRN.** The chart opens on **Overview**. Every opening is in the
**Audit log** ("Patient record opened"), as before.

## The header (always in view)

The band at the top stays just below the menu bar while you scroll, on every tab:

| Shows | Notes |
|---|---|
| Name, MRN, age and sex | `~` before the age: the date of birth is estimated (registered with an age) |
| **Allergies not asked yet** | Orange outline. Allergies are recorded from the visit screen (HIMS-CLIN-003); then the header shows them in red, or "No known allergies" |
| **Unknown patient** | Registered as unknown or unconscious |
| **Merged into …** | The record was merged (HIMS-PAT-004) |
| Prefers “…” | The preferred name, when given |

Restricted (VIP / staff) and deceased flags come with HIMS-PAT-006 and HIMS-PAT-007.

Under the header, **alerts** that the server works out (the admin console shows the same ones):

| Alert | When |
|---|---|
| This record was merged into … | Merged record |
| Unknown patient: correct the name, date of birth and contacts when known | Unknown patient |
| Under 18 with no parent or guardian recorded | A child without a current parent or guardian |
| The privacy notice is not recorded as given | No privacy notice, or it was refused or withdrawn |
| No phone, email or address recorded | No contact at all and "No phone" not ticked |

## Tabs

| Tab | Who | What |
|---|---|---|
| **Overview** | Everyone who may open patients | **Clinical summary** (allergies, problems, medicines as reported, last vitals, next appointment: "None recorded" until the visit record and appointments arrive), **Contact**, **Guardian and emergency contact**, **ID numbers** (masked), **Consent in force**, **Record** (registered where, when and by whom; last changed; date of birth; earlier names) |
| **Demographics** | Everyone who may open patients | The full record from HIMS-PAT-001: details, contacts, people, ID numbers, consent history, with **Correct details**, **Add**, **Change**, **End** and **Record** for the front desk and medical records |
| **History** | **Medical records officer** only (`patients.history`) | Who opened the record and who changed what, and when, newest first: when, who, where, what, and for a correction the **names** of the fields changed (never the old or new values: those stay in the audit log). Viewing the list is itself audited ("Patient record's history viewed") |

Visits, Notes and Vitals tabs come with HIMS-CLIN-001, HIMS-CLIN-005 and HIMS-CLIN-002.

The tab is kept in the address (`/patients/<id>?tab=history`); nothing about the patient is put
there. Asking for `?tab=history` without the permission shows Overview instead.

**Who else sees who opened a chart:** the **auditor**, in the **Audit log** (filter "Patient
record opened", or the record's id); auditors do not open charts. The hospital administrator does
not see the History tab (P0 part 04: administrators run the hospital, they do not review access).

## Admin console

**Patients → a patient.** A **Chart** section at the top shows the same alerts and the allergy
line. A medical records officer who uses the console also sees **Record history (latest 20)**;
that view is audited with "in: console".

## API

| Method | Path | Permission | Notes |
|---|---|---|---|
| GET | `/api/v1/patients/{id}/` | `patients.view` | Now also `allergy_status` (`not_asked`) and `alerts` (`code`, `severity`, `message`), most important first. Audited |
| GET | `/api/v1/patients/{id}/history/` | `patients.history` | Paginated (50); `occurred_at`, `action`, `action_label`, `actor_name`, `facility_name`, `outcome`, `changed` (field names), `reason`. Audited as `patient.history.viewed` |

## Try it (demo hospitals)

After `setup_demo_hospitals --reset` (or the hosted Development seed), sign in as the front desk
(`frontdesk.<branch>@<hospital>.demo.test`): the seed prints two MRNs under "Try these on Patients
-> Search" marked **chart alert** (a child brought in without a guardian, and an adult whose
privacy notice is still to be given). Every branch's unknown patient shows three alerts. Sign in as
`records@<hospital>.demo.test` (medical records officer) to see the **History** tab.

## After pulling this change

No new tables. Run `python manage.py migrate` anyway (local India, local US and Neon): it gives
the medical records officer role its new permission (roles are brought up to date after every
`migrate`).
