# Browser protection headers and real client addresses (spec 13; HIMS-SEC-012, HIMS-SEC-014)

Decision record: [ADR-022](../decisions/ADR-022-browser-protection-and-client-address.md).

## What the headers do

Security headers are instructions a server gives the browser about what a page may do. If an
attacker manages to slip code into a page, the browser refuses to run it or to send data elsewhere.

| Header | What it stops |
|---|---|
| `Content-Security-Policy` (CSP) | Scripts from other sites and inline scripts; data being sent to other sites; the page being framed by another site |
| `Strict-Transport-Security` | Any connection without HTTPS (managed environments only) |
| `X-Content-Type-Options` | A file being treated as a different type, such as an upload run as a script |
| `X-Frame-Options` | Older browsers framing the page (click-jacking) |
| `Referrer-Policy` | Page addresses leaking to other sites |
| `Permissions-Policy` | Camera, microphone, location, payment and USB use |
| `Cross-Origin-Opener-Policy`, `Cross-Origin-Resource-Policy` | Other sites reaching our windows or embedding our responses |

## Where each policy lives

| What is served | Policy | Set in |
|---|---|---|
| API and file downloads | Nothing may load or run | `backend/common/security_headers.py` |
| Admin console | Our own scripts only | `backend/common/security_headers.py` |
| API documentation page (off in managed environments) | Allows the Swagger CDN | `backend/common/security_headers.py` |
| The screens (React app) | Our own scripts and connections only | `frontend/security-headers.json` |

The screens are static files, so **the hosting service must send these headers**. When the HIMS server itself serves the screens (the hosted image, HIMS-OPS-022: [one-server hosting](one-server-hosting.md)), it sends exactly these headers (`common/screens.py`, kept identical to the JSON file by a test), so nothing has to be copied by hand. Otherwise:

- `vite preview` and the browser tests use `frontend/security-headers.json` exactly, so the tests
  prove the policy works on every screen.
- `npm run dev` adds what its live reload needs (inline start-up code, a WebSocket) and sends no
  reports. Production never does this.
- **At deployment:** copy every entry of `frontend/security-headers.json` into the host's response
  headers (AWS: a CloudFront response headers policy). `/api` must stay on the same address as the
  screens; if it ever moves, add its address to `connect-src`.
- If admin static files move to another address (HIMS-OPS-010), add it to `CONSOLE_POLICY`.
  **2026-11-08 (HIMS-OPS-010):** they stay on the same address: the app serves them itself
  ([static files](static-files.md)). The **API docs** no longer load Swagger UI from
  `cdn.jsdelivr.net` and run no inline script, so their rules are now only
  `script-src 'self'`, with no other site allowed.

## What was blocked

Browsers report each block to `POST /api/v1/security/browser-reports/`. The address is public
because browsers send reports without signing in, so:

- it is rate limited (`HIMS_THROTTLE_BROWSER_REPORT`, default 30 a minute per address), takes at
  most 16 KB, and stores at most 500 rows a day;
- it keeps only the rule, the blocked site and the page address with ids removed, never query
  strings or code samples, which could contain patient details;
- the content can be made up, so treat it as a hint and check before acting.

**Where to see them:** **Compliance → Browser protection** (`compliance.view`; marking reviewed
needs `compliance.manage`, and is audited), or the admin console under Compliance.

**How to read them:**

| You see | Likely meaning | Do |
|---|---|---|
| One or two entries, a site you don't know, one person | A browser add-on | Mark reviewed |
| The same site from many pages or people | Possible injected code | Report a security incident |
| Our own feature broke just after a release | The policy is too strict for a new feature | Fix the policy in the same way as any bug |

## Backing out a problem

Set `HIMS_CSP_REPORT_ONLY=true` and restart: the admin console and API then report without blocking,
and the Browser protection tab shows a warning. For the screens, rename the host's header to
`Content-Security-Policy-Report-Only`. Fix the cause and switch back.

## Real client addresses

Behind a load balancer every request seems to come from the balancer, so audit records and rate
limits would see one address. The `X-Forwarded-For` header carries the real one, but **anyone can
send that header**, so it can only be believed when the request came from our own proxy.

`HIMS_TRUSTED_PROXIES` lists our proxies' addresses or networks, comma separated:

| Where | Value |
|---|---|
| Local, no proxy | Leave unset: the header is never believed |
| AWS | The load balancer subnets, such as `10.0.0.0/16` |
| Any managed environment | Required: the service refuses to start without it |

**How to check it:** on **Compliance → Browser protection**, "HIMS sees your address as" must show
your own public address, not the load balancer's. A wrong network there means every audit record
shows the wrong address, so check it on the first deployment of each environment.

`common/client_ip.py` is the only code allowed to read these headers, and a test enforces that.

## Before HIMS-SEC-014

The default rate limiter identified people by the whole `X-Forwarded-For` header. A person changing
that header on each try was never limited, including on sign-in and password reset. Audit records
and the sign-in register were not affected, as they used the connection's address.
