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
    "rosters": {
        "name": "Rotas, on-call and leave",
        "owner": "Staff/credential domain (heads of department plan; approvers decide leave)",
        "docs": ["rotas-and-leave.md"],
    },
    "audit": {
        "name": "Audit log and tamper evidence",
        "owner": "Audit domain (separate security boundary)",
        "docs": ["audit-integrity.md", "../../decisions/ADR-013-audit-log-storage.md"],
    },
    "compliance": {
        "name": "Compliance: requirements, risks, security incidents",
        "owner": "Compliance / security officer",
        "docs": ["../../compliance/README.md"],
    },
    "notifications": {
        "name": "Notifications: emails and SMS",
        "owner": "Platform (each sending domain owns its wording)",
        "docs": ["../../workflows/notifications.md"],
    },
    "recovery": {
        "name": "Backups and restore drills",
        "owner": "Platform / operations (evidence for auditors)",
        "docs": ["../../workflows/backup-and-restore.md"],
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
    "bed_status_changes": "Append-only (database trigger); one row per bed status change, from, "
    "to, why, who and when (HIMS-FAC-008). Earlier changes copied from the audit log once.",
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
    "shift_types": "Catalog: never deleted; switched off (`is_active`). New times apply to shifts "
    "planned afterwards.",
    "shifts": "Never deleted; cancelled with a reason. Past shifts cannot be changed.",
    "leave_requests": "Never deleted; requested -> approved, refused or cancelled, each with who "
    "and when. Retention period: decision pending with the other HR records (🔒 LEGAL).",
    "audit_events": "Append-only: a database trigger refuses changes and deletes. Retention and "
    "legal hold: decision pending (🔒 LEGAL).",
    "audit_chain_entries": "Append-only (database trigger); one link per sealed audit event.",
    "audit_integrity_checks": "Append-only (database trigger); one row per check.",
    "outbox_events": "Published and dismissed rows deleted by the daily clean-up after "
    "`HIMS_OUTBOX_RETENTION_DAYS` (30); waiting and failed rows never automatically (a person "
    "sends them again or dismisses them, with a reason; HIMS-PLAT-014).",
    "outbox_processed_events": "Kept for duplicate detection; deleted by the daily clean-up "
    "after the retention period, unless the event can still run again (HIMS-PLAT-014).",
    "compliance_requirements": "Wording synced from code; removed items switched off, never "
    "deleted. Status changes audited.",
    "compliance_risks": "Never deleted; closed with a status. Changes audited.",
    "browser_security_reports": "One row per day and kind of block, at most 500 a day. Purge "
    "comes with the retention job (HIMS-COMP-006).",
    "console_access_blocks": "One row per day and refused address, at most 500 a day; reviewed, "
    "never edited otherwise. Purge comes with the retention job (HIMS-COMP-006).",
    "security_incidents": "Never deleted; closed with a summary. Keep at least 6 years (US "
    "HIPAA documentation rule); counsel sets the rest.",
    "security_incident_notifications": "Never deleted; the evidence that each legal notice was "
    "made, with its reference.",
    "notifications": "Kept as the delivery log; the real (secret-bearing) text is erased once "
    "delivered. Retention period: decision pending with the other records (🔒 LEGAL).",
    "recovery_backups": "Append-only (database trigger); one row per backup made on a developer "
    "PC. The backup files live outside the database (`HIMS_BACKUP_DIR`).",
    "recovery_restore_drills": "Append-only (database trigger); one row per restore drill, the "
    "evidence that backups can be restored (spec 27.1).",
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
    "outbox_events.resolution_note": (RESTRICTED, "Decision note (no patient details)"),
    "audit_events.changes": (RESTRICTED, "Audit content (before/after values)"),
    "audit_events.metadata": (RESTRICTED, "Audit content"),
    "audit_events.reason": (RESTRICTED, "Audit content"),
    "audit_integrity_checks.problems": (RESTRICTED, "Audit content"),
    "facilities.phone": (INTERNAL, "Facility contact"),
    "facilities.address_line1": (INTERNAL, "Facility address"),
    "facilities.address_line2": (INTERNAL, "Facility address"),
    "facilities.postal_code": (INTERNAL, "Facility address"),
    "staff_documents.sha256": (INTERNAL, "Checksum"),
    "browser_security_reports.review_note": (RESTRICTED, "Reviewer note (no patient details)"),
    "console_access_blocks.review_note": (RESTRICTED, "Reviewer note (no patient details)"),
    "console_access_blocks.last_path": (INTERNAL, "Console page (ids removed)"),
    "security_incidents.title": (RESTRICTED, "Incident record"),
    "security_incidents.description": (RESTRICTED, "Incident record (no patient details)"),
    "security_incidents.actions_taken": (RESTRICTED, "Incident record"),
    "security_incidents.closure_summary": (RESTRICTED, "Incident record"),
    "security_incident_notifications.reference": (RESTRICTED, "Incident record"),
    "security_incident_notifications.note": (RESTRICTED, "Incident record"),
    "notifications.recipients": (RESTRICTED, "Contact"),
    "notifications.subject": (RESTRICTED, "Message (secrets hidden)"),
    "notifications.body": (RESTRICTED, "Message (secrets hidden)"),
    "notifications.body_encrypted": (SECRET, "Message until delivered (encrypted)"),
    "notifications.last_error": (INTERNAL, "System diagnostics"),
    "recovery_backups.manifest": (INTERNAL, "Inventory: counts and fingerprints, no contents"),
    "recovery_backups.dump_sha256": (INTERNAL, "Checksum"),
    "recovery_restore_drills.checks": (INTERNAL, "Check results (table names, no contents)"),
    "staff_documents.original_name": (RESTRICTED, "Document (file name)"),
    "access_review_items.account_active": (RESTRICTED, "Access evidence"),
    "access_review_items.last_signed_in_at": (RESTRICTED, "Access evidence"),
    "leave_requests.leave_type": (RESTRICTED, "Personal (e.g. sick leave)"),
    "leave_requests.reason": (RESTRICTED, "Personal note (no medical details)"),
    "leave_requests.decision_note": (RESTRICTED, "Personal note"),
    "leave_requests.cancel_reason": (RESTRICTED, "Personal note"),
    "leave_requests.start_date": (RESTRICTED, "Personal (time away)"),
    "leave_requests.end_date": (RESTRICTED, "Personal (time away)"),
    "shifts.note": (RESTRICTED, "Work note (no patient details)"),
    "bed_status_changes.reason": (INTERNAL, "Bed status reason (no patient details)"),
    "shifts.cancel_reason": (RESTRICTED, "Work note"),
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
