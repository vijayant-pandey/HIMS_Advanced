"""The Phase 1 security review of the threat model (spec 13, 23; HIMS-SEC-011).

One source for the review's results: ``docs/compliance/security-review.md`` is generated from
here (``compliance_docs``), the Compliance page's Security review tab and the console's Security
status page read it, and a test checks that every piece of evidence named here is a real test.
"""

from datetime import date

REVIEWED_ON = date(2026, 11, 11)
REVIEWER = (
    "Internal engineering review against the threat model, spec 13 and the spec 23 security "
    "checklist. Not a substitute for the independent review and penetration test before go-live "
    "(HIMS-SEC-021)."
)
SCOPE = (
    "Everything built in Phase 1 (the application: every API endpoint, the admin console, "
    "background jobs, uploads, backups), on a developer PC with synthetic data. Hosting "
    "(Oracle Cloud) is reviewed again when it is set up."
)
METHOD = (
    "Each threat-model row checked against the code and its tests; the code searched for the "
    "usual weak spots (raw SQL, unescaped HTML, missing CSRF, open redirects, unsafe file "
    "handling, secrets, debug settings); every endpoint's access rule read from the code "
    "(HIMS-DOC-001); the ten spec 13.5 security tests mapped to automated tests; dependency "
    "audits (pip-audit, npm audit)."
)

FIXED = "fixed"
ACCEPTED = "accepted"
SEVERITIES = ("high", "medium", "low", "info")
FINDING_STATUSES = (FIXED, ACCEPTED)

# (code, severity, area, finding, fix, status, evidence tests)
FINDINGS: list[tuple[str, str, str, str, str, str, tuple[str, ...]]] = [
    (
        "F-01",
        "medium",
        "Sign-in sessions (13.1)",
        "Screens that refresh themselves (Bed board, Background jobs, Rota, the confirm-it's-you "
        "status) renewed the 30-minute idle timeout, so a screen left open on a ward PC stayed "
        "signed in for ever; there was no upper limit on a session.",
        "Background refreshes are marked by the app and no longer count as use; the server ends "
        "a session after 30 minutes without use and after 12 hours in any case "
        "(HIMS_SESSION_IDLE_SECONDS, HIMS_SESSION_MAX_SECONDS); ended sessions are audited.",
        FIXED,
        (
            "apps/compliance/tests/test_security_review.py::"
            "test_background_refreshes_do_not_keep_a_session_awake",
            "apps/compliance/tests/test_security_review.py::"
            "test_nobody_stays_signed_in_past_the_time_limit",
        ),
    ),
    (
        "F-02",
        "medium",
        "Password guessing (13.1)",
        "Wrong passwords were limited per client address only, so one person's password could "
        "be guessed from many addresses without slowing down.",
        "Wrong passwords are also counted per email: after 10 within 15 minutes, sign-in with "
        "that email pauses for 15 minutes in the app and the console, with the same answer for "
        "emails that have no account.",
        FIXED,
        (
            "apps/compliance/tests/test_security_review.py::"
            "test_wrong_passwords_pause_sign_in_for_that_email_from_any_address",
            "apps/compliance/tests/test_security_review.py::"
            "test_console_sign_in_shares_the_per_account_pause",
        ),
    ),
    (
        "F-03",
        "low",
        "Encryption keys (13.3)",
        "A new encryption key could be added, but nothing encrypted the stored secrets again, "
        "so an old key could never be retired.",
        "`rotate_encryption_keys` encrypts every stored secret again with the newest key "
        "(audited); the Compliance page and the console show how many values still need an older "
        "key.",
        FIXED,
        (
            "apps/compliance/tests/test_security_review.py::"
            "test_old_encryption_keys_can_be_retired_after_rotation",
        ),
    ),
    (
        "F-04",
        "low",
        "Audit log flooding (13.4)",
        'Any signed-in account could call the "no access yet" report up to 1,200 times a '
        "minute, each writing an audit event that can never be deleted.",
        "One event per person per 10 minutes (the same reference is returned); someone who "
        "already has access records nothing.",
        FIXED,
        (
            "apps/compliance/tests/test_security_review.py::"
            "test_no_access_reports_cannot_flood_the_audit_log",
        ),
    ),
    (
        "F-05",
        "low",
        "Background jobs (13.5)",
        "A background event was processed without checking which hospital it belongs to; queues "
        "are separate per deployment, but a shared broker or a copied database could run another "
        "hospital's work here.",
        "Messages carry the deployment and are refused when it differs; an event whose own "
        "hospital is not this deployment is marked failed with the reason and never runs.",
        FIXED,
        (
            "apps/compliance/tests/test_security_review.py::"
            "test_a_background_event_for_another_hospital_never_runs",
        ),
    ),
    (
        "F-06",
        "info",
        "Dependencies",
        "npm audit lists 10 moderate advisories (minimatch, a pattern-matching library) in the "
        "lint tools only; nothing in the app that browsers download. The fix would move ESLint "
        "back a major version.",
        "Accepted: lint tools never reach a hospital. CI blocks high advisories in the shipped "
        "packages; Dependabot proposes the fixed version when ESLint releases one.",
        ACCEPTED,
        (),
    ),
    (
        "F-07",
        "info",
        "Threat model",
        "The threat model still listed built controls (content security policy, passkeys, the "
        "secret-in-logs test, restore drills) as gaps.",
        "Threat model brought up to date and marked reviewed; the remaining gaps point at their "
        "tickets.",
        FIXED,
        (),
    ),
]

