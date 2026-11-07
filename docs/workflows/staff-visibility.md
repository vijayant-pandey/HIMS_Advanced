# Who sees which staff (HIMS-STAFF-008)

Spec 4.4 ("facility-, department-, patient- and encounter-level restrictions") and 13.2
("least-privilege access and explicit denial by default").

## The rule

Seeing staff follows **where your access applies** (the scope of your role on the Access page):

| Your `staff.view` access applies to | You see on Staff, a person's page and Licence expiry |
|---|---|
| The whole hospital (e.g. HR / credentialing officer, administrator) | Everyone, including people not posted anywhere yet |
| One facility (e.g. facility administrator) | People posted in any department of that facility |
| One department (e.g. head of department) | People posted in that department |

- "Posted" means a **current posting, or one starting later**. When a posting ends, that person
  disappears from the old department's view.
- Someone outside your view is simply **not found** (404), so their existence is not revealed.
- The Staff page tells you when your view is limited: "You see the staff posted in Cardiology
  (Main Hospital)".
- The job title, specialty and qualification-type lists (drop-downs) are readable with any
  `staff.view`, because they hold no personal data.

## Changing staff stays hospital-wide

Adding staff, editing them, postings, qualifications, licences, uploads, invitations and
verification still need a **hospital-wide** grant, as before: a staff record belongs to the whole
hospital, and a new person has no posting yet.

## Documents are separate: `staff.documents.view`

Seeing a person does not mean opening the copies of their licences and certificates.

| Permission | Lets you |
|---|---|
| `staff.view` | See the directory, postings, qualifications and licences (number, authority, expiry, verification) |
| `staff.documents.view` (new) | Also see and open the uploaded files |

- The **HR / credentialing officer** and **organization administrator** roles have both.
- **Head of department** and **facility administrator** have `staff.view` only, each at their own
  scope. Their view of a person says "Copies of licences and certificates are shown only to
  people allowed to open them, such as HR".
- **Nothing was taken away:** when this was introduced, every existing role (including a
  hospital's own roles) that had `staff.view` was given `staff.documents.view` too (migration
  `access_control.0005`).

## Where it is enforced

`backend/apps/staff/selectors.py` (one rule for the list, a person's page, licence expiry and
documents) and the default-deny permission check. The screens only hide buttons; the server
decides. Tests: `apps/staff/tests/test_directory_scope.py`.
