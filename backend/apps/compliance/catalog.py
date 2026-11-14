"""The regulatory requirements and starting risks HIMS tracks (spec 13, 23, 26.7).

This is the source for the screen and for docs/compliance/requirements-matrix.md and
risk-register.md (`python manage.py compliance_docs`). An engineering summary to organise the
work, NOT legal advice: counsel must confirm applicability, wording and dates (spec 26.7).
`support` says what the software does; only the hospital can mark a requirement verified.
"""

NS = "not_started"
IP = "in_progress"
DONE = "implemented"

# code, jurisdiction, regulation, citation, title, summary, support, starting status
REQUIREMENTS: list[tuple[str, str, str, str, str, str, str, str]] = [
    # --- United States: HIPAA Security Rule ---------------------------------------------------
    (
        "HIPAA-SEC-RISK-ANALYSIS",
        "US",
        "HIPAA Security Rule",
        "45 CFR 164.308(a)(1)(ii)(A)",
        "Security risk analysis",
        "Assess risks to the confidentiality, integrity and availability of electronic patient "
        "data.",
        "Threat model and risk register (Compliance page, docs/compliance/threat-model.md). The "
        "hospital must complete it for its own site and hosting.",
        IP,
    ),
    (
        "HIPAA-SEC-RISK-MGMT",
        "US",
        "HIPAA Security Rule",
        "45 CFR 164.308(a)(1)(ii)(B)",
        "Risk management",
        "Reduce risks to a reasonable and appropriate level.",
        "Risk register with treatment, owner and review date.",
        IP,
    ),
    (
        "HIPAA-SEC-ACTIVITY-REVIEW",
        "US",
        "HIPAA Security Rule",
        "45 CFR 164.308(a)(1)(ii)(D)",
        "Information system activity review",
        "Regularly review audit logs and access reports.",
        "Audit log screen, tamper check, access reviews. The hospital must run the reviews.",
        IP,
    ),
    (
        "HIPAA-SEC-OFFICER",
        "US",
        "HIPAA Security Rule",
        "45 CFR 164.308(a)(2)",
        "Security official",
        "Name one person responsible for security.",
        "Compliance officer role in HIMS. The hospital names the person.",
        NS,
    ),
    (
        "HIPAA-SEC-WORKFORCE",
        "US",
        "HIPAA Security Rule",
        "45 CFR 164.308(a)(3), (a)(4)",
        "Workforce access management",
        "Give staff only the access they need; end it promptly when they leave.",
        "Roles and scopes, default deny, periodic access reviews, cover with end dates, sessions "
        "ended when employment ends.",
        DONE,
    ),
    (
        "HIPAA-SEC-TRAINING",
        "US",
        "HIPAA Security Rule",
        "45 CFR 164.308(a)(5)",
        "Security awareness training",
        "Train all staff, including how to report incidents.",
        "Report-an-incident button for all staff. The training itself is the hospital's.",
        NS,
    ),
    (
        "HIPAA-SEC-INCIDENTS",
        "US",
        "HIPAA Security Rule",
        "45 CFR 164.308(a)(6)",
        "Security incident procedures",
        "Identify, respond to, document and mitigate incidents.",
        "Incident log with deadlines and docs/compliance/incident-response-runbook.md.",
        DONE,
    ),
    (
        "HIPAA-SEC-CONTINGENCY",
        "US",
        "HIPAA Security Rule",
        "45 CFR 164.308(a)(7)",
        "Contingency plan",
        "Backups, disaster recovery and emergency-mode operation, tested.",
        "Planned with the hosting stage (backups, restore drills, RTO/RPO).",
        NS,
    ),
    (
        "HIPAA-SEC-BAA",
        "US",
        "HIPAA Security Rule",
        "45 CFR 164.308(b), 164.502(e)",
        "Business associate agreements",
        "Sign agreements with vendors that handle patient data.",
        "Vendor list in docs/compliance/vendors.md. The contracts are the hospital's.",
        NS,
    ),
    (
        "HIPAA-SEC-PHYSICAL",
        "US",
        "HIPAA Security Rule",
        "45 CFR 164.310",
        "Physical safeguards",
        "Protect facilities, workstations and devices.",
        "Hosting provider and hospital responsibility; automatic sign-out helps workstations.",
        NS,
    ),
    (
        "HIPAA-SEC-ACCESS-CONTROL",
        "US",
        "HIPAA Security Rule",
        "45 CFR 164.312(a)",
        "Technical access control",
        "Unique user IDs, emergency access, automatic logoff and encryption where appropriate.",
        "Unique accounts, 30-minute sign-out, permission checks on the server, encrypted secrets. "
        "Still to come: emergency access (Phase 2), encryption at rest (hosting).",
        IP,
    ),
    (
        "HIPAA-SEC-AUDIT-CONTROLS",
        "US",
        "HIPAA Security Rule",
        "45 CFR 164.312(b)",
        "Audit controls",
        "Record and examine activity in systems holding patient data.",
        "Append-only audit log with a tamper-evident chain. Opening a patient's record is "
        "audited since HIMS-PAT-001 (2026-11-12), every patient search since HIMS-PAT-002 "
        "(2026-11-13: its kind and result count, never what was typed); medical records see "
        "each record's history, who opened and changed it, and seeing it is audited too "
        "(HIMS-PAT-005, 2026-11-14); clinical chart reads come with Phase 2.",
        DONE,
    ),
    (
        "HIPAA-SEC-INTEGRITY",
        "US",
        "HIPAA Security Rule",
        "45 CFR 164.312(c)",
        "Integrity",
        "Protect patient data from improper change or destruction.",
        "Versioned edits, nothing deleted, audit tamper check. Clinical amendments come with "
        "Phase 2.",
        IP,
    ),
    (
        "HIPAA-SEC-AUTHENTICATION",
        "US",
        "HIPAA Security Rule",
        "45 CFR 164.312(d)",
        "Person authentication",
        "Verify that people are who they claim to be.",
        "Strong passwords, two-factor sign-in for privileged roles, sign-in throttling.",
        DONE,
    ),
    (
        "HIPAA-SEC-TRANSMISSION",
        "US",
        "HIPAA Security Rule",
        "45 CFR 164.312(e)",
        "Transmission security",
        "Protect data sent over networks.",
        "Production settings force HTTPS and secure cookies; TLS is set up at hosting.",
        IP,
    ),
    (
        "HIPAA-SEC-DOCUMENTATION",
        "US",
        "HIPAA Security Rule",
        "45 CFR 164.316(b)",
        "Policies kept six years",
        "Keep written policies and required records for six years.",
        "docs/compliance holds the drafts; the hospital adopts and keeps them.",
        IP,
    ),
    # --- United States: Breach Notification and Privacy Rules ---------------------------------
    (
        "HIPAA-BREACH-INDIVIDUALS",
        "US",
        "HIPAA Breach Notification Rule",
        "45 CFR 164.404",
        "Tell affected people",
        "Without unreasonable delay and no later than 60 days after discovering the breach.",
        "Incident log sets the 60-day deadline and alerts before it passes.",
        DONE,
    ),
    (
        "HIPAA-BREACH-HHS",
        "US",
        "HIPAA Breach Notification Rule",
        "45 CFR 164.408",
        "Tell HHS",
        "500 or more people: within 60 days of discovery. Fewer: within 60 days after the year "
        "ends.",
        "Incident log works out the right deadline from the number of people.",
        DONE,
    ),
    (
        "HIPAA-BREACH-MEDIA",
        "US",
        "HIPAA Breach Notification Rule",
        "45 CFR 164.406",
        "Tell the media",
        "More than 500 residents of a state or area: within 60 days.",
        "Incident log adds this step above 500 people. Counsel checks the per-state count.",
        DONE,
    ),
    (
        "HIPAA-PRIV-NPP",
        "US",
        "HIPAA Privacy Rule",
        "45 CFR 164.520",
        "Notice of Privacy Practices",
        "Give patients the notice and record acknowledgment.",
        "Recorded at registration since HIMS-PAT-001 (2026-11-12, D9): privacy notice given, "
        "with history of every decision. Counsel confirms the wording.",
        IP,
    ),
    (
        "HIPAA-PRIV-MIN-NECESSARY",
        "US",
        "HIPAA Privacy Rule",
        "45 CFR 164.502(b)",
        "Minimum necessary",
        "Use and show only the patient data needed for the task.",
        "Least-privilege roles and scopes; the patient list shows the minimum and ID numbers "
        "are masked (HIMS-PAT-001); patient search returns the same minimum, at most 50 "
        "(HIMS-PAT-002); clinical patient-level rules come with Phase 2.",
        IP,
    ),
    (
        "HIPAA-PRIV-ACCESS",
        "US",
        "HIPAA Privacy Rule",
        "45 CFR 164.524",
        "Patient right of access",
        "Let patients see and get a copy of their records.",
        "Visit summary in Phase 2; patient portal in Phase 6.",
        NS,
    ),
    (
        "US-STATE-LAWS",
        "US",
        "State privacy and medical record laws",
        "Depends on state",
        "State requirements",
        "Some states add rules on minors, sensitive conditions and breach notices.",
        "Counsel lists the states served and their rules.",
        NS,
    ),
    # --- India ----------------------------------------------------------------------------------
    (
        "DPDP-NOTICE-CONSENT",
        "IN",
        "DPDP Act 2023 and Rules 2025",
        "Sections 5, 6; Rule 3",
        "Notice and consent",
        "Tell people what data is processed and why; obtain consent or rely on a lawful use.",
        "Recorded at registration since HIMS-PAT-001 (D9): privacy notice, SMS and email "
        "consent with history and withdrawal. Counsel confirms the basis for treatment.",
        IP,
    ),
    (
        "DPDP-SECURITY",
        "IN",
        "DPDP Act 2023 and Rules 2025",
        "Section 8(5); Rule 6",
        "Reasonable security safeguards",
        "Encryption or masking, access control, logging, monitoring, backups and contracts.",
        "Access control, encrypted secrets and identifiers, audit log. Backups come with hosting.",
        IP,
    ),
    (
        "DPDP-LOGS",
        "IN",
        "DPDP Rules 2025",
        "Rule 6",
        "Keep logs for at least one year",
        "Keep logs and related data for breach detection for at least one year.",
        "Audit events are never deleted; system logs are set up at hosting.",
        IP,
    ),
    (
        "DPDP-BREACH",
        "IN",
        "DPDP Act 2023 and Rules 2025",
        "Section 8(6); Rule 7",
        "Breach notification",
        "Tell the Board and affected people without delay; detailed report to the Board within "
        "72 hours.",
        "Incident log sets the deadlines and alerts before they pass.",
        DONE,
    ),
    (
        "DPDP-RETENTION",
        "IN",
        "DPDP Act 2023 and Rules 2025",
        "Section 8(7); Rule 8",
        "Erase data when no longer needed",
        "Erase personal data once the purpose is over, unless another law requires keeping it.",
        "Retention schedule drafted in docs/compliance/retention-schedule.md. Daily purge of "
        "sign-ins, messages, invitations, resets and security logs once the hospital sets "
        "periods, with legal hold (Compliance, Retention tab); periods need counsel.",
        NS,
    ),
    (
        "DPDP-RIGHTS",
        "IN",
        "DPDP Act 2023 and Rules 2025",
        "Sections 11 to 14",
        "Rights of the person",
        "Access, correction, erasure, grievance redress and nomination.",
        "Corrections are audited today; a request process comes with Phase 2.",
        NS,
    ),
    (
        "DPDP-CHILDREN",
        "IN",
        "DPDP Act 2023 and Rules 2025",
        "Section 9; Rule 10",
        "Children's data",
        "Verifiable parental consent for children; counsel checks health exemptions.",
        "A parent or guardian is asked for at registration under 18 (or a reason is recorded), "
        "since HIMS-PAT-001. Counsel confirms consent by guardians.",
        IP,
    ),
    (
        "DPDP-PROCESSORS",
        "IN",
        "DPDP Act 2023",
        "Section 8(2)",
        "Contracts with processors",
        "Use processors only under a valid contract.",
        "Vendor list in docs/compliance/vendors.md. The contracts are the hospital's.",
        NS,
    ),
    (
        "DPDP-CONTACT",
        "IN",
        "DPDP Act 2023 and Rules 2025",
        "Section 8(9); Rule 9",
        "Published contact",
        "Publish who answers questions about personal data.",
        "The hospital names the person; shown in the privacy notice in Phase 2.",
        NS,
    ),
    (
        "CERTIN-REPORTING",
        "IN",
        "CERT-In Directions (28 April 2022)",
        "IT Act section 70B(6)",
        "Report cyber incidents within 6 hours",
        "Report listed cyber incidents within 6 hours of noticing them.",
        "Incident log sets a 6-hour deadline and emails the compliance team at once.",
        DONE,
    ),
    (
        "CERTIN-LOGS",
        "IN",
        "CERT-In Directions (28 April 2022)",
        "IT Act section 70B(6)",
        "Keep system logs 180 days in India",
        "Keep logs of systems for a rolling 180 days within India.",
        "Audit events are kept; system logs are set up at hosting.",
        IP,
    ),
    (
        "CERTIN-TIME-SYNC",
        "IN",
        "CERT-In Directions (28 April 2022)",
        "IT Act section 70B(6)",
        "Synchronise clocks",
        "Synchronise system clocks to a reliable national time source.",
        "Set up at hosting.",
        NS,
    ),
    (
        "IN-IT-ACT-SPDI",
        "IN",
        "IT Act 2000 and SPDI Rules 2011",
        "Section 43A",
        "Sensitive personal data practices",
        "Reasonable security practices for health data; counsel confirms status as DPDP commences.",
        "Same safeguards as DPDP-SECURITY.",
        IP,
    ),
    (
        "ABDM-HDMP",
        "IN",
        "ABDM Health Data Management Policy",
        "Consult ABDM documents",
        "ABDM participation",
        "Consent-based exchange and security rules for ABHA and health records, if the hospital "
        "joins.",
        "ABHA numbers recorded as not verified since HIMS-PAT-001 (encrypted, masked); ABDM "
        "integration in Phase 6.",
        NS,
    ),
    (
        "AADHAAR-STORAGE",
        "IN",
        "Aadhaar Act 2016 and UIDAI rules",
        "Counsel to confirm",
        "Storing Aadhaar numbers",
        "UIDAI rules restrict storing full Aadhaar numbers. Decision D6 allows entry for now.",
        "Encrypted, masked and marked not verified since HIMS-PAT-001 (ADR-036). Must be "
        "settled before real patients.",
        NS,
    ),
    (
        "IN-MEDICAL-RECORDS",
        "IN",
        "Medical council regulations and state rules",
        "Counsel to confirm",
        "Medical record retention",
        "Keep patient records for the required period; medico-legal cases often longer.",
        "Nothing is deleted; docs/compliance/retention-schedule.md lists what counsel must set.",
        NS,
    ),
    # --- Both -----------------------------------------------------------------------------------
    (
        "ALL-THREAT-MODEL",
        "ALL",
        "HIMS specification",
        "Spec 23",
        "Threat model and risk assessment",
        "Completed and reviewed before go-live.",
        "docs/compliance/threat-model.md and the risk register; needs security review.",
        IP,
    ),
    (
        "ALL-RETENTION",
        "ALL",
        "HIMS specification",
        "Spec 13.3, 13.4, 23",
        "Retention and legal hold",
        "Documented retention, deletion and legal-hold rules.",
        "docs/compliance/retention-schedule.md; retention periods, legal holds and a recorded "
        "daily purge (Compliance, Retention tab); periods need counsel.",
        IP,
    ),
    (
        "ALL-INCIDENT-DRILL",
        "ALL",
        "HIMS specification",
        "Spec 27.5",
        "Incident response readiness",
        "Run through the incident process before go-live.",
        "Runbook and incident log exist; the drill is the hospital's.",
        NS,
    ),
    (
        "ALL-COUNSEL-REVIEW",
        "ALL",
        "HIMS specification",
        "Spec 13, 26.7",
        "Counsel review",
        "Qualified counsel validates this matrix against the real services.",
        "This register and docs/compliance are prepared for that review.",
        NS,
    ),
]

