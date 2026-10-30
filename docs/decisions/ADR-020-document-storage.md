# ADR-020: Storing staff documents (licences, certificates)

**Status:** Proposed — needs Product Owner and Security approval. **Owner:** Platform.
**Ticket:** HIMS-STAFF-005 (documents), HIMS-STAFF-006 (expiry alerts).
**Spec:** 4.3 (credentials), 4.22 (documents), 13.3 (data protection), 13.4 (audit),
14.2–14.3 (scheduled jobs), 17 (S3), 31.4 (configuration).

## Context
HR must keep a copy of each licence and qualification certificate and must know before a
licence expires. These files contain personal data (names, registration numbers, sometimes
photos), so they must not be reachable by anyone who merely guesses a link.

## Decision
1. **No public URL, ever.** Files are stored by Django's storage layer under
   `MEDIA_ROOT/staff-documents/<staff id>/<random name>.<ext>`, and `MEDIA_URL` is not served.
   The only way to a file is `GET /api/v1/staff-documents/{id}/download/`. That endpoint checks
   `staff.view`, records `staff.document.downloaded` in the audit log, and sends
   `Content-Security-Policy: default-src 'none'; sandbox`, `X-Content-Type-Options: nosniff` and
   `Cache-Control: private, no-store`.
2. **Checked on the way in.**
   - Only PDF, JPEG and PNG are accepted, recognised by their first bytes, never by the name.
   - The limit is 10 MB (`HIMS_UPLOAD_MAX_BYTES`), and empty files are refused.
   - The original name is kept only for display, with folder parts removed. The stored name is
     random, so a person's name never appears in a path.
   - A SHA-256 fingerprint is stored and audited.
   - The same checks apply in the admin console.
3. **Never deleted.** A wrong or replaced file is archived with a reason
   (`staff.document.archived`). Each document belongs to exactly one licence or one
   qualification of the same person (a database check enforces this).
4. **One folder per deployment.** By default `MEDIA_ROOT = backend/media/<HIMS_DEPLOYMENT_ID>`,
   so two hospitals on one machine (India and US locally) never share files (ADR-003).
5. **Production storage:** S3-compatible object storage with server-side encryption (KMS),
   block-public-access and versioning (spec 17), configured through Django `STORAGES`.
   - Until that is set up, `manage.py check --deploy` warns (`hims.W001`) in QA, staging and
     production, because local disk on container hosts such as Render is wiped on each deploy.
   - Tracked as **HIMS-OPS-015** (🔒 AWS / hosting decision).
6. **Malware scanning** plugs into `apps/staff/uploads.py` when the scanning service exists
   (HIMS-SEC-013). Until then, accepting only PDF/JPEG/PNG with verified signatures, never
   serving files inline without a sandbox, and keeping them away from the web root limit the risk.
7. **Expiry alerts** run daily (Celery beat `notifications.credential_expiry_alerts`; also
   `manage.py send_credential_expiry_alerts` where no scheduler runs).
   - **Stages** are 60, 30 and 7 days before expiry (`HIMS_CREDENTIAL_ALERT_DAYS`) and once
     after expiry.
   - **Each stage is sent once** per licence and expiry date. The unique key is
     (credential, expires_at, days_before), so the job is safe to repeat, catches up after a
     missed day, and starts again when a licence is renewed with a new date.
   - **Who is emailed:** HR (active holders of `staff.credentials.verify` or `staff.manage`)
     gets one summary, and the person gets their own reminder.
   - **Who is skipped:** staff who are suspended or terminated, and rejected licences.
   - Every alert is audited (`staff.credential.expiry_alert_sent`).

## Consequences
- Documents work locally today. Hosted environments need the S3 step before uploads can be
  relied on, and the deploy check makes sure this cannot be forgotten.
- Backups must include the document storage as well as the database (HIMS-OPS-009).
