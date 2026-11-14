# Restricted records and emergency access (HIMS-PAT-006)

Phase 2 → Spec §4.5, §13 → Slice 2A. Rules: [Phase 2 P0 part 04](../p0/phase-2-patients/04-roles-and-permissions.md)
("Restricted records (D23) need `patients.restricted` or emergency access"), [part 03](../p0/phase-2-patients/03-state-machines.md)
("Emergency access (D14)") and the [P0 decisions](../p0/phase-2-patients/README.md) D14 and D23.
The chart itself: [patient chart](patient-chart.md). Finding patients: [patient search](patient-search.md).

**Synthetic data only** until LEGAL closes D6, D7, D9 and D24 and the paid hosting stage is done.

## What it is for

Some patients need more privacy than others: a VIP or public figure, a member of staff (or their
family), or someone who asks for it. Medical records mark such a record **restricted**. From then
on:

| Who | Patient search | Opening the record |
|---|---|---|
| **Medical records officer** (`patients.restricted`) | Found as usual, with a red **Restricted** chip | Opens it. Every opening is recorded as a restricted opening |
| **Doctor or nurse** (`clinical.emergency_access`: today the **Head of department** role; the Doctor and OPD nurse roles get it with HIMS-CLIN-*) | Not found by name, phone or ID number. Its **exact MRN** shows one row, **Restricted record**, with nothing about the patient | Sees **Restricted record** and can open it with **emergency access**: 4 hours, with a reason. Medical records are emailed at once |
| **Everyone else who may open patients** (front desk, hospital administrator) | As for the doctor | Sees **Restricted record**: "ask medical records". No emergency access (P0 part 04: front desk and administrators have none) |
| **Admin console** without `patients.restricted` | Restricted patients, their contacts, people, ID numbers, consents and earlier names are not listed anywhere | — |

The software supplier's support account never holds any of the three permissions (they are patient
data, spec 7.2). All three need two-factor sign-in (P0 part 04, ★).

## Restrict a record, or lift the restriction (medical records)

1. Open the patient (**Patients** → search → the MRN).
2. In the header, click **Restrict record**. Choose **Why** (VIP or public figure; member of staff;
   other) and type the **Reason** (at least 10 characters; kept in the audit log). **Restrict record**.
3. The header shows a red **Restricted record** chip and an alert: "Restricted record (…): hidden from
   patient search. Every opening is recorded and reviewed by medical records."

To lift it: **Lift restriction** in the header, with a reason. In the admin console: **Patients → the
patient → Restricted record** (choose, give the reason, Save).

## Emergency access (doctors and nurses)

1. Search the patient's **exact MRN** (from the patient's card or wristband) and click it, or open a
   link to the record.
2. The screen says **Restricted record**. Type the **Reason for emergency access** (at least 10
   characters, e.g. "Unconscious in the emergency room") and click **Open with emergency access**.
3. The chart opens with a yellow banner: "You opened this restricted record with emergency access
   until …". It lasts **4 hours**. Click **End emergency access** when you no longer need it.

Medical records get an email ("emergency access to a patient record": who and when, never the
patient or the reason). Asking again while it is open is refused ("You already have emergency access
… until …").

## Review (medical records, weekly by habit)

**Menu → Emergency access** (`patients.records_correct`):

| Tab | Shows |
|---|---|
| **To review** | Emergency access that has ended (after 4 hours or ended early) and waits. **Review** → **Appropriate**, or **Not appropriate (follow up)** with a note (required) → **Save review** |
| **Open now** | Emergency access still running (it cannot be reviewed until it ends) |
| **Reviewed** | Outcome, who reviewed it, when, the note |
| **Restricted record openings** | Every opening of a restricted record in the last 7, 30 or 90 days: when, which MRN, who, where, how (**Medical records** or **Emergency access**). Viewing this list is recorded in the audit log |

Nobody reviews their own emergency access (the screen says "Your own: someone else reviews it"; the
server and the database refuse it too). The admin console has the same list: **Patients → Emergency
access** (the outcome and note can be filled in once it has ended).

## Audit log

| Event | When |
|---|---|
| Patient record restricted (VIP or staff) / Patient record's restriction lifted | With the reason and before/after |
| Emergency access to a patient record opened (4 hours) | With the reason |
| Emergency access to a patient record ended early | |
| Emergency access to a patient record reviewed | With the outcome and note |
| Patient record opened | As before; for a restricted record also `restricted: true` and how (`via`) |
| List of restricted record openings viewed | |
| Permission denied | Someone tried to open a restricted record without the right (code `RESTRICTED_RECORD`) |

All of them show on the record's **History** tab for medical records.

## API

| Method | Path | Permission | Notes |
|---|---|---|---|
| GET | `/api/v1/patients/?search=` and `?mrn=` | `patients.search` | Restricted records left out for people without `patients.restricted`, except an exact MRN: that row has `hidden: true` and no name, age, sex or phone. Every row has `is_restricted` |
| GET | `/api/v1/patients/{id}/` (and every change to the record) | `patients.view` | `403 RESTRICTED_RECORD` unless `patients.restricted` or open emergency access. Adds `is_restricted`, `restriction`, `restriction_label`, `emergency_access` (yours, while open) |
| POST | `/api/v1/patients/{id}/restriction/` | `patients.restricted` | `restricted`, `restriction` (vip, staff, other), `reason`, `version` |
| POST | `/api/v1/patients/{id}/emergency-access/` | `clinical.emergency_access` | `reason` (10+ characters). `409 EMERGENCY_ACCESS_NOT_NEEDED` (not restricted, or you may open it anyway), `409 EMERGENCY_ACCESS_OPEN` |
| POST | `/api/v1/patients/{id}/emergency-access/end/` | `clinical.emergency_access` | Ends yours early |
| GET | `/api/v1/patients/restricted-openings/?days=7` | `patients.records_correct` | Paginated; audited |
| GET | `/api/v1/patient-emergency-access/?state=to_review` | `patients.records_correct` | `active`, `to_review`, `reviewed`; `patient_id=` |
| POST | `/api/v1/patient-emergency-access/{id}/review/` | `patients.records_correct` | `outcome` (appropriate, not_appropriate), `note`, `version`. `409 STILL_OPEN`, `ALREADY_REVIEWED`, `SAME_PERSON` |

## Try it (demo hospitals)

After `setup_demo_hospitals --reset` (or, on the hosted Development hospital, `add_demo_restricted_records`;
[Render + Neon section 8](render-neon-hosting.md)): per branch one adult's record is restricted (the
first branch: a VIP; the others: a member of staff). The rebuild prints the VIP's MRN as
**restricted record**. Then:

* `frontdesk.<branch>@<hospital>.demo.test`: the VIP's name finds nothing; the MRN shows **Restricted
  record**; opening it says "ask medical records".
* `hod.<branch>@<hospital>.demo.test` (head of department): the same, plus **Open with emergency
  access**.
* `records@<hospital>.demo.test` (medical records): finds and opens it; **Emergency access** in the
  menu shows one emergency access by the first branch's head of department **to review** and one
  already **reviewed**, and the openings.

On a demo hospital on the PC two-factor is switched off; on Render the head of department and
medical records accounts must now set up two-factor at their next sign-in (P0 part 04, ★).

## After pulling this change

Run `python manage.py migrate` (local India, local US and Neon): migration `patients.0003` adds the
restricted columns and the `patient_emergency_access` table, and the roles get their new
permissions. Then rebuild the PC demo hospitals with `--reset`.
