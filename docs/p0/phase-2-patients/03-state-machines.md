# 03 State machines (P0-C)

DRAFT. Format from spec 26.3. **No screen or API may change a `status` directly**: each change
is a named action in the domain service, which checks the guard, locks the row, checks the
version, writes the audit event and (where listed) an outbox event, all in one transaction.
Any action not listed below is refused (409 `INVALID_TRANSITION`).

Columns: current → **action** → next · guard · who (permission, part 04) · audit event ·
outbox event · retry/recovery.

## Patient record

| Current | Action | Next | Guard | Who | Audit | Outbox |
|---|---|---|---|---|---|---|
| (none) | register | active | required fields; duplicate check passed or overridden with reason; MRN issued in same transaction | `patients.register` | patient.registered | patient.registered |
| active | update demographics | active | version matches; unique IDs still unique | `patients.register` | patient.updated (before/after) | — |
| active | record death | active (deceased_at set) | doctor; time not in future | `clinical.record` (doctor) | patient.deceased | patient.deceased |
| active | merge completes (as duplicate) | merged | approved merge | system (merge) | patient.merged | patient.merged |
| merged | merge undone | active | within 30 days; approved undo | system (merge) | patient.unmerged | patient.unmerged |

Retry: registration is idempotent (`Idempotency-Key`); a failed transaction issues no MRN (the
number is taken inside the same transaction, so no gaps or reuse).

## Merge (D5)

| Current | Action | Next | Guard | Who | Audit |
|---|---|---|---|---|---|
| (none) | request | requested | two different active patients; no open merge for either | `patients.merge` | patient.merge.requested |
| requested | approve | completed | approver ≠ requester; both still active; versions unchanged | `patients.merge` | patient.merge.approved + patient.merged |
| requested | reject | rejected | reason | `patients.merge` | patient.merge.rejected |
| requested | cancel | rejected | requester only | `patients.merge` | patient.merge.cancelled |
| completed | request undo | completed (undo requested) | ≤ 30 days; reason | `patients.merge` | patient.merge.undo_requested |
| completed (undo requested) | approve undo | undone | approver ≠ requester | `patients.merge` | patient.merge.undone |

Approve = one transaction: lock both patients, move every row listed in part 02 (recording each
move), add the merged MRN as an alias, mark the duplicate merged. Undo moves exactly the
recorded rows back (rows created after the merge stay on the kept record and are listed for
manual review).

## Appointment

| Current | Action | Next | Guard | Who | Audit |
|---|---|---|---|---|---|
| (none) | book | booked | slot inside a session, not in the past, free (exclusion constraint) or extra allowed | `appointments.manage` | appointment.booked |
| booked | reschedule | cancelled (+ new booked) | new slot free; reason | `appointments.manage` | appointment.rescheduled |
| booked | cancel | cancelled | reason | `appointments.manage` | appointment.cancelled |
| booked | check in | checked_in (+ encounter `arrived`) | on the appointment day | `appointments.manage` | appointment.checked_in, encounter.arrived |
| (none) | walk in | checked_in (+ encounter) | doctor has a session today | `appointments.manage` | appointment.walk_in |
| checked_in | start consultation | in_consultation | doctor of the appointment (or same department) | `encounters.manage` | encounter.started |
| in_consultation | finish | completed | encounter finished | `encounters.manage` | encounter.finished |
| booked | mark no-show | no_show | session ended (automatic job) or front desk | system / `appointments.manage` | appointment.no_show |
| no_show | undo no-show | booked | same day | `appointments.manage` | appointment.no_show_undone |

Retry: the no-show job is safe to run repeatedly (only `booked` past sessions). Email
reminders/confirmations go through the outbox (sent once, retried on failure).

## Encounter (outpatient)

| Current | Action | Next | Guard | Who | Audit |
|---|---|---|---|---|---|
| (none) | arrive (check-in / walk-in) | arrived | visit number issued in the same transaction | `appointments.manage` | encounter.arrived |
| arrived | start | in_progress | doctor of the department | `encounters.manage` | encounter.started |
| in_progress | finish | finished | consultation note signed **[DR: D-rule, part 01 §5]** | `encounters.manage` | encounter.finished |
| arrived | cancel | cancelled | patient left before being seen; reason | `appointments.manage` | encounter.cancelled |
| any | mark entered in error | entered_in_error | reason; medical records | `patients.records_correct` | encounter.entered_in_error |
| finished | reopen | in_progress | same day, attending doctor, reason **[DR]** | `encounters.manage` | encounter.reopened |

## Clinical note (D16)

| Current | Action | Next | Guard | Who | Audit |
|---|---|---|---|---|---|
| (none) | create draft | draft | encounter arrived/in_progress | `clinical.notes.write` | clinical.note.created |
| draft | save | draft | author only; version | `clinical.notes.write` | clinical.note.saved (no content in audit) |
| draft | sign | signed | author only; required sections (Assessment, Plan) **[DR]** | `clinical.notes.sign` | clinical.note.signed |
| signed / amended | amend | amended | reason; new version, older versions kept | `clinical.notes.sign` | clinical.note.amended |
| signed / amended | addendum | (unchanged) | reason; appended version | `clinical.notes.write` | clinical.note.addendum |
| any | entered in error | entered_in_error | reason; author or medical records | `clinical.notes.sign` / `patients.records_correct` | clinical.note.entered_in_error |

Signed content can never be edited (database trigger on `clinical_note_versions`).

## Vital sign, allergy, diagnosis, reported medication

| Entity | Allowed changes |
|---|---|
| Vital sign | final → entered_in_error (reason). No edits: re-enter the correct value. |
| Allergy | active ⇄ inactive; active → resolved; any → entered_in_error (reason); verification unconfirmed → confirmed/refuted; edits of reactions/severity with version and audit |
| Diagnosis | active → resolved (date); certainty working → provisional → final; any → entered_in_error (reason); code change only before the visit is finished, after that = new diagnosis + old one entered in error |
| Reported medication | active → stopped (date); any → entered_in_error |

## Emergency access (D14)

| Current | Action | Next | Guard | Who | Audit |
|---|---|---|---|---|---|
| (none) | request | active (4 h) | reason ≥ 10 characters; user holds `clinical.emergency_access` | doctor/nurse | access.emergency (email to medical records) |
| active | expire | expired | time passed | system | — |
| expired | review | reviewed | reviewer ≠ user | `patients.records_correct` | access.emergency.reviewed |