# Checked and found sound (no finding): (area, what was checked).
CHECKED: list[tuple[str, str]] = [
    (
        "Forged requests",
        "Every signed-in write goes through CSRF checks; the nine sign-in, invitation and reset "
        "endpoints that run before sign-in enforce CSRF themselves.",
    ),
    (
        "Injection",
        "No SQL built from user input: the few raw statements use fixed names or quoted "
        "identifiers; no `eval`, `pickle`, unsafe YAML or shell commands.",
    ),
    (
        "Cross-site scripting",
        "React escapes all text and nothing uses raw HTML; the two server-side HTML spots escape "
        "first; content security policy on screens, console and API.",
    ),
    (
        "Access control",
        "Default deny on every endpoint, read from the code and pinned by tests (HIMS-DOC-001); "
        "only 12 endpoints work without sign-in, all rate limited; rows outside a facility grant "
        "answer 404.",
    ),
    (
        "Files",
        "Uploads are virus-checked, typed by content and size-limited; downloads need a "
        "permission and the person's scope, are audited, and are sent as attachments with a "
        "sandbox policy and no caching.",
    ),
    (
        "Secrets",
        "Nothing secret in the repository (secret scan in CI), logs, traces or audit metadata "
        "(tests); hosted settings refuse to start without their keys; API docs and the console "
        "are off unless switched on, the console only from allowed addresses.",
    ),
    (
        "Transport and browser",
        "HTTPS redirect, HSTS, secure and HTTP-only cookies, SameSite, X-Frame-Options DENY, "
        "nosniff, strict referrer policy in hosted settings; checked by `check --deploy` in CI.",
    ),
    (
        "Sign-in",
        "Argon2 password hashing, 12-character minimum and common-password checks, the same "
        "answer for unknown and wrong accounts, session key renewed at sign-in, two-factor for "
        "privileged roles (enforced in production), confirm-it's-you for 23 sensitive actions.",
    ),
    (
        "Dependencies",
        "pip-audit: no known vulnerabilities; npm audit of shipped packages: none; libraries "
        "hash-locked, GitHub Actions pinned to commits.",
    ),
]

TESTED = "tested"
PHASE1_FORM = "phase1_form"
WAITS = "waits"
CASE_STATUS = {
    TESTED: "Tested",
    PHASE1_FORM: "Tested for Phase 1 records; patients follow",
    WAITS: "Waits for the feature",
}
CASE_STATUSES = tuple(CASE_STATUS)

