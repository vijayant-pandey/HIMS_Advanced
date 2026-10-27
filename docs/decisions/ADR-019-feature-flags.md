# ADR-019: Feature settings (feature flags) per hospital, country and facility

**Status:** Proposed — needs Product Owner approval. **Owner:** Platform. **Ticket:** HIMS-ORG-004.
**Spec:** 4.1 ("configuration and feature flags by organization, country and facility"), 7.2
("per-customer configuration and feature flags"), 31.4 ("documented schema for settings such as
feature flags"), 13.4 (audit), 26.4 (permissions), 20 (roadmap and controlled rollout).

## Context
Every hospital is its own deployment and database (ADR-003), and each runs in India or the US.
Hospitals must be able to switch parts of HIMS on or off: for the whole hospital or one branch
at a time during a controlled rollout (spec 20, Phase 6), and some features only exist in one
country (ABDM in India, Stedi in the US). These are product settings changed by hospital
administrators, not environment variables changed by engineers.

## Decision
1. **The feature list is code.** `backend/apps/features/catalog.py` declares every feature: key,
   name, description, category, whether it is set for the whole hospital or per facility, its
   default (optionally per country), the countries where it is offered, and whether it is
   available yet (with the planned phase). The table below is the documented schema (spec 31.4).
2. **A hospital's choices are data.** Table `feature_flags`: one row per feature for the whole
   hospital (created automatically, set to "use the default"), plus optional rows for single
   facilities. `enabled` is on, off, or empty (use the default). The table has a unique key
   `(key, facility)` with NULLS NOT DISTINCT.
3. **How a value is decided** (first match wins):
   1. Not available yet, or not offered in the hospital's country → **off**.
   2. The facility's own setting (only for per-facility features).
   3. The hospital-wide setting.
   4. The default for the hospital's country, else the general default.
4. **The server enforces every feature.** The app hides buttons and links as a convenience only.
   A request for a closed feature gets `409 FEATURE_DISABLED` with a plain-language message.
5. **Changes are controlled:**
   - `features.manage` is needed, and two-factor sign-in is required (it can change security
     behaviour).
   - A reason is required.
   - Optimistic concurrency uses `version` (an old copy gets 409).
   - Each change is audited (`feature.flag.changed`) with the before/after setting and the
     effective value.
   - Rows are never deleted: "back to default" keeps the row.
   - A facility administrator can only change their own facility's per-facility settings.
6. **Fresh values.** Settings are read in one small query per request and remembered for that
   request only. There is no cross-request cache, so a change takes effect on the next request
   in every server process.
7. **Planned modules are listed but locked.** Hospitals can see what is coming (Phase 2–6). The
   database refuses to switch them on (`Not available yet`). When a module is built, its entry
   gets `available=True` and its code checks the flag.
8. **Admin console:** "Feature flags" lists every feature with its setting, default, current
   value and availability. Facility rows can be added there. Changes are audited, as for every
   console change (ADR-016).

## Catalog at the time of writing

| Key | Feature | Scope | Default | Offered | Status |
|---|---|---|---|---|---|
| `auth.self_service_password_reset` | Forgot-password emails | Hospital | On | All | Live: when off, `POST /auth/password-reset/request/` → 409 for every address (no account enumeration); the sign-in page hides the link; admin-sent reset links still work |
| `auth.two_factor_for_everyone` | Two-factor sign-in for all staff | Hospital | Off | All | Live: when on, every user must use an authenticator app (`mfa.is_required`); same effect as the server setting `HIMS_MFA_REQUIRED_FOR_ALL` |
| `locations.module` | Locations and beds | Per facility | On | All | Live: when off for a facility, its locations are left out of lists, and its tree, items, creates and bed changes → 409; the admin console still shows them |
| `patients.registration` | Patient registration | Per facility | Off | All | Phase 2 |
| `outpatient.appointments` | Appointments and outpatient visits | Per facility | Off | All | Phase 2 |
| `inpatient.admissions` | Admissions, transfers and discharge | Per facility | Off | All | Phase 3 |
| `nursing.care` | Nursing care | Per facility | Off | All | Phase 3 |
| `pharmacy.module` | Pharmacy and medication | Per facility | Off | All | Phase 4 |
| `laboratory.module` | Laboratory | Per facility | Off | All | Phase 4 |
| `radiology.module` | Imaging / radiology | Per facility | Off | All | Phase 4 |
| `billing.module` | Billing and payments | Per facility | Off | All | Phase 5 |
| `insurance.us_payers` | US insurance (Stedi) | Per facility | Off | US | Phase 5 |
| `insurance.india_tpa` | Indian insurers, TPAs and government schemes | Per facility | Off | IN | Phase 5 |
| `portal.patient` | Patient portal | Per facility | Off | All | Phase 6 |
| `integrations.abdm` | ABDM (Ayushman Bharat Digital Mission) | Per facility | Off | IN | Phase 6 |

## API
- `GET /api/v1/features/` (`?facility=`) — `features.view`.
- `POST /api/v1/features/{key}/change/` `{facility?, setting: default|on|off, reason, version}` —
  `features.manage`, Idempotency-Key.
- `GET /api/v1/features/effective/` — current values. Before sign-in it returns only public
  features (to show or hide "Forgot password?").

## Consequences
- Adding a feature means adding one catalog entry and checking it in code. The next `migrate`
  gives every hospital a "use the default" row automatically.
- Settings are per deployment. A future control plane (spec 7.2) can drive the same API or
  table for many hospitals.
- Kill switches for incidents are possible without a deployment, but every use leaves an audit
  trail and a reason.
- Not chosen: environment variables for product settings (needs an engineer and a restart, and
  isn't audited), and a third-party flag service (adds an external dependency and sends
  configuration outside the hospital's deployment).
