"""HIMS-IAM-012: periodic access reviews (spec 4.4, 13.2 "periodic permission review")."""

import csv
import io
from datetime import timedelta

import pytest
from django.core import mail
from django.test import Client, override_settings
from django.utils import timezone

from apps.access_control.models import (
    AccessReview,
    AccessReviewItem,
    AccessReviewReminder,
    RoleAssignment,
)
from apps.access_control.reviews import schedule, send_access_review_reminders
from apps.access_control.selectors import has_permission
from apps.access_control.services import revoke_role_assignment
from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction

URL = "/api/v1/access-reviews/"


@pytest.fixture
def people(make_user, system_roles, facility_a, department_a):
    """A second administrator (so the reviewer is never alone), an HR officer at one branch and
    a head of department."""
    return {
        "admin2": make_user(
            role=system_roles["organization-administrator"], display_name="Second Admin"
        ),
        "hr": make_user(
            role=system_roles["hr-credentialing-officer"],
            facility=facility_a,
            display_name="Hana HR",
        ),
        "hod": make_user(
            role=system_roles["department-head"],
            facility=facility_a,
            department=department_a,
            display_name="Harish HOD",
        ),
    }


def start(client, title="Q4 2026 access review", **extra):
    return client.post(URL, {"title": title, **extra}, format="json")


def items_of(client, review_id, **params):
    return client.get(f"{URL}{review_id}/items/", params).json()


@pytest.mark.django_db
def test_start_takes_a_snapshot_of_everyones_current_access(
    client_for, admin_user, people, facility_a
):
    expired = RoleAssignment.objects.get(user=people["hod"])
    response = start(client_for(admin_user))
    assert response.status_code == 201, response.content
    review = response.json()
    assert review["status"] == "open"
    assert review["due_on"] == (timezone.localdate() + timedelta(days=14)).isoformat()
    assert (
        review["summary"]["pending"]
        == RoleAssignment.objects.filter(revoked_at__isnull=True).count()
    )

    rows = items_of(client_for(admin_user), review["id"])
    by_person = {r["person_name"]: r for r in rows}
    assert by_person["Hana HR"]["scope"] == facility_a.name
    assert by_person["Hana HR"]["role_name"] == "HR / credentialing officer"
    assert by_person["Harish HOD"]["scope"] == f"{facility_a.name} / Cardiology"
    assert by_person["Second Admin"]["scope"] == "Whole hospital"
    assert [r["is_own"] for r in rows if r["person_email"] == admin_user.email] == [True]
    assert expired.pk  # snapshot rows point at the real assignments

    event = AuditEvent.objects.get(action=AuditAction.ACCESS_REVIEW_STARTED)
    assert event.metadata["items"] == len(rows)


@pytest.mark.django_db
def test_only_one_review_at_a_time_and_due_date_not_in_the_past(client_for, admin_user):
    client = client_for(admin_user)
    yesterday = (timezone.localdate() - timedelta(days=1)).isoformat()
    assert start(client, due_on=yesterday).json()["code"] == "DUE_DATE_PAST"
    assert start(client).status_code == 201
    second = start(client, title="Another")
    assert second.status_code == 409
    assert second.json()["code"] == "REVIEW_ALREADY_OPEN"


@pytest.mark.django_db
def test_remove_ends_access_at_once_and_needs_a_reason(client_for, admin_user, people, facility_a):
    client = client_for(admin_user)
    review = start(client).json()
    hr_item = items_of(client, review["id"], search="Hana")[0]
    assert has_permission(people["hr"], "staff.manage", facility_id=facility_a.pk)

    no_reason = client.post(
        f"{URL}{review['id']}/decide/",
        {"items": [hr_item["id"]], "decision": "remove"},
        format="json",
    )
    assert no_reason.status_code == 400

    response = client.post(
        f"{URL}{review['id']}/decide/",
        {"items": [hr_item["id"]], "decision": "remove", "comment": "Moved to another hospital"},
        format="json",
    )
    assert response.status_code == 200, response.content
    assert response.json()[0]["decision"] == "remove"
    assignment = RoleAssignment.objects.get(user=people["hr"])
    assert assignment.revoked_at is not None
    assert assignment.revoked_by == admin_user
    assert "Moved to another hospital" in assignment.revocation_reason
    fresh = type(people["hr"]).objects.get(pk=people["hr"].pk)  # as on the next request
    assert not has_permission(fresh, "staff.manage", facility_id=facility_a.pk)
    assert AuditEvent.objects.filter(action=AuditAction.ROLE_REVOKED).exists()
    decided = AuditEvent.objects.get(action=AuditAction.ACCESS_REVIEW_DECIDED)
    assert decided.metadata["removed"] == 1


