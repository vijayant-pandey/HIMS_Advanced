# ADR-032: Ticket IDs as requirement IDs; endpoint contracts generated from the code

**Status:** Proposed (2026-11-11) · **Items:** HIMS-DOC-001 · **Spec:** 25.3, 25.4, 29.5, 29.9

## Context

Spec 25.3 asks for a stable identifier for every requirement and traceability to code, tests and
pull requests, and suggests families such as `HIMS-FR-<DOMAIN>-NNN` and `HIMS-NFR-<CATEGORY>-NNN`.
Spec 25.4 lists fourteen fields every requirement record holds. Spec 29.5 lists twenty-two fields
every endpoint specification holds, and 29.9 asks that breaking changes be caught in CI.

By the end of Phase 1 the backlog already has 122 tickets named `HIMS-<AREA>-NNN`, and those IDs
appear in the code, tests, commits, PR titles and the tracker. The API has 240 endpoints. A
contract written by hand for each would be out of date after the next pull request.

## Decision

**1. Ticket IDs are the requirement IDs.** No renumbering. Each area maps to a spec 25.3 family
([requirements README](../requirements/README.md)): functional areas (ORG, FAC, IAM, STAFF, AUD,
NOTIF, UI) to `HIMS-FR`, platform areas (PLAT, DATA, QA, DOC) to `HIMS-NFR`, and SEC and OPS stay
as they are. Integration (`HIMS-INT`) and clinical (`HIMS-CLIN`) IDs start when those requirements
exist (Phase 2 onwards).

**2. Requirement records are written by hand, and checked.** One record per built requirement in
`docs/requirements/`, with the fourteen fields. A test fails when a Done ticket has no record, a
field is empty, or a record names an audit event, table, permission or test file that does not
exist.

**3. Endpoint contracts are generated from the code.** `python manage.py api_contracts` writes one
section per endpoint in the 29.5 template, reading:

* the views as requests reach them (access rule, permission, scope, "confirm it's you",
  Idempotency-Key, rate limits): `common/contracts/inventory.py`;
* the code each endpoint calls, followed a few steps deep (audit events, background events, error
  codes, locks, transactions, outside services): `common/contracts/reach.py`;
* `docs/api/openapi.yaml` (request and response schemas, fields and limits);
* the backend tests (which tests call the endpoint);
* `common/contracts/catalog.py` (which requirement each view delivers; purposes where the code has
  no docstring).

A CI test fails when the files are out of date, when an API view has no requirement, or when an
endpoint has no purpose. The same inventory feeds the Access page's **API endpoints** tab and the
console's **API endpoints** page, so all three always agree with the server.

**4. A traceability matrix is generated** (`docs/requirements/traceability.md`): every Phase 1
ticket with its status, record, endpoints, test files and PRs.

## Alternatives

* **Renumber to `HIMS-FR-…`:** matches the spec's suggestion, but breaks the link to 49 PRs and the
  tests that name tickets. Rejected; the mapping table gives the same classification.
* **Hand-written endpoint contracts:** 240 × 22 fields, out of date quickly. Rejected.
* **Contracts only in OpenAPI descriptions:** OpenAPI has no place for audit events, locks or
  requirement links, and would bloat the generated types. Rejected; OpenAPI stays the schema
  source and the contracts read it.

## Consequences

* Adding or changing an endpoint, a test that calls one, a backlog status or a PR row means
  running `python manage.py api_contracts` before pushing (listed in
  [before you push](../workflows/before-you-push.md)).
* The code walk lists what an endpoint *can* record on any path, not what one request does; a test
  pins the events of the most important writes so a broken walk fails CI.
* The API endpoints list needs `access.roles.view`: it shows which permission opens what, which is
  access-control information, not public.

**Owner:** PO. **Review:** when Phase 2 adds clinical requirements (`HIMS-CLIN`) and the first
outside integration (`HIMS-INT`).
