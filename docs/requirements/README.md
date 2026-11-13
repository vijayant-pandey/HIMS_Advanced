# Requirement records (spec 25.3, 25.4; HIMS-DOC-001)

One record for every requirement HIMS has built, in the fourteen fields of spec 25.4, so that each
requirement can be traced to its code, endpoints, tests, pull requests and release risk.

## Requirement IDs

The backlog ticket IDs (`HIMS-<AREA>-NNN`) are the requirement IDs: they already appear in the
code, the tests, the commits and the pull requests, so renaming them would break that trail. How
they map to the identifier families suggested in spec 25.3 is recorded in
[ADR-032](../decisions/ADR-032-requirement-ids-and-contract-docs.md):

| Spec 25.3 family | HIMS IDs |
|---|---|
| `HIMS-FR-<DOMAIN>-NNN` (functional) | `HIMS-ORG`, `HIMS-FAC`, `HIMS-IAM`, `HIMS-STAFF`, `HIMS-AUD`, `HIMS-NOTIF`, `HIMS-UI` |
| `HIMS-NFR-<CATEGORY>-NNN` (non-functional) | `HIMS-PLAT`, `HIMS-DATA`, `HIMS-QA`, `HIMS-DOC` |
| `HIMS-SEC-NNN` (security) | `HIMS-SEC` (same family) |
| `HIMS-OPS-NNN` (operational) | `HIMS-OPS` (same family) |
| `HIMS-INT-<PROVIDER>-NNN` (integration) | none built yet (Stedi, ABDM, SMS gateway come later) |
| `HIMS-CLIN-NNN` (clinical) | none built yet (Phase 2 onwards; CLIN sign-off) |
| `HIMS-ADR-NNN` | `ADR-NNN` in [docs/decisions](../decisions/README.md) |
| Compliance (not in 25.3) | `HIMS-COMP` |

## Where the records are

| File | Requirements |
|---|---|
| [platform-and-operations.md](platform-and-operations.md) | HIMS-PLAT, HIMS-UI, HIMS-OPS, HIMS-DATA, HIMS-QA, HIMS-DOC |
| [organization-and-facilities.md](organization-and-facilities.md) | HIMS-ORG, HIMS-FAC |
| [identity-and-access.md](identity-and-access.md) | HIMS-IAM |
| [staff-and-rota.md](staff-and-rota.md) | HIMS-STAFF |
| [audit-and-security.md](audit-and-security.md) | HIMS-AUD, HIMS-SEC |
| [notifications-and-compliance.md](notifications-and-compliance.md) | HIMS-NOTIF, HIMS-COMP |
| [patients.md](patients.md) | HIMS-PAT (Phase 2, from 2026-11-12) |
| [traceability.md](traceability.md) (generated) | Every Phase 1 requirement: status, record, endpoints, tests, PRs (and, from 2026-11-12, every Phase 2 requirement in its own section) |

## How to read a record

| Field (spec 25.4) | What it holds here |
|---|---|
| ID and title | The ticket ID and what it delivers |
| Business/clinical reason | Why it is needed, and who owns the decision (PO, CLIN, LEGAL) |
| Actors | Roles (by permission) and service identities (Celery jobs, commands) |
| Preconditions | What must exist first (Phase 1 has no patient, encounter or financial state) |
| Main success path | The normal flow and what is saved |
| Alternate/failure paths | Refusals, timeouts, lost scanners, stale versions, cancellations |
| Data effects | Tables and events ([data dictionary](../architecture/data-architecture/data-dictionary.md)) |
| Security classification | Data sensitivity, using the classes in the data dictionary |
| Audit requirement | Audit events written ([audit catalog](../architecture/data-architecture/README.md)) |
| Idempotency/concurrency | Idempotency-Key, `version` checks, row locks, unique rules |
| Integration dependencies | Outside systems and what happens when they fail |
| Acceptance criteria | Observable, testable conditions (spec 25.5) |
| Test evidence | Backend tests, browser tests and the manual test guide part; reviewer: the PO, at PR review |
| Release risk | Clinical, privacy, financial and operational impact, and how to roll back |

Every endpoint of a requirement, with its full contract, is listed in the
[API contracts](../architecture/api-and-integrations/endpoints/README.md); the
[traceability matrix](traceability.md) links both ways.

## Keeping them current

* A new requirement gets its record in the same pull request that marks it Done in the backlog.
  The test `test_every_done_requirement_has_a_complete_record` fails otherwise, and also when a
  field is left empty.
* A new API view must be mapped to its requirement in `backend/common/contracts/catalog.py`
  (test `test_every_api_view_traces_to_a_requirement`).
* After changing the API, the tests, the backlog or the PR history, run
  `python manage.py api_contracts` and commit the regenerated files (CI checks them).

Phase 1 has no patient data: "PHI" below means it is not stored yet. Clinical sign-off (CLIN),
legal review (LEGAL) and the product owner (PO) approved the Phase 1 documents for now on
2026-11-08; later changes are possible.
