"""Hand-maintained facts for the data dictionary (spec 28; HIMS-DATA-001).

Everything that cannot be read from the models lives here: which domain owns each app, the
lifecycle/correction rule of every table, and how columns are classified. A test fails when a
table has no lifecycle entry, so every new table is documented when it is added.
"""

# --- Domains (spec 28.3 "domain ownership and sources of truth") ---------------------------
# Order is the order of the generated documents.
DOMAINS: dict[str, dict] = {
    "organizations": {
        "name": "Hospital (organization)",
        "owner": "Organization/facility domain",
        "docs": ["../../decisions/ADR-009-single-organization-per-deployment.md"],
    },
    "facilities": {
        "name": "Facilities, departments and locations",
        "owner": "Organization/facility domain",
        "docs": ["facilities-and-departments.md", "locations-and-beds.md"],
    },
    "beds": {
        "name": "Beds",
        "owner": "Bed domain (occupancy will come from bed assignments, Phase 3)",
        "docs": ["locations-and-beds.md"],
    },
    "numbering": {
        "name": "Numbering (MRN, visit, invoice, claim numbers)",
        "owner": "Organization/facility domain",
        "docs": ["numbering-schemes.md"],
    },
    "features": {
        "name": "Feature settings",
        "owner": "Organization/facility domain",
        "docs": ["../../decisions/ADR-019-feature-flags.md"],
    },
    "identity": {
        "name": "Identity: accounts, sign-in, two-factor",
        "owner": "Identity and access domain",
        "docs": [
            "../../decisions/ADR-011-browser-session-authentication.md",
            "../../decisions/ADR-018-two-factor-sign-in.md",
        ],
    },
    "access_control": {
        "name": "Access control: roles, access, reviews, cover",
        "owner": "Identity and access domain",
        "docs": [
            "access-reviews.md",
            "cover-arrangements.md",
            "../../decisions/ADR-015-scoped-rbac.md",
        ],
    },
    "staff": {
        "name": "Staff and credentials",
        "owner": "Staff/credential domain (verification and expiry are separate from sign-in)",
        "docs": ["../../decisions/ADR-020-document-storage.md"],
    },
    "audit": {
        "name": "Audit log and tamper evidence",
        "owner": "Audit domain (separate security boundary)",
        "docs": ["audit-integrity.md", "../../decisions/ADR-013-audit-log-storage.md"],
    },
    "outbox": {
        "name": "Platform: transactional outbox",
        "owner": "Platform",
        "docs": [
            "../../decisions/ADR-005-transactional-outbox.md",
            "../../decisions/ADR-012-outbox-dispatcher.md",
        ],
    },
    "idempotency": {
        "name": "Platform: idempotency",
        "owner": "Platform",
        "docs": [],
    },
}

# --- Lifecycle, retention and correction per table (spec 28.1 #5, 28.2) --------------------
LIFECYCLE: dict[str, str] = {
    "organizations": "One row per deployment. Never deleted; details edited with a version check.",
    "facilities": "Never deleted. Switched to inactive only after its departments and wards "
    '("close in order").',
    "departments": "Never deleted. Switched to inactive only after postings and wards end.",
    "department_services": "Never deleted; switched off (`is_active`).",
    "department_hours": "Weekly timetable rows, replaced as a set when the hours change (the "
    "only deleted rows in HIMS; every change is audited with before/after).",
    "buildings": "Never deleted; switched off (`is_active`).",
    "floors": "Never deleted; switched off (`is_active`).",
    "wards": "Never deleted; switched off (`is_active`).",
    "rooms": "Never deleted; switched off (`is_active`).",
    "beds": "Never deleted; switched off. Status changes with reason; history in the audit log.",
    "numbering_schemes": "Never deleted; switched off. Edits versioned and audited.",
    "numbering_counters": "One per scheme and period; the value only increases.",
    "issued_numbers": "Append-only register; a number is never reused.",
    "feature_flags": "One per feature and scope; every change audited with a reason.",
    "users": "Never deleted; switched off (`is_active`), which ends every session.",
    "user_invitations": "Single use, valid 72 hours (`HIMS_INVITATION_TTL_HOURS`); kept as "
    "history (accepted, revoked or expired).",
    "user_password_resets": "Single use, valid 60 minutes (`HIMS_PASSWORD_RESET_TTL_MINUTES`); "
    "kept as history.",
    "user_sessions": "Register of sign-ins; closed (`ended_at`, reason) on sign-out, expiry or "
    "switch-off; kept as history.",
    "user_mfa_devices": "One per person; deleted when two-factor is switched off or reset "
    "(audited).",
    "user_mfa_recovery_codes": "Single use; replaced as a set when regenerated or reset.",
    "permissions": "Synced from the code catalog on migrate; removed codes are deactivated, "
    "never deleted.",
    "roles": "Never deleted. System roles follow the code catalog; custom roles are versioned.",
    "role_permissions": "Changed with a custom-role edit (audited); system roles synced.",
    "role_assignments": "Never deleted; revoked (`revoked_at`, reason) or expire (`valid_until`).",
    "access_reviews": "Never deleted; open → completed or cancelled, then locked.",
    "access_review_items": "Snapshot taken when the review starts; each decided once; never "
    "deleted.",
    "access_review_reminders": "One per kind and due date (sent once); kept as history.",
    "access_delegations": "Never deleted; ends by date, or early with a reason.",
    "specialties": "Catalog: never deleted; switched off (`is_active`).",
    "qualification_types": "Catalog: never deleted; switched off (`is_active`).",
    "designations": "Catalog: never deleted; switched off (`is_active`).",
    "staff_members": "Never deleted; leaving is recorded (`employment_status`, `left_on`).",
    "staff_department_assignments": "Never deleted; postings end (`valid_until`).",
    "staff_qualifications": "Never deleted; verification recorded (who, when).",
    "staff_credentials": "Never deleted; verification recorded; renewal is a new credential.",
    "staff_documents": "Never deleted; archived with a reason; the file is kept (ADR-020).",
    "staff_credential_expiry_alerts": "One per credential, stage and expiry date (sent once).",
    "audit_events": "Append-only: a database trigger refuses changes and deletes. Retention and "
    "legal hold: decision pending (🔒 LEGAL).",
    "audit_chain_entries": "Append-only (database trigger); one link per sealed audit event.",
    "audit_integrity_checks": "Append-only (database trigger); one row per check.",
    "outbox_events": "Kept after publishing; archival job pending (HIMS-PLAT-014).",
    "outbox_processed_events": "Kept for duplicate detection; archival with HIMS-PLAT-014.",
    "idempotency_records": "Purged hourly once expired (48 hours, "
    "`HIMS_IDEMPOTENCY_RETENTION_HOURS`).",
}

