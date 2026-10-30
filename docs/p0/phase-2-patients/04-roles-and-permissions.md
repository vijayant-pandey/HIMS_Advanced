# 04 Roles and permissions (P0-D)

DRAFT. Extends the existing catalogue (`backend/apps/access_control/catalog.py`,
[RBAC document](../../status/Hospital_Departments_and_Doctors_RBAC.MD)). Same rules as today:
default deny, checked on the server, scope by facility/department, nobody grants themselves
access, two-factor required where marked ★. Phase 2 adds **patient-level** rules (who may open
which chart, D13).

## New permissions

| Permission | Allows | 2FA |
|---|---|---|
| `patients.search` | Search and see the minimal result list (name, MRN, age/sex, last visit) | |
| `patients.view` | Open demographics, contacts, identifiers (masked), relationships | |
| `patients.register` | Register patients; edit demographics, contacts, relationships, consents | |
| `patients.merge` | Request/approve merges and undo (two different people needed) | ★ |
| `patients.records_correct` | Mark visits/notes entered in error; review emergency access; possible duplicates list | ★ |
| `patients.restricted` | See restricted (VIP/staff) records in search | ★ |
| `appointments.view` | See calendars, queues, OPD lists | |
| `appointments.manage` | Book, reschedule, cancel, check in, walk in, no-show | |
| `schedules.manage` | Doctor sessions and exceptions | |
| `encounters.manage` | Start, finish, reopen visits | |
| `clinical.view` | Read clinical data (vitals, allergies, diagnoses, notes) of patients in scope | |
| `clinical.record` | Record vitals, allergies, diagnoses, reported medicines; record death | |
| `clinical.notes.write` | Create/save drafts, addenda | |
| `clinical.notes.sign` | Sign, amend, mark own notes entered in error | ★ |
| `clinical.emergency_access` | Use break-glass (D14) | ★ |
| `reports.opd` | OPD lists and visit summaries | |

## New system roles (assign at facility or department scope)

| Role | Permissions | Typical scope |
|---|---|---|
| Receptionist / front desk | patients.search, patients.view, patients.register, appointments.view, appointments.manage, reports.opd | Facility |
| OPD nurse | patients.search, patients.view, appointments.view, clinical.view, clinical.record, clinical.notes.write (triage), clinical.emergency_access | Department |
| Doctor (consultant) | patients.search, patients.view, patients.register (walk-ins), appointments.view, encounters.manage, clinical.view, clinical.record, clinical.notes.write, clinical.notes.sign, clinical.emergency_access, reports.opd | Department (several allowed) |
| Medical records officer | patients.search, patients.view, patients.register, patients.merge, patients.records_correct, patients.restricted, clinical.view (read only), reports.opd | Facility / hospital |
| Scheduler (optional) | appointments.view, appointments.manage, schedules.manage | Department |

Existing roles: **Head of department** gains appointments.view, schedules.manage, reports.opd and
the unsigned-notes report for their department **[DR]**. **Organization administrator** keeps
configuration powers but gets **no clinical.view by default** (least privilege; administrators
run the hospital, they do not read charts) **[PO]**. **Auditor** gains read access to the
patient-access audit events (who opened which chart), not to the charts themselves.

## Who may open a patient's clinical record (D13)

A user with `clinical.view` may open the clinical part of a chart when **any** of these holds:

1. The patient has (or had) a visit in a department/facility the user's grant covers; or
2. The patient is booked with or checked in to the user (as doctor) today; or
3. The user has an active emergency access grant for this patient (D14).

Otherwise the chart shows demographics only (if `patients.view`) and offers **Emergency access**
(reason required). Restricted records (D23) need `patients.restricted` or emergency access, and
every opening is reported to medical records weekly.

Every chart opening and every search is audited (`patient.chart.viewed`, `patient.searched`).
Read volume: about 20–50 events per visit; sized in HIMS-DATA-002.

## Matrix (spec 26.4 actions relevant to Phase 2)

| Action | Receptionist | Nurse | Doctor | Medical records | HOD | Admin | Auditor |
|---|---|---|---|---|---|---|---|
| Search patients | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| Register / edit demographics | ✅ | — | ✅ walk-in | ✅ | — | — | — |
| Merge / undo (two people) | — | — | — | ✅ | — | — | — |
| Book / check in | ✅ | — | — | — | — | — | — |
| Doctor schedules | — | — | own (view) | — | ✅ dept | ✅ | — |
| Read clinical record | — | ✅ in scope | ✅ in scope | ✅ read | ✅ dept **[DR]** | — | — |
| Record vitals | — | ✅ | ✅ | — | — | — | — |
| Allergies, diagnoses | — | allergies ✅ | ✅ | — | — | — | — |
| Write / sign note | — | triage draft | ✅ sign | — | — | — | — |
| Amend signed note | — | — | own ✅ | — | — | — | — |
| Entered in error | — | — | own notes | ✅ | — | — | — |
| Emergency access | — | ✅ | ✅ | — | — | — | — |
| See who opened a chart | — | — | — | ✅ | — | — | ✅ |
| Export / print visit summary | — | — | ✅ | ✅ | — | — | — |

**[DR]** to confirm every ✅ in the clinical rows; **[PO]** the rest.
