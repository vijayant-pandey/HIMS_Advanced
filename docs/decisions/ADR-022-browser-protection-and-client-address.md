# ADR-022: Browser protection headers and real client addresses

**Status:** Proposed. **Owner:** Engineering lead. **Tickets:** HIMS-SEC-012, HIMS-SEC-014.
**Spec:** 13.1 (login throttling), 13.4 (auditability), 23 (threat model, risk R-005).
How-to: [security-headers.md](../workflows/security-headers.md).

## Decision

**Content security policy**
- Scripts and connections are limited to our own address on the screens and the admin console, with
  no inline scripts and no `eval`. API responses allow nothing at all.
- **`style-src` allows `'unsafe-inline'`.** MUI (through Emotion) and the admin console's templates
  add inline styles. Nonces need a server rendering each page, and the screens are static files.
  Styles cannot run code, so this is the accepted trade-off; scripts stay strict.
- The screens' policy lives in `frontend/security-headers.json`, used by `vite preview`, the browser
  tests and hosting, so what is tested is what is deployed. The backend does not serve the screens.
- Django 5.2 has no built-in CSP (it arrives in 6.0), and one small middleware avoids a new dependency.

**Reports**
- Browsers report blocks to a public, rate-limited, write-only address. Rows are added up per day,
  capped at 500 a day, and hold no query strings or code samples (no patient details can land there).
- `report-uri` is used. It is deprecated in favour of `report-to` but is still what every major
  browser supports, and the policy can carry both later.
- Reports appear on the Compliance page and in the admin console; reviewing one is audited.

**Client address**
- `X-Forwarded-For` is believed only when the connection comes from `HIMS_TRUSTED_PROXIES`, walking
  from the right and stopping at the first address that is not ours. A fixed "number of proxies" was
  rejected: it would believe the header on a request that reached the app directly.
- One function, `common.client_ip.client_ip`, is used by audit, the sign-in register, rate limits and
  the admin lock-out. A test refuses any other code reading those headers.
- Managed environments refuse to start without `HIMS_TRUSTED_PROXIES`, because otherwise all audit
  records would silently show the load balancer's address.

## Consequences
- Fixes a real gap: faking `X-Forwarded-For` got around sign-in and password-reset rate limits.
- Fixes a future gap: behind a load balancer, the admin lock-out would have locked everyone out when
  one person failed to sign in five times.
- A new feature needing another site (a payment page, a CDN) must add it to the policy. The browser
  tests fail until it does, which is intended.
- `HIMS_CSP_REPORT_ONLY` covers the backend-served pages; for the screens the header is renamed at
  hosting. Hosting must send the screens' headers (recorded under HIMS-SEC-012 and the deployment
  work), since nothing protects the screens until it does.