# --- Sensitivity classification (spec 13.3, 28.1 #3 and #7) --------------------------------
SECRET = "Secret"  # noqa: S105 - a sensitivity level name, not a password
RESTRICTED = "Restricted"
INTERNAL = "Internal"
LEVELS = {
    SECRET: "Credentials and keys. Stored only hashed or encrypted; never shown, exported or "
    "logged.",
    RESTRICTED: "Personal data or security records: names, contact details, registration "
    "numbers, documents, IP addresses, audit content. Need-to-know access by permission; kept "
    "out of logs, traces and URLs.",
    INTERNAL: "Hospital configuration and system data. Visible to staff with the right permission.",
}
# Patient data (PHI) will add a "Clinical" level with stricter rules (Phase 2, spec 26 P0).

# Exact columns, checked first: "table.column" -> (level, category).
COLUMN_OVERRIDES: dict[str, tuple[str, str]] = {
    "users.password": (SECRET, "Credential (hashed)"),
    "user_mfa_devices.secret_encrypted": (SECRET, "Credential (encrypted)"),
    "user_mfa_recovery_codes.code_hash": (SECRET, "Credential (hashed)"),
    "user_sessions.session_key": (SECRET, "Credential (session identifier)"),
    "idempotency_records.response_body": (RESTRICTED, "Stored response (may hold personal data)"),
    "idempotency_records.request_fingerprint": (INTERNAL, "Checksum"),
    "outbox_events.payload": (RESTRICTED, "Event content (may hold personal data)"),
    "outbox_events.last_error": (INTERNAL, "System diagnostics"),
    "audit_events.changes": (RESTRICTED, "Audit content (before/after values)"),
    "audit_events.metadata": (RESTRICTED, "Audit content"),
    "audit_events.reason": (RESTRICTED, "Audit content"),
    "audit_integrity_checks.problems": (RESTRICTED, "Audit content"),
    "facilities.phone": (INTERNAL, "Facility contact"),
    "facilities.address_line1": (INTERNAL, "Facility address"),
    "facilities.address_line2": (INTERNAL, "Facility address"),
    "facilities.postal_code": (INTERNAL, "Facility address"),
    "staff_documents.sha256": (INTERNAL, "Checksum"),
    "staff_documents.original_name": (RESTRICTED, "Document (file name)"),
    "access_review_items.account_active": (RESTRICTED, "Access evidence"),
    "access_review_items.last_signed_in_at": (RESTRICTED, "Access evidence"),
}
# Column names, checked next: name -> (level, category).
NAME_RULES: dict[str, tuple[str, str]] = {
    "email": (RESTRICTED, "Contact"),
    "person_email": (RESTRICTED, "Contact"),
    "display_name": (RESTRICTED, "Personal identifier"),
    "person_name": (RESTRICTED, "Personal identifier"),
    "given_name": (RESTRICTED, "Personal identifier"),
    "family_name": (RESTRICTED, "Personal identifier"),
    "employee_number": (RESTRICTED, "Personal identifier"),
    "registration_number": (RESTRICTED, "Professional registration"),
    "ip_address": (RESTRICTED, "Online identifier"),
    "user_agent": (RESTRICTED, "Online identifier"),
    "file": (RESTRICTED, "Document"),
    "last_login": (RESTRICTED, "Account activity"),
}
# Whole tables whose remaining columns are security records.
RESTRICTED_TABLES = {
    "audit_events",
    "audit_chain_entries",
    "audit_integrity_checks",
    "user_sessions",
}