# code, title, description, category, likelihood, impact, mitigation
RISKS: list[tuple[str, str, str, str, int, int, str]] = [
    (
        "R-001",
        "Stolen staff password",
        "A password is phished or reused and used to sign in.",
        "access",
        4,
        4,
        "Two-factor for privileged roles, phishing-resistant passkeys as a second factor "
        "(HIMS-IAM-014), throttling per address and per account, sessions ended after 30 minutes "
        "without use and after 12 hours (HIMS-SEC-011), sign-in register; the admin console "
        "answers only allowed addresses (HIMS-SEC-015). Planned: two-factor for clinical roles "
        "(D13), firewall rule at hosting (HIMS-OPS-020).",
    ),
    (
        "R-002",
        "Excessive or stale access",
        "People keep access they no longer need.",
        "access",
        3,
        4,
        "Least-privilege roles, 90-day access reviews, access ended on leaving.",
    ),
    (
        "R-003",
        "Insider browses records",
        "Staff open records without a care reason.",
        "access",
        3,
        5,
        "Audit log; opening a patient's record audited (HIMS-PAT-001), every search too, "
        "with at most 50 minimal results (HIMS-PAT-002); medical records see who opened "
        "each record on its History tab (HIMS-PAT-005). Planned in Phase 2: "
        "patient-level rules, restricted records, emergency access review.",
    ),
    (
        "R-004",
        "Privilege escalation bug",
        "A flaw lets someone act beyond their role.",
        "application",
        2,
        5,
        "Default-deny server checks, escalation guard, permission tests; every endpoint's "
        "access rule read from the code and pinned by tests (HIMS-DOC-001); internal security "
        "review (HIMS-SEC-011). Planned: independent penetration test (HIMS-SEC-021).",
    ),
    (
        "R-005",
        "Injection or cross-site scripting",
        "Malicious input runs code or queries.",
        "application",
        2,
        5,
        "ORM queries, React escaping, CSRF protection, security headers and "
        "content security policy with reports of anything blocked (HIMS-SEC-012).",
    ),
    (
        "R-006",
        "Malicious file upload",
        "An uploaded document carries malware.",
        "application",
        3,
        3,
        "Type and size checks, no public links, sandboxed responses; every upload checked "
        "for viruses before it is stored, uploads refused while the scanner is unreachable, "
        "refusals audited and reported (HIMS-SEC-013).",
    ),
    (
        "R-007",
        "Audit log tampering",
        "Someone with database access alters the audit trail.",
        "data",
        2,
        5,
        "Append-only triggers, keyed hash chain, daily check; the app's own database user "
        "cannot change, delete or empty the audit log or touch its triggers (HIMS-OPS-007). "
        "Planned: external copy of the chain head (HIMS-SEC-016).",
    ),
    (
        "R-008",
        "Secret or key leak",
        "Credentials reach the code, logs or a laptop.",
        "data",
        3,
        5,
        "Secret scanning in CI, gitignored environment files, encrypted secrets with key "
        "rotation (`rotate_encryption_keys`, HIMS-SEC-011). Planned: managed secret store at "
        "hosting.",
    ),
    (
        "R-009",
        "Data sent to the wrong place",
        "Personal data leaks through logs, traces or email.",
        "data",
        3,
        4,
        "No query strings in logs or traces, hidden sign-in links, no clinical text "
        "in messages; tested.",
    ),
    (
        "R-010",
        "Data loss or ransomware",
        "Data is destroyed or encrypted by an attacker.",
        "availability",
        3,
        5,
        "Backups and restore drills with audit-chain checks on a developer PC (HIMS-OPS-009). "
        "Planned at hosting: scheduled backups, point-in-time recovery, cloud restore drill "
        "(HIMS-OPS-018), RTO/RPO. Until then no real patient data is entered.",
    ),
    (
        "R-011",
        "Vulnerable third-party library",
        "A dependency has a known or planted flaw.",
        "supply_chain",
        3,
        4,
        "Hash-locked libraries, pinned actions, vulnerability scans in CI, Dependabot.",
    ),
    (
        "R-012",
        "One hospital sees another's data",
        "Data crosses between hospital deployments.",
        "data",
        1,
        5,
        "One database per hospital, startup environment guard, no cross-database links; "
        "background events of another hospital refused (HIMS-SEC-011). Planned: isolation tests "
        "at hosting.",
    ),
    (
        "R-013",
        "Missed legal breach deadline",
        "An incident is not reported on time.",
        "compliance",
        3,
        4,
        "Incident log with deadlines and alerts, runbook. Planned: drill.",
    ),
    (
        "R-014",
        "Wrong-patient record",
        "Clinical data is filed against the wrong person.",
        "clinical",
        3,
        5,
        "Designed for Phase 2: duplicate check, identity header, entered-in-error "
        "workflow, two-person merge. Needs doctor sign-off.",
    ),
    (
        "R-015",
        "Going live before compliance is complete",
        "Real patient data enters too early.",
        "compliance",
        2,
        5,
        "This register; spec 27.5 go/no-go; legal items closed first.",
    ),
    (
        "R-016",
        "Records deleted too early or kept too long",
        "The purge removes records still needed, or personal data is kept past its purpose.",
        "compliance",
        2,
        4,
        "Purge limited to housekeeping records; nothing deleted until a period is set; "
        "minimum periods; shorter periods wait 7 days; legal holds always win; every run "
        "recorded. Clinical, financial and audit records are never purged.",
    ),
]
