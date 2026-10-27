"""Versioned permission catalog (spec 26.4).

This is the single source of permission codenames; the database ``permissions`` table is
synchronised from it after every migration. Add permissions here as domains are built, with
separate permissions for viewing, editing, signing, approving and exporting (spec 13.2).
"""


class P:
    ORGANIZATION_VIEW = "organization.view"
    ORGANIZATION_MANAGE = "organization.manage"
    FACILITIES_VIEW = "facilities.view"
    FACILITIES_MANAGE = "facilities.manage"
    DEPARTMENTS_VIEW = "departments.view"
    DEPARTMENTS_MANAGE = "departments.manage"
    LOCATIONS_VIEW = "locations.view"
    LOCATIONS_MANAGE = "locations.manage"
    BEDS_STATUS_MANAGE = "beds.status.manage"
    STAFF_VIEW = "staff.view"
    STAFF_MANAGE = "staff.manage"
    STAFF_CREDENTIALS_VERIFY = "staff.credentials.verify"
    ROLES_VIEW = "access.roles.view"
    ROLES_MANAGE = "access.roles.manage"
    ROLE_ASSIGNMENTS_MANAGE = "access.assignments.manage"
    AUDIT_VIEW = "audit.view"
    ADMIN_CONSOLE = "platform.admin_console"


PERMISSIONS: dict[str, str] = {
    P.ADMIN_CONSOLE: "Use the Django admin operations console (all changes are audited)",
    P.ORGANIZATION_VIEW: "View organization configuration",
    P.ORGANIZATION_MANAGE: "Change organization configuration",
    P.FACILITIES_VIEW: "View facilities",
    P.FACILITIES_MANAGE: "Create facilities (organization-wide) and change them",
    P.DEPARTMENTS_VIEW: "View departments",
    P.DEPARTMENTS_MANAGE: "Create and change departments",
    P.LOCATIONS_VIEW: "View buildings, floors, wards, rooms and beds",
    P.LOCATIONS_MANAGE: "Create, change and deactivate buildings, floors, wards, rooms and beds",
    P.BEDS_STATUS_MANAGE: "Put beds into or out of maintenance, blocked or out of service",
    P.STAFF_VIEW: "View the staff directory, qualifications and credentials",
    P.STAFF_MANAGE: "Onboard staff and maintain their qualifications and credentials",
    P.STAFF_CREDENTIALS_VERIFY: "Verify staff qualifications and professional credentials",
    P.ROLES_VIEW: "View roles and role assignments",
    P.ROLES_MANAGE: "Create roles and change role permissions",
    P.ROLE_ASSIGNMENTS_MANAGE: "Grant and revoke role assignments",
    P.AUDIT_VIEW: "Search the audit log",
}

# Holding any of these makes two-factor sign-in mandatory (spec 13.1: "MFA for privileged
# users"; HIMS-IAM-005). Add clinical permissions here when clinical governance decides which
# clinical actions also require it (docs/status/Hospital_Departments_and_Doctors_RBAC.MD).
MFA_REQUIRED_PERMISSIONS: frozenset[str] = frozenset(
    {
        P.ADMIN_CONSOLE,
        P.ORGANIZATION_MANAGE,
        P.FACILITIES_MANAGE,
        P.LOCATIONS_MANAGE,
        P.STAFF_MANAGE,
        P.STAFF_CREDENTIALS_VERIFY,
        P.ROLES_MANAGE,
        P.ROLE_ASSIGNMENTS_MANAGE,
        P.AUDIT_VIEW,
    }
)

# Roles created for every new organization at provisioning. Clinical roles (doctor, nurse,
# pharmacist...) are added with their domains, after clinical governance approves the
# permission matrix (spec 26.4).
SYSTEM_ROLES: dict[str, dict] = {
    "organization-administrator": {
        "name": "Organization administrator",
        "description": "Full administrative access to organization configuration.",
        "permissions": [code for code in PERMISSIONS if code != P.AUDIT_VIEW],
    },
    "auditor": {
        "name": "Auditor / compliance officer",
        "description": "Read access to the audit log.",
        "permissions": [P.AUDIT_VIEW],
    },
    # Administrative roles usable today (see docs/status/Hospital_Departments_and_Doctors_RBAC.MD).
    "facility-administrator": {
        "name": "Facility (branch) administrator",
        "description": "Runs one branch: its details and departments. Assign at facility scope.",
        "permissions": [
            P.FACILITIES_VIEW,
            P.FACILITIES_MANAGE,
            P.DEPARTMENTS_VIEW,
            P.DEPARTMENTS_MANAGE,
            P.LOCATIONS_VIEW,
            P.LOCATIONS_MANAGE,
            P.BEDS_STATUS_MANAGE,
        ],
    },
    "hr-credentialing-officer": {
        "name": "HR / credentialing officer",
        "description": "Onboards staff and verifies qualifications and licences.",
        "permissions": [
            P.STAFF_VIEW,
            P.STAFF_MANAGE,
            P.STAFF_CREDENTIALS_VERIFY,
            P.FACILITIES_VIEW,
            P.DEPARTMENTS_VIEW,
        ],
    },
    "department-head": {
        "name": "Head of department (HOD)",
        "description": "Sees their department. Clinical approvals are added with clinical "
        "domains. Assign at department scope.",
        "permissions": [P.FACILITIES_VIEW, P.DEPARTMENTS_VIEW, P.LOCATIONS_VIEW],
    },
    "basic-staff": {
        "name": "Basic staff access",
        "description": "Minimum access for any employee: see their hospital and departments.",
        "permissions": [P.FACILITIES_VIEW, P.DEPARTMENTS_VIEW, P.LOCATIONS_VIEW],
    },
    "bed-manager": {
        "name": "Bed manager / ward clerk",
        "description": "Keeps beds usable: marks beds for maintenance, blocked or out of "
        "service. Bed allocation to patients is added in Phase 3. Assign at facility scope.",
        "permissions": [P.FACILITIES_VIEW, P.LOCATIONS_VIEW, P.BEDS_STATUS_MANAGE],
    },
}
