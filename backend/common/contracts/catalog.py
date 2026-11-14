"""Which requirement each API view delivers (spec 25.3; HIMS-DOC-001).

Keys are view classes (``module.Class``); values are backlog ticket IDs, which are this project's
requirement IDs (ADR-032). A test fails when an API view is missing here or names a ticket that
the backlog does not have, so every endpoint traces to a requirement and back.
"""

_A = "apps.access_control.api."
_AU = "apps.audit.api."
_B = "apps.beds.api.views."
_C = "apps.compliance.api."
_F = "apps.facilities.api."
_I = "apps.identity.api."
_O = "apps.organizations.api.views."
_R = "apps.rosters.api."
_S = "apps.staff.api.views."

VIEW_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    # Hospital (organization) settings, logo and letterhead
    _O + "OrganizationView": ("HIMS-ORG-002", "HIMS-ORG-005"),
    _O + "LetterheadView": ("HIMS-ORG-006",),
    _O + "OrganizationLogoView": ("HIMS-ORG-006",),
    _O + "OrganizationLogoRemoveView": ("HIMS-ORG-006",),
    # Facilities, departments and locations
    _F + "views.FacilityViewSet": ("HIMS-FAC-001", "HIMS-FAC-003", "HIMS-FAC-006"),
    _F + "views.DepartmentViewSet": ("HIMS-FAC-002", "HIMS-FAC-006", "HIMS-FAC-007"),
    _F + "views.DepartmentServiceViewSet": ("HIMS-FAC-007",),
    _F + "location_views.BuildingViewSet": ("HIMS-FAC-004", "HIMS-FAC-005"),
    _F + "location_views.FloorViewSet": ("HIMS-FAC-004", "HIMS-FAC-005"),
    _F + "location_views.WardViewSet": ("HIMS-FAC-004", "HIMS-FAC-005"),
    _F + "location_views.RoomViewSet": ("HIMS-FAC-004", "HIMS-FAC-005"),
    _B + "BedViewSet": ("HIMS-FAC-004", "HIMS-FAC-005", "HIMS-PLAT-018"),
    _B + "FacilityLocationsView": ("HIMS-FAC-005",),
    _B + "BedBoardView": ("HIMS-FAC-008",),
    "apps.equipment.api.views.EquipmentViewSet": ("HIMS-FAC-009",),
    # Patients (Phase 2)
    "apps.patients.api.views.PatientViewSet": (
        "HIMS-PAT-001",
        "HIMS-PAT-002",
        "HIMS-PAT-005",
        "HIMS-PAT-006",
    ),
    "apps.patients.api.views.EmergencyAccessViewSet": ("HIMS-PAT-006",),
    # Numbering and features
    "apps.numbering.api.views.NumberingSchemeViewSet": ("HIMS-ORG-003",),
    "apps.numbering.api.views.IssuedNumberViewSet": ("HIMS-ORG-003",),
    "apps.features.api.views.FeatureListView": ("HIMS-ORG-004",),
    "apps.features.api.views.EffectiveFeaturesView": ("HIMS-ORG-004",),
    "apps.features.api.views.FeatureChangeView": ("HIMS-ORG-004",),
    # Sign-in, two-factor, passkeys, sessions and accounts
    _I + "views.CsrfTokenView": ("HIMS-IAM-002",),
    _I + "views.LoginView": ("HIMS-IAM-002", "HIMS-IAM-005"),
    _I + "views.LoginVerifyView": ("HIMS-IAM-005",),
    _I + "views.LoginPasskeyOptionsView": ("HIMS-IAM-014",),
    _I + "views.LoginPasskeyView": ("HIMS-IAM-014",),
    _I + "views.LogoutView": ("HIMS-IAM-002", "HIMS-IAM-006"),
    _I + "views.CurrentUserView": ("HIMS-IAM-002", "HIMS-UI-002"),
    _I + "views.NoAccessReportView": ("HIMS-UI-002",),
    _I + "views.InvitationInspectView": ("HIMS-IAM-003",),
    _I + "views.InvitationAcceptView": ("HIMS-IAM-003",),
    _I + "views.PasswordResetRequestView": ("HIMS-IAM-004",),
    _I + "views.PasswordResetInspectView": ("HIMS-IAM-004",),
    _I + "views.PasswordResetConfirmView": ("HIMS-IAM-004", "HIMS-IAM-006"),
    _I + "views.MfaStatusView": ("HIMS-IAM-005",),
    _I + "views.MfaSetupView": ("HIMS-IAM-005",),
    _I + "views.MfaConfirmView": ("HIMS-IAM-005",),
    _I + "views.MfaDisableView": ("HIMS-IAM-005", "HIMS-IAM-007"),
    _I + "views.MfaRecoveryCodesView": ("HIMS-IAM-005", "HIMS-IAM-007"),
    _I + "views.ConfirmIdentityView": ("HIMS-IAM-007",),
    _I + "views.EndIdentityConfirmationView": ("HIMS-IAM-007",),
    _I + "views.ConfirmIdentityPasskeyOptionsView": ("HIMS-IAM-007", "HIMS-IAM-014"),
    _I + "views.PasskeysView": ("HIMS-IAM-014",),
    _I + "views.PasskeyAddOptionsView": ("HIMS-IAM-014",),
    _I + "views.PasskeyAddView": ("HIMS-IAM-014",),
    _I + "views.PasskeyRemoveView": ("HIMS-IAM-014",),
    _I + "views.MySessionsView": ("HIMS-IAM-016",),
    _I + "views.MySessionEndView": ("HIMS-IAM-016",),
    _I + "views.MySessionsEndOthersView": ("HIMS-IAM-016",),
    _I + "account_views.AccountViewSet": ("HIMS-IAM-015", "HIMS-IAM-006", "HIMS-IAM-005"),
    # Roles, access reviews and cover
    _A + "views.PermissionViewSet": ("HIMS-IAM-009", "HIMS-IAM-013"),
    _A + "views.RoleViewSet": ("HIMS-IAM-009", "HIMS-IAM-013"),
    _A + "views.RoleAssignmentViewSet": ("HIMS-IAM-009", "HIMS-IAM-013"),
    _A + "views.AccessReviewViewSet": ("HIMS-IAM-012",),
    _A + "delegation_views.AccessDelegationViewSet": ("HIMS-IAM-017",),
    _A + "delegation_views.MyDelegationsView": ("HIMS-IAM-017",),
    _A + "support_views.SupportAccessViewSet": ("HIMS-IAM-021",),
    _A + "support_views.MySupportAccessViewSet": ("HIMS-IAM-021",),
    # Staff, credentials, documents, catalogs and privileges
    _S + "StaffMemberViewSet": (
        "HIMS-STAFF-001",
        "HIMS-STAFF-004",
        "HIMS-STAFF-005",
        "HIMS-STAFF-007",
        "HIMS-STAFF-008",
    ),
    _S + "StaffCredentialViewSet": ("HIMS-STAFF-003", "HIMS-STAFF-006"),
    _S + "StaffDocumentViewSet": ("HIMS-STAFF-005", "HIMS-STAFF-008"),
    _S + "DesignationViewSet": ("HIMS-STAFF-009", "HIMS-STAFF-010"),
    _S + "SpecialtyViewSet": ("HIMS-STAFF-002", "HIMS-STAFF-010"),
    _S + "QualificationTypeViewSet": ("HIMS-STAFF-002", "HIMS-STAFF-010"),
    _S + "ClinicalPrivilegeViewSet": ("HIMS-STAFF-016",),
    _S + "StaffPrivilegeViewSet": ("HIMS-STAFF-016",),
    # Rota, leave and staffing
    _R + "views.ShiftTypeViewSet": ("HIMS-STAFF-012",),
    _R + "views.ShiftViewSet": ("HIMS-STAFF-012",),
    _R + "views.RotaWeekView": ("HIMS-STAFF-012", "HIMS-STAFF-015"),
    _R + "views.RotaNowView": ("HIMS-STAFF-012",),
    _R + "views.MyScheduleView": ("HIMS-STAFF-012",),
    _R + "views.LeaveRequestViewSet": ("HIMS-STAFF-012", "HIMS-STAFF-013"),
    _R + "views.MyLeaveRequestsView": ("HIMS-STAFF-012", "HIMS-STAFF-013"),
    _R + "views.MyLeaveCancelView": ("HIMS-STAFF-012",),
    _R + "staffing_views.LeaveEntitlementViewSet": ("HIMS-STAFF-013",),
    _R + "staffing_views.LeaveAdjustmentViewSet": ("HIMS-STAFF-013",),
    _R + "staffing_views.LeaveBalancesView": ("HIMS-STAFF-013",),
    _R + "staffing_views.StaffingRequirementViewSet": ("HIMS-STAFF-015",),
    # Audit
    _AU + "views.AuditEventViewSet": ("HIMS-AUD-001", "HIMS-AUD-003"),
    _AU + "integrity.AuditIntegrityCheckViewSet": ("HIMS-SEC-010",),
    # Messages
    "apps.notifications.api.views.NotificationViewSet": ("HIMS-NOTIF-001",),
    "apps.notifications.api.template_views.MessageTemplateViewSet": ("HIMS-NOTIF-003",),
    # Compliance and security
    _C + "views.ComplianceRequirementViewSet": ("HIMS-COMP-001", "HIMS-COMP-002", "HIMS-COMP-003"),
    _C + "views.RiskEntryViewSet": ("HIMS-COMP-005",),
    _C + "views.ComplianceSummaryView": ("HIMS-COMP-004",),
    _C + "views.SecurityIncidentViewSet": ("HIMS-COMP-004",),
    _C + "browser_views.BrowserReportReceiveView": ("HIMS-SEC-012",),
    _C + "browser_views.BrowserSecurityReportViewSet": ("HIMS-SEC-012",),
    _C + "browser_views.SecurityStatusView": ("HIMS-SEC-012", "HIMS-SEC-015"),
    _C + "console_views.ConsoleAccessView": ("HIMS-SEC-015",),
    _C + "console_views.ConsoleAccessBlockViewSet": ("HIMS-SEC-015",),
    _C + "database_views.DatabaseAccessView": ("HIMS-OPS-007",),
    _C + "scanning_views.ScanningStatusView": ("HIMS-SEC-013",),
    _C + "scanning_views.ScanDocumentsView": ("HIMS-SEC-013",),
    _C + "review_views.SecurityReviewView": ("HIMS-SEC-011",),
    _C + "hosting_views.HostingReadinessView": ("HIMS-OPS-020",),
    _C + "retention_views.RetentionView": ("HIMS-COMP-006",),
    _C + "retention_views.RetentionPeriodView": ("HIMS-COMP-006",),
    _C + "retention_views.RetentionRunView": ("HIMS-COMP-006",),
    _C + "retention_views.RetentionPurgeRunViewSet": ("HIMS-COMP-006",),
    _C + "retention_views.LegalHoldViewSet": ("HIMS-COMP-006",),
    # Operations
    "common.outbox.api.BackgroundJobViewSet": ("HIMS-PLAT-007", "HIMS-PLAT-014"),
    "common.outbox.trigger.ScheduledJobsTriggerView": ("HIMS-OPS-023", "HIMS-OPS-024"),
    "apps.recovery.api.views.BackupViewSet": ("HIMS-OPS-009",),
    "apps.recovery.api.views.RestoreDrillViewSet": ("HIMS-OPS-009",),
    "apps.performance.api.views.PerformanceCheckViewSet": ("HIMS-DATA-002", "HIMS-OPS-017"),
    # This item: the API endpoints list itself
    "common.contracts.api.ApiEndpointsView": ("HIMS-DOC-001",),
}


