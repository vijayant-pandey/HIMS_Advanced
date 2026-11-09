# Static files (admin console and API docs)

**Ticket:** HIMS-OPS-010 · **Spec:** 6.2 (Django admin and API ecosystem), 13 (browser
protection), 17 (hosted deployment), 33.6 (no unreviewed outside code) · Related:
[security headers](security-headers.md), [dependencies](dependencies.md)

## In one paragraph

The admin console and the API docs need their own style and script files ("static files"). On a
developer PC, `runserver` serves them, as before. In a hosted environment Django does not, so the
**server image now collects them when it is built** and **serves them itself with WhiteNoise**:
compressed, with a fingerprint in each file name (`admin/css/base.96c479cedf7a.css`), so browsers
may keep them for a year and always get the new file after an update. The **API docs' Swagger UI
is now part of HIMS** (the `drf-spectacular-sidecar` package) instead of being downloaded from a
public CDN. The screens (React app) are separate and are not affected.

## What changed

| Before | Now |
|---|---|
| Hosted: admin console and API docs would load without their style and script files | Collected into the image at build time and served by the app (`whitenoise`) |
| API docs loaded Swagger UI from `cdn.jsdelivr.net`, the newest version each time (`@latest`), with an inline start-up script | Swagger UI from the installed, hash-locked `drf-spectacular-sidecar` package; start-up script served as a file |
| API docs protection rules allowed the CDN and inline scripts | Only HIMS itself: `script-src 'self'`, no other site (see [security headers](security-headers.md)) |

## How it works

| Piece | Where |
|---|---|
| Libraries | `backend/requirements/base.in`: `whitenoise==6.12.0`, `drf-spectacular-sidecar==2026.10.1` (hash-locked in `base.txt` and `dev.txt`) |
| Collect at build | `backend/Dockerfile`: `collectstatic` with `config/settings/build.py` (no database and no secrets needed), before the image drops to the `hims` user |
| Serve | `config/settings/production.py`: WhiteNoise right after Django's security middleware; fingerprinted, compressed storage (`HOSTED_STORAGES` in `base.py`) |
| Swagger UI | `SWAGGER_UI_DIST = "SIDECAR"`; `/api/docs/` uses the "split" view (start-up script at `/api/docs/?script=`) |
| Developer PC | Unchanged: `runserver` serves the files from each app; no collecting needed |

If a referenced file is missing, collecting **fails the image build** (strict manifest), so a
broken admin page cannot be shipped.

## After pulling this change (your PC)

Two libraries were added. Install them once, or HIMS will not start:

```
cd C:\Users\vpand\OneDrive\Desktop\HIMS\backend
.venv\Scripts\activate.bat
pip install --require-hashes -r requirements/dev.txt
```

## Tests

- `backend/common/tests/test_static_files.py`: files are collected with fingerprints and
  compressed copies; served by the app with a one-year cache and gzip; admin pages link the
  fingerprinted names; the API docs page loads nothing from another site and has no inline
  script, and its protection rules allow only HIMS itself; the image collects the files before
  dropping to the `hims` user; build settings need no secrets; production uses WhiteNoise and the
  fingerprinted storage.
- Browser test (`04-audit-and-safety`): the API docs open in Chrome under the strict rules with
  nothing blocked, missing or loaded from another site.
- GitHub's **container** check builds the image, which runs the collecting step.
