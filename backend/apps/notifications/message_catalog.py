"""Every message HIMS sends, with its standard wording (HIMS-NOTIF-003; spec 4.1 "templates and
notification settings", 4.23). A hospital can change the wording; the standard stays here.

Rules for the wording: placeholders are written ``{{name}}`` and only the variables listed for
that message exist, so nobody can pull other data into a message by typing a placeholder. The
values never hold patient or incident details (spec 13.3). Text is plain: HIMS does not run
templates as code. ``required`` variables cannot be removed, because the message is useless
without them (for example the activation link).

The test message on the Messages page is not listed: it checks that delivery works and promises
to contain no personal data, so it is not editable.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Variable:
    name: str
    description: str
    sample: str


@dataclass(frozen=True)
class MessageSpec:
    code: str
    name: str
    when: str
    category: str
    subject: str
    body: str
    variables: tuple[Variable, ...]
    required: frozenset[str] = frozenset()


HOSPITAL = Variable("hospital", "The hospital's name", "Sunrise Hospitals")
LINK = Variable("link", "The link to open", "https://hims.example/link")
PERSON = Variable("name", "The person's name", "Asha Verma")
PERIOD = Variable("period", "The dates", "12 Nov 2026 to 14 Nov 2026 (3 days)")
LEAVE_TYPE = Variable("leave_type", "The kind of leave", "annual leave")
COVER_PERIOD = Variable("period", "From and to", "from 12 Nov 2026 09:00 to 14 Nov 2026 17:00 IST")
COVER_REASON = Variable("reason", "Why cover is needed", "Annual leave")
COVER_ROLES = Variable("roles", "The access lent", "- Head of department (Cardiology)")
_OPEN_HIMS = "Open HIMS to see it (sign-in needed): {{link}}\n"


def _leave(code, name, when, subject, body, *variables, required=()):
    return MessageSpec(
        code=code,
        name=name,
        when=when,
        category="staff",
        subject=subject,
        body=f"{body}\n\n{_OPEN_HIMS}",
        variables=(*variables, HOSPITAL, LINK),
        required=frozenset(required),
    )


MESSAGES: tuple[MessageSpec, ...] = (
    MessageSpec(
        code="identity.invitation",
        name="Account invitation",
        when="Someone is given an account and must choose a password.",
        category="account",
        subject="Activate your {{hospital}} HIMS account",
        body=(
            "Hello {{name}},\n\n"
            "You have been invited to use the {{hospital}} hospital system (HIMS).\n"
            "Open this link to choose your password and activate your account:\n\n"
            "{{link}}\n\n"
            "The link can be used once and expires on {{expires}}.\n"
            "If you were not expecting this email, you can ignore it.\n"
        ),
        variables=(
            PERSON,
            HOSPITAL,
            Variable("link", "The activation link", "https://hims.example/activate"),
            Variable("expires", "When the link stops working", "16 Nov 2026, 10:00 IST"),
        ),
        required=frozenset({"link"}),
    ),
    MessageSpec(
        code="identity.password_reset",
        name="Password reset link",
        when="Someone asks to reset a forgotten password, or an administrator sends a reset link.",
        category="security",
        subject="Reset your {{hospital}} HIMS password",
        body=(
            "Hello {{name}},\n\n"
            "We received a request to reset the password of your {{hospital}} HIMS account.\n"
            "Open this link to choose a new password:\n\n"
            "{{link}}\n\n"
            "The link can be used once and expires in {{minutes}} minutes.\n"
            "If you did not ask for this, you can ignore this email; your password stays the "
            "same.\n"
        ),
        variables=(
            PERSON,
            HOSPITAL,
            Variable("link", "The reset link", "https://hims.example/reset-password"),
            Variable("minutes", "Minutes until the link stops working", "30"),
        ),
        required=frozenset({"link"}),
    ),
    MessageSpec(
        code="identity.password_changed",
        name="Password changed notice",
        when="A password has just been changed.",
        category="security",
        subject="Your {{hospital}} HIMS password was changed",
        body=(
            "Hello {{name}},\n\n"
            "The password of your {{hospital}} HIMS account was just changed, and all devices "
            "that were signed in have been signed out.\n\n"
            "If you did not do this, contact your hospital administrator immediately.\n"
        ),
        variables=(PERSON, HOSPITAL),
    ),
    MessageSpec(
        code="access.cover_starting",
        name="Cover: you are covering",
        when="Someone is arranged to cover for a colleague (sent to the person covering).",
        category="access",
        subject="HIMS: you are covering for {{colleague}}",
        body=(
            "You will work with {{colleague}}'s access {{period}}.\n\n"
            "Reason: {{reason}}\n\nAccess lent to you:\n{{roles}}\n\n"
            "Everything you do is recorded under your own name. The access ends by itself.\n"
        ),
        variables=(
            Variable("colleague", "The person being covered", "Asha Verma"),
            COVER_PERIOD,
            COVER_REASON,
            COVER_ROLES,
            HOSPITAL,
        ),
        required=frozenset({"colleague", "period"}),
    ),
    MessageSpec(
        code="access.cover_for_you",
        name="Cover: someone covers for you",
        when="Someone is arranged to cover for a colleague (sent to the person being covered).",
        category="access",
        subject="HIMS: {{colleague}} is covering for you",
        body=(
            "{{colleague}} will work with your access {{period}}.\n\n"
            "Reason: {{reason}}\n\nAccess lent:\n{{roles}}\n\n"
            "If you did not expect this, tell your hospital administrator.\n"
        ),
        variables=(
            Variable("colleague", "The person covering", "Ravi Kumar"),
            COVER_PERIOD,
            COVER_REASON,
            COVER_ROLES,
            HOSPITAL,
        ),
        required=frozenset({"colleague", "period"}),
    ),
    MessageSpec(
        code="access.cover_ended",
        name="Cover ended early",
        when="A cover arrangement is ended before its end date.",
        category="access",
        subject="HIMS: cover arrangement ended",
        body=("The cover by {{covering}} for {{covered}} ended early.\n\nReason: {{reason}}\n"),
        variables=(
            Variable("covering", "The person who was covering", "Ravi Kumar"),
            Variable("covered", "The person who was covered", "Asha Verma"),
            Variable("reason", "Why it ended", "Back early"),
            HOSPITAL,
        ),
    ),
    MessageSpec(
        code="access.review_overdue",
        name="Access review overdue",
        when="The access review in progress is past its finish date.",
        category="access",
        subject="{{hospital}}: the access review is overdue",
        body=(
            "The access review “{{title}}” was due to finish on {{due}}. "
            "{{pending}} item(s) still need a decision.\n\n"
            "Open HIMS → Access reviews to finish it.\n"
        ),
        variables=(
            Variable("title", "The review's title", "Quarterly review"),
            Variable("due", "The finish date", "12 Nov 2026"),
            Variable("pending", "How many items are left", "4"),
            HOSPITAL,
        ),
    ),
    MessageSpec(
        code="access.review_due",
        name="Access review due",
        when="It is time for the next periodic access review.",
        category="access",
        subject="{{hospital}}: a periodic access review is due",
        body=(
            "It is time to check who has access to HIMS and remove access people no longer "
            "need (due {{due}}; reviews are due every {{interval}} days).\n\n"
            "Open HIMS → Access reviews → Start a review.\n"
        ),
        variables=(
            Variable("due", "The date it is due", "12 Nov 2026"),
            Variable("interval", "Days between reviews", "90"),
            HOSPITAL,
        ),
    ),
    MessageSpec(
        code="audit.integrity_alert",
        name="Audit log integrity alert",
        when="The audit log check finds records changed or removed.",
        category="audit",
        subject="HIMS: audit log integrity check found problems",
        body=(
            "The audit log integrity check found {{count}} problem(s) on {{when}} UTC.\n\n"
            "This can mean that someone changed or removed audit records directly in the "
            "database.\nTreat it as a possible security incident: do not change anything, and "
            "follow the\nincident procedure.\n\n"
            "See the details (sign-in needed): {{link}}\n"
        ),
        variables=(
            Variable("count", "How many problems", "2"),
            Variable("when", "When the check finished", "2026-11-09 10:00"),
            Variable("link", "The check's page", "https://hims.example/audit/integrity/1"),
            HOSPITAL,
        ),
        required=frozenset({"link"}),
    ),
    MessageSpec(
        code="compliance.incident_reported",
        name="Security incident reported",
        when="A security incident is reported. The details stay behind the sign-in.",
        category="compliance",
        subject="HIMS: security incident reported",
        body=(
            "A security incident was reported ({{severity}} severity).\n\n"
            "{{deadlines}}\n\n"
            "See it here (sign-in needed): {{link}}\n"
        ),
        variables=(
            Variable("severity", "How serious it is", "High"),
            Variable("deadlines", "The legal deadlines, if any", "Deadlines:\n- 12 Nov 2026 10:00"),
            Variable("link", "The incident's page", "https://hims.example/compliance"),
            HOSPITAL,
        ),
        required=frozenset({"link"}),
    ),
    MessageSpec(
        code="compliance.incident_deadline",
        name="Incident deadline reminder",
        when="An incident's legal deadline is close or has passed.",
        category="compliance",
        subject="HIMS: {{what}} {{state}}",
        body=(
            "{{what}} {{state}} (deadline {{deadline}}).\n\n"
            "See the incident (sign-in needed): {{link}}\n"
        ),
        variables=(
            Variable("what", "What is due", "India: tell the Data Protection Board"),
            Variable("state", "How close it is", "is due within 24 hours"),
            Variable("deadline", "The deadline", "12 Nov 2026 10:00 IST"),
            Variable("link", "The incident's page", "https://hims.example/compliance"),
            HOSPITAL,
        ),
        required=frozenset({"link"}),
    ),
    _leave(
        "rosters.leave_requested",
        "Leave to decide",
        "Someone asks for leave (sent to whoever can approve it).",
        "Leave to decide: {{person}}, {{period}}",
        "{{person}} ({{department}}) has leave waiting for your decision:\n"
        "{{leave_type}}, {{period}}.\nGo to Leave in HIMS to approve or refuse it.",
        Variable("person", "Who asked", "Asha Verma"),
        Variable("department", "Their department", "Cardiology"),
        LEAVE_TYPE,
        PERIOD,
    ),
    _leave(
        "rosters.leave_approved",
        "Leave approved",
        "Leave is approved.",
        "Leave approved: {{period}}",
        "Your {{leave_type}} for {{period}} was approved.\n{{note}}",
        LEAVE_TYPE,
        PERIOD,
        Variable("note", "The approver's note, if any", "Note: Enjoy your break"),
    ),
    _leave(
        "rosters.leave_rejected",
        "Leave refused",
        "Leave is refused.",
        "Leave refused: {{period}}",
        "Your {{leave_type}} for {{period}} was refused.\nReason: {{reason}}",
        LEAVE_TYPE,
        PERIOD,
        Variable("reason", "Why it was refused", "Too few staff that week"),
        required=("reason",),
    ),
    _leave(
        "rosters.leave_withdrawn",
        "Leave withdrawn",
        "Someone withdraws their own leave (sent to whoever can approve it).",
        "Leave cancelled: {{person}}, {{period}}",
        "{{person}} withdrew their leave for {{period}}.",
        Variable("person", "Who withdrew it", "Asha Verma"),
        PERIOD,
    ),
    _leave(
        "rosters.leave_cancelled",
        "Leave cancelled",
        "Approved leave is cancelled by someone else (sent to the person).",
        "Leave cancelled: {{person}}, {{period}}",
        "Your {{leave_type}} for {{period}} was cancelled.\nReason: {{reason}}",
        Variable("person", "Whose leave it was", "Asha Verma"),
        LEAVE_TYPE,
        PERIOD,
        Variable("reason", "Why it was cancelled", "Emergency cover needed"),
        required=("reason",),
    ),
    MessageSpec(
        code="staff.licence_expiry_hr",
        name="Licences expiring (for HR)",
        when="Staff licences are expiring or have expired (daily summary to HR).",
        category="staff",
        subject="{{hospital}}: {{count}} licence(s) expiring or expired",
        body=(
            "These staff licences need attention (renewal or a new copy):\n\n"
            "{{licences}}\n\n"
            "See the Licence expiry page in HIMS for the full list.\n"
        ),
        variables=(
            Variable("count", "How many", "1"),
            Variable(
                "licences",
                "The list of licences",
                "- Asha Verma (E100): Medical licence MCI-1, MCI - expires on 12 Dec 2026",
            ),
            HOSPITAL,
        ),
        required=frozenset({"licences"}),
    ),
    MessageSpec(
        code="staff.licence_expiry_person",
        name="Your licence is expiring",
        when="A person's own licence is expiring or has expired.",
        category="staff",
        subject="{{hospital}}: your licence {{headline}}",
        body=(
            "Hello {{name}},\n\n"
            "Your {{licence}} ({{authority}}) {{state}} {{date}}.\n"
            "Please renew it and give a copy of the new licence to HR.\n"
        ),
        variables=(
            Variable("name", "The person's first name", "Asha"),
            Variable("licence", "The licence and its number", "Medical licence MCI-1"),
            Variable("authority", "Who issued it", "Medical Council"),
            Variable("state", '"expired on" or "expires on"', "expires on"),
            Variable("date", "The expiry date", "12 Dec 2026"),
            Variable("headline", '"has expired" or "expires soon"', "expires soon"),
            HOSPITAL,
        ),
        required=frozenset({"licence", "date"}),
    ),
)

BY_KEY: dict[str, MessageSpec] = {spec.code: spec for spec in MESSAGES}