# Spec 13.5: (case, status, how it is met, evidence tests)
SPEC_CASES: list[tuple[str, str, str, tuple[str, ...]]] = [
    (
        "A user from Hospital A requests a patient ID belonging to Hospital B.",
        PHASE1_FORM,
        "Each hospital has its own deployment and database (ADR-003) with its own cookies; an ID "
        "or a session from elsewhere is simply not there. Patients arrive in Phase 2 on the same "
        "basis.",
        (
            "apps/compliance/tests/test_security_review.py::"
            "test_a_record_or_session_from_another_hospital_is_not_found",
            "common/tests/test_environment.py::test_deployment_identity_required",
        ),
    ),
    (
        "A doctor accesses a patient outside the authorized scope.",
        PHASE1_FORM,
        "Facility and department scope on every list and record (staff, beds, rota); patient and "
        "encounter scope with Phase 2 (HIMS-IAM-010).",
        (
            "apps/staff/tests/test_directory_scope.py::"
            "test_someone_elsewhere_is_not_found_and_changes_stay_hospital_wide",
            "apps/beds/tests/test_bed_board.py::test_a_department_grant_sees_only_its_wards",
        ),
    ),
    (
        "A nurse attempts to modify a signed doctor's note.",
        WAITS,
        "Clinical notes are Phase 2 (slice 2C); the test is written with them.",
        (),
    ),
    (
        "A pharmacist attempts to dispense more stock than is available.",
        WAITS,
        "Pharmacy is Phase 4; the test is written with it.",
        (),
    ),
    (
        "A terminated employee reuses an old session.",
        TESTED,
        "Ending employment ends every session on every device; the next request is refused.",
        (
            "apps/identity/tests/test_sessions.py::"
            "test_terminating_staff_signs_them_out_on_every_device",
        ),
    ),
    (
        "A user downloads a document by guessing another document's URL.",
        TESTED,
        "Document addresses are random IDs and every download checks the permission and the "
        "person's scope; a guessed address answers 404.",
        (
            "apps/compliance/tests/test_security_review.py::"
            "test_a_guessed_document_address_finds_nothing",
        ),
    ),
    (
        "A Celery job runs with missing or stale customer context.",
        TESTED,
        "Queues per deployment; messages carry the deployment; events of another hospital are "
        "refused and marked failed (finding F-05).",
        (
            "apps/compliance/tests/test_security_review.py::"
            "test_a_background_event_for_another_hospital_never_runs",
        ),
    ),
    (
        "A report export includes patients outside the authorized facility.",
        PHASE1_FORM,
        "Phase 1 lists follow the facility and department scope; the only exports (audit log, "
        "access reviews) are hospital-wide by design and need confirm-it's-you. Patient reports "
        "come with Phase 2 (HIMS-RPT).",
        (
            "apps/staff/tests/test_directory_scope.py::test_licence_expiry_list_follows_the_same_scope",
        ),
    ),
    (
        "An integration logs a secret or sensitive patient data during an exception.",
        TESTED,
        "The real flows run and the logs, audit log, stored errors and responses are searched "
        "for every secret.",
        (
            "common/tests/test_secrets_never_logged.py::"
            "test_no_secret_reaches_a_log_the_audit_log_or_a_stored_error",
        ),
    ),
    (
        "A database restore recovers records but fails to restore required audit relationships.",
        TESTED,
        "The restore drill checks the audit chain and its links; a copy that lost them fails.",
        (
            "apps/recovery/tests/test_restore_drill.py::test_restore_that_loses_audit_relationships_is_caught",
        ),
    ),
]

# Before real patient data: what this review cannot replace.
BEFORE_GO_LIVE: list[tuple[str, str]] = [
    ("HIMS-SEC-021", "Independent security review and penetration test of the hosted system"),
    ("HIMS-OPS-020", "Hosting threat review on Oracle Cloud: network, firewall, secrets, backups"),
    ("HIMS-OPS-021", "Load test with many people at once"),
    ("HIMS-SEC-016", "Copy of the audit chain head to write-once storage"),
    ("HIMS-SEC-018", "The screens' protection headers sent by the hosting"),
]


def summary() -> dict:
    return {
        "reviewed_on": REVIEWED_ON,
        "reviewer": REVIEWER,
        "scope": SCOPE,
        "method": METHOD,
        "findings": [
            {
                "code": code,
                "severity": severity,
                "area": area,
                "finding": finding,
                "fix": fix,
                "status": status,
            }
            for code, severity, area, finding, fix, status, _ in FINDINGS
        ],
        "checked": [{"area": area, "result": result} for area, result in CHECKED],
        "cases": [
            {
                "number": number,
                "case": case,
                "status": status,
                "status_label": CASE_STATUS[status],
                "how": how,
                "tests": len(tests),
            }
            for number, (case, status, how, tests) in enumerate(SPEC_CASES, start=1)
        ],
        "before_go_live": [{"ticket": ticket, "what": what} for ticket, what in BEFORE_GO_LIVE],
    }
