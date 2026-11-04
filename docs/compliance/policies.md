# Policies to adopt (spec 13, 23; HIMS-COMP-004)

DRAFT wording for hospital management to review, adapt and adopt. The right-hand column shows how HIMS enforces
each rule. A policy only counts once it is approved, dated and known to staff.

## Access control policy

| Rule | How HIMS enforces it |
|---|---|
| Everyone has their own account; sharing is forbidden | Unique accounts; sign-in register |
| Access is only what the job needs, and is approved | Default deny; roles and places; no self-granted access |
| Privileged roles use two-factor sign-in | Enforced; production refuses to disable it |
| Access is reviewed every 90 days | Access reviews with reminders |
| Access ends the day someone leaves | Switching off an account ends sessions and cover |
| Temporary cover is time-limited with a reason | Cover arrangements, 30 days at most |
| Administrators do not read audit logs; auditors do not change settings | Separation of duties built into roles |
| Emergency access has a reason and is reviewed | Designed for Phase 2 (D14) |

## Password and device policy

At least 12 characters (enforced), never reused or shared. Sign out on shared computers (30-minute idle sign-out is
enforced). Lock unattended devices. Report lost devices at once. No patient data on personal devices or personal
email.

## Encryption and key management policy

| Item | Rule | Status |
|---|---|---|
| Data in transit | HTTPS only | Forced by production settings |
| Secrets in the database (two-factor keys, ID numbers) | Encrypted (Fernet), rotatable keys | Built |
| Passwords | Strong one-way hash (Argon2) | Built |
| Audit chain key | Kept outside the database; rotated by adding a new key | Built |
| Databases, backups, documents at rest | Encrypted with managed keys | At hosting |
| Keys | In a secret manager, per environment and hospital; never in code, email or chat | At hosting; secret scan in CI today |
| Rotation | Yearly, and at once after suspected exposure or when key holders leave | To schedule |

## Acceptable use and data handling

Use patient data only for care and authorised work. Do not look up people out of curiosity: every opening is
recorded. Do not copy or photograph records, and do not put patient details in email, chat, incident reports or
test systems. Test systems use synthetic data only.

## Change and vendor management

Every change goes through a reviewed pull request with automated checks. New vendors handling personal data need a
contract before use ([vendors.md](vendors.md)). Library versions are locked and scanned
([dependencies.md](../workflows/dependencies.md)).

## Training

At joining and yearly: privacy basics, phishing, how to report incidents, acceptable use. Keep attendance records as
evidence (`HIPAA-SEC-TRAINING`).
