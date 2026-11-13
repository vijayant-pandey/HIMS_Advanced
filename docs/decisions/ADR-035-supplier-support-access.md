# ADR-035: Supplier support access, the "locked box"

**Status:** Proposed (2026-11-12) · **Items:** HIMS-IAM-021 · **Spec:** 7.2, 7.4, 13.2, 13.4

## Context

HIMS is sold to many hospitals. Each one is its own deployment with its own database and its own
admin console (ADR-003, ADR-009). No hospital sees another one, and the developer launcher on
the product owner's PC is never deployed.

The product owner (the software supplier) needs to be able to get into any hospital's system: to
support it, and to check that nothing illegal is done with it. The specification asks for this
to be controlled:

* 7.2: the control plane handles "customer support access requests and approval workflow" and
  "should not silently gain access to patient records";
* 7.4: "prevent cross-customer access through support tooling" and "establish a documented
  process for emergency support access and audit it".

A permanent super-user account in every hospital would break both rules. It would also mean
that one stolen password opens every hospital at once.

## Decision

1. **The supplier's support account holds no access.** Each hospital has one account with the
   system role **Software supplier support** (`supplier-support`). It holds a single
   permission, `support.access.request`. It is created at provisioning
   (`provision_organization --support-email ...`) and needs two-factor sign-in.
2. **It asks.** On the **Support access** page it asks for one role, with a reason, for 1 to
   `HIMS_SUPPORT_ACCESS_MAX_HOURS` hours (default `HIMS_SUPPORT_ACCESS_HOURS` = 2). It can ask
   for the hospital administrator role (to fix or change things) or the auditor role (to read
   the audit log), one at a time, so the two stay separate (ADR-013). Asking needs a recent
   "confirm it's you" (HIMS-IAM-007).
3. **The hospital decides.** Holders of `support.access.manage` (the hospital administrator)
   are emailed. They approve the request, which also needs "confirm it's you", or refuse it with
   a reason, in the app or the console. The supplier is emailed the answer.
4. **Emergency.** The supplier can open the access at once instead. **By the product owner's
   decision (2026-11-12) the hospital is not emailed** unless the deployment setting
   `HIMS_SUPPORT_EMERGENCY_NOTICE` is on (default off). The record still shows on the
   hospital's Support access page and in its audit log: nothing is hidden from the hospital's
   own records, only the email is not sent.
5. **The access is an ordinary role assignment, valid until `ends_at`.** Every permission rule
   applies unchanged, and the access ends by itself without a job. Either side can end it early
   with a reason. It never counts as one of the hospital's administrators (the lock-out rule),
   and it is never lent as cover.
6. **Every request the supplier makes while the access lasts is recorded** in the audit log as
   `support.access.used`, with the method, the address without its query string, and the
   answer. Background refreshes are not recorded. The audit log is append-only and sealed
   (ADR-013, HIMS-SEC-010), so neither the supplier nor the hospital can change or delete the
   record. The check costs no database query: `users.support_access_until` is read from the
   signed-in user.

## Consequences

* The supplier can reach every hospital it supports, but only through each hospital's own
  address and records. There is still no central list of hospitals; that is the owner console
  (control plane, HIMS-OPS-025, hosting stage).
* **Legal note (open):** opening emergency access without telling the hospital differs from
  spec 7.2 ("should not silently gain access"). HIPAA business associate agreements and DPDP
  contracts may require notice. LEGAL accepted the compliance pack "for now" on 2026-11-08; this
  setting must be reviewed before real patient data. Switching `HIMS_SUPPORT_EMERGENCY_NOTICE`
  on changes it without code.
* The hospital can remove the supplier's role, like any other role. The supplier then cannot
  even ask. Whether contracts should forbid that is a PO and LEGAL question for later.
* New table `support_access` and a new column `users.support_access_until`; three new message
  wordings; two permissions and one system role. Existing hospitals get them at their next
  `migrate`.

## Update 2026-11-12 (HIMS-PAT-001): no patient records

With patients built, the administrator role holds `patients.search` and `patients.view`. Spec 7.2 says support "should not silently gain access to patient records", and an emergency opening is not told to the hospital (decision 13). So the supplier's account **never holds patient permissions** (`PATIENT_DATA_PERMISSIONS` in `apps/access_control/catalog.py`, held back in `selectors.py`), whatever role it is lent; it still gets every other permission of that role. A hospital-approved exception, if the PO ever wants one: HIMS-IAM-022.
