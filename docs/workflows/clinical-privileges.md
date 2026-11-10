# Clinical privileges (HIMS-STAFF-016)

**Spec:** 4.3 "clinical privileges". The spec is clear that a doctor's degree, designation,
specialty and permission to perform a procedure are separate concepts, so a privilege is its own
record, never a line of text on the staff member.

**Approval:** clinical governance said "fine for now" on 2026-11-08, on the basis that the hospital
sets the values itself ([decisions log](../status/decisions-log.md), item 5). HIMS ships **no list
of privileges and no clinical rules**.

## Setting it up

1. Menu → **Job titles & catalogs** → **Clinical privileges** → **Add clinical privilege**. Write your
   hospital's own list, e.g. "Central line insertion". This needs `catalogs.manage`.
2. Open a person on **Staff** → **Privileges** → **Give a privilege** (needs
   `staff.privileges.manage`, held by the organization administrator and the HR / credentialing
   officer):
   - **Where:** wherever the person works, or only in one department they are posted in.
   - **From**, and an optional **Review date**, after which it stops applying.
   - A **note**, such as who approved it. No patient details.

To change a privilege, **End** it with a reason and give it again. Grants are never edited or
deleted, so the record always shows who could perform what on any past day.

## The rules

| Refused when | Why |
|---|---|
| You give one to yourself | Someone else has to decide. The buttons do not appear on your own record |
| The person is not working here | |
| The privilege is switched off | Existing grants stay on record |
| The department is one they are not posted in | |
| They already hold it there | The database refuses this too, for two people acting at the same moment |

- Giving and ending ask you to [confirm it's you](sensitive-actions.md), and need two-factor sign-in.
- Every grant and ending is in the audit log.
- **Termination ends everything the person held**, recorded with the reason "Employment ended".
- Anyone who may see the person on the Staff page can see their privileges.

## What it does not do yet

**Nothing checks a privilege yet, because no clinical action exists until Phase 2.** Today this is a
kept record. The code clinical actions will call is ready and tested:

```python
from apps.staff.privileges import holds_privilege

holds_privilege(staff, "central-line-insertion", department=department)
```

It says no for someone suspended or on long leave, outside the dates, in another department, or once
the grant has ended. Connecting it to clinical actions, and reminders before a review date, is
**HIMS-STAFF-017** in the [Phase 2 backlog](../backlog/phase-2-patients.md).

## Admin console

- **Clinical privileges:** the hospital's list.
- **Staff privileges:** give one under the same rules, and an action to end selected ones. Existing
  grants are read-only.
- On a **Staff member's** page, a read-only **Clinical privileges** section.

## Tables

`clinical_privileges` and `staff_privileges`: see the
[data dictionary](../architecture/data-architecture/data-dictionary.md).
