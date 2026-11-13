# ADR-036: Patient ID numbers: encrypted, masked, found by a keyed fingerprint

**Status:** Proposed (2026-11-12) · **Items:** HIMS-PAT-001 · **Spec:** 4.5, 13.3, 26.7

## Context

Registration records identity document numbers: ABHA number and address, Aadhaar, passport, voter
ID, driving licence, a previous hospital's MRN, and in the US the Social Security number. The PO
decided on 2026-10-30 (P0 decisions D6, D7, D8) that Aadhaar and SSN may be typed in now, marked
"not verified", **stored encrypted and shown masked**, with verification when UIDAI / ABDM are
connected (Phase 6). LEGAL confirmed this for now on 2026-11-08 and keeps it as a go-live item
(Aadhaar Data Vault rules).

Two needs pull against each other:

* the full number must not be readable in screens, the admin console, the audit log, logs or a
  stolen database copy;
* the front desk must still be stopped when the same number is typed for a second patient, and
  later search must find a patient by the number (HIMS-PAT-002).

A plain hash would allow both, but a 12-digit Aadhaar number has only 10^12 values: anyone with
the database could hash every number and read them all back.

## Decision

1. **Encrypted value.** The normalised number is encrypted with the field-encryption keys
   (`common.crypto`, Fernet, `HIMS_FIELD_ENCRYPTION_KEYS`), like two-factor secrets. The column is
   listed for key rotation (`rotate_encryption_keys`, Compliance page). Nothing in HIMS decrypts it
   for display; it is kept for the later UIDAI / ABDM checks.
2. **Masked display.** A masked copy is stored for screens and the console: Aadhaar
   `XXXX XXXX 1234`, SSN `XXX-XX-1234`, ABHA `XX-XXXX-XXXX-1234`, others the last 4 only. A
   previous hospital's MRN is shown in full (it is that hospital's number, needed to ask them).
   The audit log keeps only the masked copy.
3. **Keyed fingerprint.** HMAC-SHA256 of `kind|scope|number` with a random 256-bit key per
   hospital. The key is created on first use, stored **encrypted** in `patient_identifier_keys`
   (so it follows key rotation), and never changes, so fingerprints stay comparable. Without the
   key a database copy does not reveal the numbers.
4. **One person per number** for ABHA number, ABHA address, Aadhaar, passport and SSN: a partial
   unique index on `(organization, kind, fingerprint)` while active. The second registration is
   refused with the first patient's MRN. Voter IDs and driving licences are not refused (typed
   references may repeat in a family); previous MRNs are scoped by the hospital that issued them.
5. **Checks before saving.** Aadhaar: 12 digits, not starting with 0 or 1, Verhoeff check digit;
   SSN: 9 digits, not area 000, 666 or 9xx, group 00 or serial 0000; ABHA number 14 digits; kinds
   not used in the hospital's country are refused.
6. **Wrong numbers are ended, not deleted**, with a reason; the same number can then be recorded on
   the right patient.

## Consequences

* A lost database copy without the field keys reveals no ID number; with the keys it does, as for
  every other encrypted secret: the keys live in the secret manager (spec 13.3).
* The fingerprint key is in the same database (encrypted). Moving it to the secret manager is a
  hosting-stage option; it would need a re-fingerprint of every row.
* LEGAL may still decide that the full Aadhaar number must not be kept (D6 go-live item). Then the
  encrypted column is emptied by a migration and only the masked copy and the fingerprint stay;
  duplicate checks keep working.