# Business purpose of endpoints whose code has no docstring saying it ("METHOD path").
_V = "/api/v1/"
PURPOSES: dict[str, str] = {
    f"POST {_V}access-reviews/{{pk}}/cancel/": "Cancel an access review that is still open; "
    "decisions already taken stay on record.",
    f"POST {_V}access-reviews/{{pk}}/complete/": "Close an access review once every person in it "
    "has a decision.",
    f"POST {_V}accounts/{{pk}}/reactivate/": "Switch an account of someone who is not staff back "
    "on.",
    f"POST {_V}accounts/{{pk}}/sign-out-everywhere/": "End every session of this account on every "
    "device.",
    f"POST {_V}auth/confirm-identity/end/": 'End the "confirm it\'s you" window early (the app '
    "does this when the person signs out or walks away).",
    f"POST {_V}auth/invitations/accept/": "Set the first password from an invitation link; the "
    "account becomes active and the link stops working.",
    f"POST {_V}auth/invitations/inspect/": "Check an invitation link before showing the form "
    "(valid, expired or used), without revealing the account to strangers.",
    f"POST {_V}auth/login/": "Sign in with email and password. Accounts with two-factor get a "
    "second step; wrong details get the same answer whether or not the account exists.",
    f"POST {_V}auth/login/passkey/": "Finish the second sign-in step with a passkey.",
    f"POST {_V}auth/logout/": "Sign out: this session ends on the server.",
    f"GET {_V}auth/me/": "Who is signed in, their permissions with scope, theme and hospital "
    "details: what the app needs on every page load.",
    f"POST {_V}auth/mfa/confirm/": "Finish setting up the authenticator app with its first code; "
    "returns the backup codes once.",
    f"POST {_V}auth/mfa/disable/": "Switch off two-factor for yourself (not allowed for roles that "
    'require it). Sensitive: needs a recent "confirm it\'s you".',
    f"POST {_V}auth/mfa/recovery-codes/": "Make a new set of backup codes; the old ones stop "
    'working. Sensitive: needs a recent "confirm it\'s you".',
    f"POST {_V}auth/mfa/setup/": "Start setting up an authenticator app: returns the QR code and "
    "the secret to type in.",
    f"POST {_V}auth/passkeys/add/": "Save a new passkey after the device signed the challenge.",
    f"POST {_V}auth/password-reset/inspect/": "Check a password reset link before showing the "
    "form (valid, expired or used).",
    f"POST {_V}beds/bulk/": "Add many beds to one room in one go (codes in sequence; at most 60).",
    f"POST {_V}beds/{{pk}}/status/": "Set a bed to available, cleaning, maintenance or blocked, "
    "with a reason where needed. Occupied and reserved are set only by admissions (later phase).",
    f"POST {_V}browser-security-reports/{{pk}}/review/": "Mark a report of something the browser "
    "blocked as reviewed, with a note.",
    f"GET {_V}compliance-summary/": "Compliance at a glance: requirements by status for this "
    "hospital's country and the open risks.",
    f"POST {_V}console-access-blocks/{{pk}}/review/": "Mark a refused console visit (address not "
    "on the allow-list) as reviewed, with a note.",
    f"POST {_V}departments/{{pk}}/services/": "Add a service the department offers.",
    f"POST {_V}equipment/{{pk}}/service-records/": "Record a service, repair or calibration visit "
    "and the next due date.",
    f"POST {_V}equipment/{{pk}}/status/": "Change an item's status (in service, under maintenance, "
    "out of service, retired) with a reason.",
    f"POST {_V}leave-requests/{{pk}}/approve/": "Approve a leave request (optionally cancelling "
    "the person's shifts on those days); approved days count against the balance.",
    f"POST {_V}leave-requests/{{pk}}/cancel/": "Cancel approved leave before it ends, with a "
    "reason; the days go back to the balance.",
    f"POST {_V}leave-requests/{{pk}}/reject/": "Turn down a leave request, with a reason.",
    f"POST {_V}legal-holds/{{pk}}/release/": "Release a legal hold, with a reason; the records it "
    "protected follow the normal retention periods again.",
    f"POST {_V}message-templates/{{pk}}/reset/": "Put a message back to the standard wording.",
    f"POST {_V}notifications/test/": "Send a test message (email, or SMS printed on the "
    "console) to check that messages go out.",
    f"POST {_V}notifications/{{pk}}/send-again/": "Send a failed message again.",
    f"POST {_V}numbering-schemes/{{pk}}/next-number/": "Move a scheme's next number forward (for "
    "example after moving from paper records); it can never go back.",
    f"POST {_V}organization/logo/remove/": "Remove the hospital logo from letterheads and emails.",
    f"GET {_V}retention/": "How long each kind of record is kept, the legal holds and the last "
    "purge.",
    f"POST {_V}role-assignments/{{pk}}/revoke/": "End a role grant now, with a reason.",
    f"POST {_V}security-incidents/{{pk}}/notifications/{{notification_id}}/": "Record that one "
    "required notice about an incident (regulator, people affected) was sent, or why not.",
    f"POST {_V}security/browser-reports/": "Receives the browser's own reports of anything the "
    "security rules blocked (no sign-in; size-limited and rate limited).",
    f"GET {_V}security/console-access/": "Who may reach the admin console from where, and the "
    "recent refusals.",
    f"GET {_V}security/database-access/": "Which database user the app runs as and what that user "
    "is not allowed to do.",
    f"GET {_V}security/status/": "Security status at a glance: headers, reports, console access, "
    "upload scanning and database users.",
    f"GET {_V}security/upload-scanning/": "Whether uploads are checked for viruses, and the counts "
    "of files checked, blocked and waiting.",
    f"POST {_V}shifts/{{pk}}/cancel/": "Cancel a shift, with a reason; it stays on record.",
    f"POST {_V}staff-credentials/{{pk}}/verify/": "Mark a licence or registration as checked "
    "against the issuer, or rejected. Nobody verifies their own.",
    f"GET {_V}staff-documents/{{pk}}/download/": "Download one staff document; every download is "
    "audited.",
    f"POST {_V}staff-privileges/{{pk}}/end/": "End a clinical privilege, with a reason. It stays "
    "on record.",
    f"POST {_V}staff/{{pk}}/credentials/": "Add a licence or registration (body, number, expiry) "
    "to this person; it starts as not verified.",
    f"POST {_V}staff/{{pk}}/department-assignments/": "Post this person to a department (primary "
    "or additional), from a start date.",
    f"POST {_V}staff/{{pk}}/qualifications/": "Add a qualification (degree, diploma, fellowship) "
    "to this person; it starts as not verified.",
}


def requirements_for(view_cls) -> tuple[str, ...]:
    return VIEW_REQUIREMENTS.get(f"{view_cls.__module__}.{view_cls.__qualname__}", ())
