# Virus scanning of uploads (HIMS-SEC-013)

**Spec:** 4.22 (documents), 13.3 (data protection). **Risk:** R-006 "Malicious file upload".
Storage design: [ADR-020](../decisions/ADR-020-document-storage.md).

## What it does

Every file uploaded to HIMS is checked for viruses **before it is saved**: staff licence and
certificate copies, and the hospital logo. It works the same in the app and the admin console.

| The file | What happens |
|---|---|
| Has no virus | Saved, with how it was checked (`clean`, by `clamd`) |
| Has a virus | **Refused and never written anywhere.** The person sees why. The refusal is in the audit log with the file's fingerprint (never its name, which may name a person). The compliance team is emailed |
| Cannot be checked, because the scanner is down | **Refused** until the scanner is back ("uploads are paused"). A file that could not be checked is never stored as if it had been |

## Which scanner

Chosen with `HIMS_VIRUS_SCANNER` in `backend\.env`:

| Setting | Meaning | Where |
|---|---|---|
| `clamd` | **ClamAV**, the free, widely used virus scanner, reached over the network at `HIMS_CLAMD_HOST`:`HIMS_CLAMD_PORT` (default port 3310) | **Required when hosted.** A deploy check (`hims.W002`) warns otherwise |
| `test-file` (default) | Recognises only the standard anti-virus **test file** (EICAR), so you can see a refusal on your PC. **Not protection:** files are recorded as "not checked" | Developer PC |
| `none` | Nothing is checked | Only if you have a reason |

ClamAV keeps its virus list up to date by itself (its `freshclam` service). At hosting it runs next
to the app; that is part of the hosting stage (HIMS-OPS-020).

## Trying it on your PC

1. Open Notepad and type this test line, made for testing virus scanners and harmless. It is shown in
   two halves so that this guide is not itself taken for a virus: type the first half, then the
   second straight after it, **on one line with no space between them**:
   ```
   X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-
   STANDARD-ANTIVIRUS-TEST-FILE!$H+H*
   ```
   Save it. Windows' own virus protection may remove the file as soon as you save it. That is
   expected: it shows the test file works. If it does, skip to step 3.
2. Rename it `test.pdf`, and upload it as a staff document or the hospital logo.
3. HIMS refuses it: "This file contains a virus or harmful content (EICAR test file)…". The audit log
   shows "Upload refused: a virus was found", and the compliance team's email appears in the launcher
   window.

With Docker Desktop you can also run a real ClamAV:
`docker compose --profile scanning up -d clamav`. Then set `HIMS_VIRUS_SCANNER=clamd` in
`backend\.env` and restart. ClamAV takes a minute or two to load its virus list.

## Files stored before scanning

They are marked **not checked**. To check them once ClamAV is set up:

- **Compliance → Scanning and traces → Check documents not checked yet** (needs `compliance.manage`), or
- admin console → **Staff documents** → choose them → **Check selected documents for viruses now**, or
- `python manage.py scan_documents` (add `--all` to check every document again, e.g. after a new
  virus is announced).

Up to 200 at a time; run again for more. A virus found in a stored file **blocks it**: it can no longer
be opened or downloaded (in the app or the console), it is archived, and the compliance team is
emailed. It is kept only as a record, and a later clean result never unblocks it.

## Where to see it

- **Compliance → Scanning and traces**: the scanner and whether it can be reached; documents checked,
  not checked and blocked; viruses blocked in the last 30 days.
- Admin console → **Security status**: the same.
- **Staff → a person → Licences**: an unchecked file says "not checked for viruses"; a blocked one
  says so and has no link.

## Settings

| Setting | Default | Meaning |
|---|---|---|
| `HIMS_VIRUS_SCANNER` | `test-file` | `clamd`, `test-file` or `none` |
| `HIMS_CLAMD_HOST` | `localhost` | Where ClamAV listens |
| `HIMS_CLAMD_PORT` | `3310` | Its port |
| `HIMS_CLAMD_TIMEOUT` | `30` | Seconds to wait for an answer |
| `HIMS_ACCEPT_UNSCANNED_UPLOADS` | `false` | Throw-away runs only (the CI image check): hosted without a real scanner, on purpose. **A real hospital must never set it** |
