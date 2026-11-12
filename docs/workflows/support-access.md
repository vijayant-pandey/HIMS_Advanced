# Supplier support access, the "locked box" (HIMS-IAM-021)

Every hospital runs its own copy of HIMS, with its own database and admin console. No hospital
sees another one. You, the software supplier, get into a hospital's system this way.

Decision record: [ADR-035](../decisions/ADR-035-supplier-support-access.md).

## The supplier's account

Each hospital has one **Software supplier support** account. It is created when the hospital is
set up:

```
python manage.py provision_organization ... --support-email support@your-company.example --support-password-env SUPPORT_PW
```

On its own, this account can do nothing in the hospital except ask for access. It needs
two-factor sign-in, like every privileged account.

## Asking (the supplier)

1. Sign in at the hospital's address with the support account.
2. Open **Support access** → **Ask for access**.
3. Choose **Organization administrator** (to fix or change things) or **Auditor / compliance
   officer** (to read the audit log). Choose the hours (default 2, at most 8) and give the reason.
   No patient details.
4. **Ask the hospital**: the hospital's administrators are emailed, and nothing opens yet.
   **Emergency** instead opens the access at once. By your decision the hospital is **not
   emailed** (setting `HIMS_SUPPORT_EMERGENCY_NOTICE`, off by default). It still appears on
   their Support access page and in their audit log.
5. When the work is done, press **End now**. Otherwise the access ends by itself.

## Deciding (the hospital)

**Support access** (menu), or the console under **Access control → Support access**:

* **Approve**: the supplier gets the role from now, for the hours it asked. This needs a recent
  "confirm it's you".
* **Refuse** with a reason: the supplier is emailed the reason.
* **End now** on running access, with a reason.

## What is recorded

| Event | When |
|---|---|
| `support.access.requested` / `.emergency_opened` | The supplier asks, or opens emergency access |
| `support.access.approved` / `.refused` / `.cancelled` / `.ended` | Each decision |
| `access.role.assigned` / `.revoked` | The role given and removed |
| `support.access.used` | **Every request the supplier makes while the access lasts**: method, address (without search words), answer |

Nobody can change or delete these records, not even the hospital or the supplier. The audit log
is append-only and sealed every minute.

## Rules

* One waiting request at a time per account; the supplier never approves its own request.
* The access never counts as one of the hospital's administrators, and it is never lent as cover.
* The hospital can remove the supplier's role altogether (Access page). The supplier then cannot
  ask.

## Settings (per hospital deployment)

| Setting | Default | Meaning |
|---|---|---|
| `HIMS_SUPPORT_ACCESS_HOURS` | 2 | Hours given when the supplier does not choose |
| `HIMS_SUPPORT_ACCESS_MAX_HOURS` | 8 | Most hours one request can ask for |
| `HIMS_SUPPORT_EMERGENCY_NOTICE` | false | Email the hospital's administrators about emergency access |

Later, in the hosting stage, an owner console (HIMS-OPS-025) will list every hospital and open
its Support access page from one place.
