"""Plain-language names for audit events, for the Audit log screen (HIMS-AUD-003).

Every ``AuditAction`` must have a label here (a test enforces it). Admin-console changes are
recorded as ``admin.<record>.created|updated`` and get a generated label.
"""

from .services import AuditAction as A

CATEGORIES: dict[str, str] = {
    "auth": "Sign-in and security",
    "user": "Accounts",
    "access": "Access and roles",
    "staff": "Staff",
    "rota": "Rotas and leave",
    "leave": "Rotas and leave",
    "organization": "Hospital setup",
    "facility": "Hospital setup",
    "department": "Hospital setup",
    "location": "Locations and beds",
    "bed": "Locations and beds",
    "numbering": "Numbering",
    "feature": "Features",
    "admin": "Admin console",
    "audit": "Audit log",
    "notification": "Emails and SMS",
    "compliance": "Compliance",
    "recovery": "Backups and restore drills",
    "database": "Database access",
    "outbox": "Background jobs",
}

LABELS: dict[str, str] = {
    A.SHIFT_TYPE_CREATED: "Shift type added",
    A.SHIFT_TYPE_UPDATED: "Shift type changed",
    A.SHIFT_ADDED: "Shift or on-call planned",
    A.SHIFT_CANCELLED: "Shift or on-call cancelled",
    A.LEAVE_REQUESTED: "Leave asked for",
    A.LEAVE_APPROVED: "Leave approved",
    A.LEAVE_REJECTED: "Leave refused",
    A.LEAVE_CANCELLED: "Leave cancelled",
    A.ORGANIZATION_PROVISIONED: "Hospital set up",
    A.ORGANIZATION_UPDATED: "Hospital details changed",
    A.FACILITY_CREATED: "Facility added",
    A.FACILITY_UPDATED: "Facility changed",
    A.DEPARTMENT_CREATED: "Department added",
    A.DEPARTMENT_UPDATED: "Department changed",
    A.DEPARTMENT_HOURS_CHANGED: "Department opening hours changed",
    A.DEPARTMENT_SERVICE_CREATED: "Department service added",
    A.DEPARTMENT_SERVICE_UPDATED: "Department service changed",
    A.CATALOG_ITEM_CREATED: "Job title, specialty or qualification added",
    A.CATALOG_ITEM_UPDATED: "Job title, specialty or qualification changed",
    A.LOCATION_CREATED: "Location added (building, floor, ward, room or bed)",
    A.LOCATION_UPDATED: "Location changed",
    A.BED_STATUS_CHANGED: "Bed status changed",
    A.UPLOAD_BLOCKED: "Upload refused: a virus was found",
    A.STAFF_DOCUMENT_VIRUS_FOUND: "Virus found in a stored document (blocked)",
    A.STAFF_DOCUMENTS_SCANNED: "Stored documents checked for viruses",
    A.STAFF_PRIVILEGE_GRANTED: "Clinical privilege given",
    A.STAFF_PRIVILEGE_ENDED: "Clinical privilege ended",
    A.STAFFING_REQUIREMENT_CREATED: "Minimum staffing added",
    A.STAFFING_REQUIREMENT_UPDATED: "Minimum staffing changed",
    A.STAFFING_GAP_ALERT_SENT: "Staffing gaps emailed to planners",
    A.LEAVE_ENTITLEMENT_CREATED: "Leave entitlement added",
    A.LEAVE_ENTITLEMENT_UPDATED: "Leave entitlement changed",
    A.LEAVE_BALANCE_ADJUSTED: "Leave balance adjusted",
    A.EQUIPMENT_CREATED: "Equipment added",
    A.EQUIPMENT_UPDATED: "Equipment changed",
    A.EQUIPMENT_STATUS_CHANGED: "Equipment status changed",
    A.EQUIPMENT_SERVICE_RECORDED: "Equipment service or calibration recorded",
    A.ORGANIZATION_LOGO_CHANGED: "Hospital logo changed",
    A.MESSAGE_TEMPLATE_UPDATED: "Message wording changed",
    A.MESSAGE_TEMPLATE_RESET: "Message wording put back to the standard",
    A.NUMBERING_SCHEME_CREATED: "Numbering scheme added",
    A.NUMBERING_SCHEME_UPDATED: "Numbering scheme changed",
    A.NUMBERING_NEXT_NUMBER_SET: "Numbering continued from a previous system",
    A.FEATURE_FLAG_CHANGED: "Feature switched on or off",
    A.FEATURE_CATALOG_SYNCED: "New features added (default settings)",
    A.USER_CREATED: "Account created",
    A.ACCOUNT_CREATED: "Account added for someone who is not staff",
    A.ACCOUNT_DEACTIVATED: "Account switched off",
    A.ACCOUNT_REACTIVATED: "Account switched back on",
    A.USER_INVITATION_ISSUED: "Invitation sent",
    A.USER_INVITATION_ACCEPTED: "Invitation accepted (account activated)",
    A.USER_INVITATION_REJECTED: "Invalid or expired invitation link used",
    A.PASSWORD_RESET_REQUESTED: "Password reset requested",
    A.PASSWORD_RESET_COMPLETED: "Password reset completed",
    A.PASSWORD_RESET_REJECTED: "Invalid or expired password reset link used",
    A.AUTH_LOGIN: "Signed in",
    A.AUTH_LOGIN_FAILED: "Failed sign-in",
    A.AUTH_LOGOUT: "Signed out",
    A.AUTH_SESSIONS_ENDED: "Signed out of devices",
    A.AUTH_CONSOLE_ADDRESS_REFUSED: "Admin console refused: address not allowed",
    A.ACCESS_REVIEW_STARTED: "Access review started",
    A.ACCESS_REVIEW_DECIDED: "Access review decision (keep or remove)",
    A.ACCESS_REVIEW_COMPLETED: "Access review completed",
    A.ACCESS_REVIEW_CANCELLED: "Access review cancelled",
    A.ACCESS_REVIEW_EXPORTED: "Access review downloaded",
    A.ACCESS_REVIEW_REMINDER_SENT: "Access review reminder emailed",
    A.AUTH_IDENTITY_CONFIRMED: "Confirmed identity for sensitive actions",
    A.AUTH_IDENTITY_CONFIRM_FAILED: "Failed to confirm identity",
    A.AUTH_IDENTITY_CONFIRM_LOCKED: "Signed out after too many failed confirmations",
    A.AUTH_MFA_ENABLED: "Two-factor turned on",
    A.AUTH_MFA_DISABLED: "Two-factor turned off",
    A.AUTH_MFA_RESET: "Two-factor reset by an administrator",
    A.AUTH_MFA_VERIFIED: "Two-factor code accepted",
    A.AUTH_MFA_FAILED: "Wrong two-factor code",
    A.AUTH_MFA_RECOVERY_CODE_USED: "Backup code used",
    A.AUTH_MFA_RECOVERY_CODES_REGENERATED: "New backup codes created",
    A.ROLE_CREATED: "Role created",
    A.ROLE_UPDATED: "Role changed",
    A.ROLE_ASSIGNED: "Access given",
    A.ROLE_REVOKED: "Access removed",
    A.ACCESS_DENIED: "Access denied (permission denied screen)",
    A.ACCESS_NONE_ASSIGNED: "Signed in without any access yet",
    A.STAFF_CREATED: "Staff member added",
    A.STAFF_UPDATED: "Staff member changed",
    A.STAFF_DEPARTMENT_ASSIGNED: "Department posting added",
    A.STAFF_DEPARTMENT_ASSIGNMENT_ENDED: "Department posting ended",
    A.STAFF_QUALIFICATION_ADDED: "Qualification added",
    A.STAFF_QUALIFICATION_VERIFIED: "Qualification verified or rejected",
    A.STAFF_CREDENTIAL_ADDED: "Licence added",
    A.STAFF_CREDENTIAL_VERIFIED: "Licence verified or rejected",
    A.STAFF_DOCUMENT_UPLOADED: "Document uploaded (licence or qualification)",
    A.STAFF_DOCUMENT_DOWNLOADED: "Document opened or downloaded",
    A.STAFF_DOCUMENT_ARCHIVED: "Document archived",
    A.CREDENTIAL_EXPIRY_ALERT_SENT: "Licence expiry alert sent",
    A.ACCESS_DELEGATION_CREATED: "Cover arranged (access lent for a time)",
    A.ACCESS_DELEGATION_ENDED: "Cover ended early",
    A.COMPLIANCE_REQUIREMENT_UPDATED: "Compliance requirement updated",
    A.COMPLIANCE_RISK_CREATED: "Risk added",
    A.COMPLIANCE_RISK_UPDATED: "Risk updated",
    A.COMPLIANCE_INCIDENT_REPORTED: "Security incident reported",
    A.COMPLIANCE_INCIDENT_UPDATED: "Security incident updated",
    A.COMPLIANCE_NOTIFICATION_RECORDED: "Incident notification recorded",
    A.COMPLIANCE_BROWSER_REPORT_REVIEWED: "Browser block report reviewed",
    A.COMPLIANCE_CONSOLE_BLOCK_REVIEWED: "Refused console address reviewed",
    A.NOTIFICATION_RETRIED: "Email/SMS sent again",
    A.NOTIFICATION_TEST_SENT: "Test email/SMS sent",
    A.AUDIT_SEARCHED: "Audit log searched",
    A.AUDIT_EXPORTED: "Audit log exported",
    A.AUDIT_INTEGRITY_CHECKED: "Audit log integrity checked",
    A.AUDIT_INTEGRITY_ALERT_SENT: "Audit integrity problem: auditors alerted",
    A.BACKUP_CREATED: "Backup made",
    A.RESTORE_DRILL_COMPLETED: "Restore drill run",
    A.DATABASE_USERS_SET_UP: "Separate database users set up or their rights re-applied",
    A.OUTBOX_CLEANED_UP: "Old background events cleaned up",
    A.OUTBOX_EVENT_SENT_AGAIN: "Failed background event sent again",
    A.OUTBOX_EVENT_DISMISSED: "Failed background event dismissed",
}


def category(action: str) -> str:
    return CATEGORIES.get(action.split(".", 1)[0], "Other")


def label(action: str) -> str:
    if action in LABELS:
        return LABELS[action]
    parts = action.split(".")
    if parts[0] == "admin" and len(parts) == 3:
        verb = {"created": "added", "updated": "changed"}.get(parts[2], parts[2].replace("_", " "))
        return f"Admin console: {parts[1]} {verb}"
    return action


def all_actions() -> list[dict]:
    """Known events for the filter list, grouped by category (admin console changes as one)."""
    rows = [{"action": a, "label": text, "category": category(a)} for a, text in LABELS.items()]
    return sorted(rows, key=lambda row: (row["category"], row["label"]))