@pytest.mark.django_db
def test_nobody_reviews_their_own_access(client_for, admin_user, people):
    client = client_for(admin_user)
    review = start(client).json()
    own = [r for r in items_of(client, review["id"]) if r["is_own"]]
    response = client.post(
        f"{URL}{review['id']}/decide/",
        {"items": [own[0]["id"]], "decision": "keep"},
        format="json",
    )
    assert response.status_code == 409
    assert response.json()["code"] == "SELF_REVIEW"
    # ...but another administrator can.
    response = client_for(people["admin2"]).post(
        f"{URL}{review['id']}/decide/",
        {"items": [own[0]["id"]], "decision": "keep"},
        format="json",
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_complete_needs_every_item_decided_then_it_is_locked(client_for, admin_user, people):
    client, other = client_for(admin_user), client_for(people["admin2"])
    review = start(client).json()
    rows = items_of(client, review["id"])
    own_ids = [r["id"] for r in rows if r["is_own"]]
    rest = [r["id"] for r in rows if not r["is_own"]]

    early = client.post(f"{URL}{review['id']}/complete/", {"version": 1}, format="json")
    assert early.status_code == 409
    assert early.json()["code"] == "REVIEW_NOT_FINISHED"

    assert (
        client.post(
            f"{URL}{review['id']}/decide/", {"items": rest, "decision": "keep"}, format="json"
        ).status_code
        == 200
    )
    assert (
        other.post(
            f"{URL}{review['id']}/decide/", {"items": own_ids, "decision": "keep"}, format="json"
        ).status_code
        == 200
    )
    current = client.get(f"{URL}{review['id']}/").json()
    stale = client.post(f"{URL}{review['id']}/complete/", {"version": 1}, format="json")
    assert stale.status_code == 409  # someone decided since version 1 was loaded

    done = client.post(
        f"{URL}{review['id']}/complete/",
        {"version": current["version"], "notes": "All confirmed"},
        format="json",
    )
    assert done.status_code == 200, done.content
    assert done.json()["status"] == "completed"
    assert done.json()["summary"]["keep"] == len(rows)

    locked = client.post(
        f"{URL}{review['id']}/decide/", {"items": rest[:1], "decision": "keep"}, format="json"
    )
    assert locked.status_code == 409
    assert locked.json()["code"] == "REVIEW_CLOSED"
    assert schedule()["last_completed_at"] is not None


@pytest.mark.django_db
def test_access_that_ended_elsewhere_is_marked_and_does_not_block(client_for, admin_user, people):
    client = client_for(admin_user)
    review = start(client).json()
    hod = RoleAssignment.objects.get(user=people["hod"])
    revoke_role_assignment(actor=None, assignment_id=hod.pk, reason="Left")

    item = items_of(client, review["id"], search="Harish")[0]
    response = client.post(
        f"{URL}{review['id']}/decide/",
        {"items": [item["id"]], "decision": "keep"},
        format="json",
    )
    assert response.json()[0]["decision"] == "ended"


@pytest.mark.django_db
def test_cancel_needs_a_reason_and_keeps_decisions(client_for, admin_user, people):
    client = client_for(admin_user)
    review = start(client).json()
    hr_item = items_of(client, review["id"], search="Hana")[0]
    client.post(
        f"{URL}{review['id']}/decide/",
        {"items": [hr_item["id"]], "decision": "remove", "comment": "Not needed"},
        format="json",
    )
    version = client.get(f"{URL}{review['id']}/").json()["version"]
    assert (
        client.post(f"{URL}{review['id']}/cancel/", {"version": version}, format="json").status_code
        == 400
    )
    response = client.post(
        f"{URL}{review['id']}/cancel/",
        {"version": version, "reason": "Started by mistake"},
        format="json",
    )
    assert response.json()["status"] == "cancelled"
    assert AccessReviewItem.objects.get(pk=hr_item["id"]).decision == "remove"
    assert start(client, title="Proper review").status_code == 201


@pytest.mark.django_db
def test_auditor_can_read_and_download_but_not_decide(client_for, admin_user, auditor_user, people):
    review = start(client_for(admin_user)).json()
    auditor = client_for(auditor_user)
    assert auditor.get(URL).status_code == 200
    rows = items_of(auditor, review["id"])
    assert rows
    assert start(auditor).status_code == 403
    assert (
        auditor.post(
            f"{URL}{review['id']}/decide/",
            {"items": [rows[0]["id"]], "decision": "keep"},
            format="json",
        ).status_code
        == 403
    )

    response = auditor.get(f"{URL}{review['id']}/export/")
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")
    lines = list(csv.reader(io.StringIO(response.content.decode())))
    assert lines[0][:3] == ["Review", "Review status", "Person"]
    assert len(lines) == len(rows) + 1
    assert AuditEvent.objects.filter(action=AuditAction.ACCESS_REVIEW_EXPORTED).exists()


@pytest.mark.django_db
def test_people_without_review_permissions_see_nothing(client_for, people):
    client = client_for(people["hr"])
    assert client.get(URL).status_code == 403
    assert client.get(f"{URL}schedule/").status_code == 403


@pytest.mark.django_db
@override_settings(HIMS_ACCESS_REVIEW_INTERVAL_DAYS=90)
def test_reminders_are_sent_once_when_due_and_when_overdue(admin_user, people, organization):
    today = timezone.localdate()
    plan = schedule(today)
    assert plan["next_due_on"] == timezone.localdate(organization.created_at) + timedelta(days=90)
    assert send_access_review_reminders(today) == 0  # not due yet

    later = today + timedelta(days=91)
    assert send_access_review_reminders(later) == 1
    assert send_access_review_reminders(later) == 0  # once only
    assert len(mail.outbox) == 1
    assert set(mail.outbox[0].to) == {admin_user.email, people["admin2"].email}
    assert "access review is due" in mail.outbox[0].subject

    from apps.access_control.reviews import start_review

    review = start_review(actor=admin_user, organization=organization, title="Late review")
    assert send_access_review_reminders(review.due_on) == 0  # due today: not overdue yet
    overdue_day = review.due_on + timedelta(days=1)
    assert send_access_review_reminders(overdue_day) == 1
    assert send_access_review_reminders(overdue_day) == 0
    assert "overdue" in mail.outbox[-1].subject
    assert AccessReviewReminder.objects.count() == 2
    assert AuditEvent.objects.filter(action=AuditAction.ACCESS_REVIEW_REMINDER_SENT).count() == 2


@pytest.mark.django_db
def test_admin_console_starts_and_decides_with_the_same_rules(admin_user, people):
    console = Client()
    console.force_login(admin_user)
    response = console.post(
        "/admin/access_control/accessreview/add/",
        {"title": "Console review", "due_on": (timezone.localdate() + timedelta(days=7))},
    )
    assert response.status_code == 302, response.content[:2000]
    review = AccessReview.objects.get()
    assert review.items.count() == RoleAssignment.objects.filter(revoked_at__isnull=True).count()

    again = console.post(
        "/admin/access_control/accessreview/add/",
        {"title": "Second", "due_on": (timezone.localdate() + timedelta(days=7))},
    )
    assert again.status_code == 200  # form shown again with the error
    assert b"already in progress" in again.content

    hr_item = review.items.get(person_name="Hana HR")
    own_item = review.items.get(person_email=admin_user.email)
    console.post(
        "/admin/access_control/accessreviewitem/",
        {"action": "remove_selected", "_selected_action": [str(hr_item.pk)]},
    )
    hr_item.refresh_from_db()
    assert hr_item.decision == "remove"
    assert RoleAssignment.objects.get(user=people["hr"]).revoked_at is not None

    console.post(
        "/admin/access_control/accessreviewitem/",
        {"action": "keep_selected", "_selected_action": [str(own_item.pk)]},
    )
    own_item.refresh_from_db()
    assert own_item.decision == "pending"  # own access refused, same as the app


@pytest.mark.django_db
def test_auditor_role_includes_review_evidence(system_roles):
    codes = set(system_roles["auditor"].permissions.values_list("codename", flat=True))
    assert codes == {"audit.view", "access.reviews.view"}
    admin_codes = set(
        system_roles["organization-administrator"].permissions.values_list("codename", flat=True)
    )
    assert {"access.reviews.view", "access.reviews.manage"} <= admin_codes


@pytest.mark.django_db
def test_last_administrator_role_cannot_be_removed(client_for, make_user, system_roles):
    """Someone with access-management rights (but not an administrator) cannot remove the
    hospital's only administrator role, on the Access page or in a review."""
    only_admin = make_user(role=system_roles["organization-administrator"])
    from apps.access_control.services import create_role
    from apps.organizations.selectors import get_deployment_organization

    manager_role = create_role(
        actor=None,
        organization=get_deployment_organization(),
        code="access-manager",
        name="Access manager",
        permissions=[
            "access.roles.view",
            "access.assignments.manage",
            "access.reviews.view",
            "access.reviews.manage",
        ],
    )
    manager = make_user(role=manager_role)
    grant = RoleAssignment.objects.get(user=only_admin)
    client = client_for(manager)
    response = client.post(
        f"/api/v1/role-assignments/{grant.pk}/revoke/", {"reason": "test"}, format="json"
    )
    assert response.status_code == 409
    assert response.json()["code"] == "LAST_ADMINISTRATOR"

    review = start(client).json()
    item = next(i for i in items_of(client, review["id"]) if i["person_email"] == only_admin.email)
    response = client.post(
        f"{URL}{review['id']}/decide/",
        {"items": [item["id"]], "decision": "remove", "comment": "test"},
        format="json",
    )
    assert response.status_code == 409
    assert response.json()["code"] == "LAST_ADMINISTRATOR"
    grant.refresh_from_db()
    assert grant.revoked_at is None
    assert AccessReviewItem.objects.get(pk=item["id"]).decision == "pending"
