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
    "organization": "Hospital setup",
    "facility": "Hospital setup",
    "department": "Hospital setup",
    "location": "Locations and beds",
    "bed": "Locations and beds",
    "numbering": "Numbering",
    "feature": "Features",
    "admin": "Admin console",
    "audit": "Audit log",
}

LABELS: dict[str, str] = {
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
    A.AUTH_SESSIONS_ENDED: "Signed out of all devices",
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
    A.AUDIT_SEARCHED: "Audit log searched",
    A.AUDIT_EXPORTED: "Audit log exported",
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
