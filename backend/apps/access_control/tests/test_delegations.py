"""HIMS-IAM-017: cover arrangements / delegated access (spec 4.4 "delegated access", 13.2).

All people and data are synthetic.
"""

from datetime import timedelta

import pytest
from django.core import mail
from django.test import Client
from django.utils import timezone

from apps.access_control.catalog import P
from apps.access_control.models import AccessDelegation, AccessReviewItem, RoleAssignment
from apps.access_control.selectors import has_permission
from apps.access_control.services import revoke_role_assignment
from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.identity.accounts import active_administrators
from apps.identity.models import User

URL = "/api/v1/access-delegations/"


@pytest.fixture
def people(make_user, system_roles, facility_a, department_a):
    ravi = make_user(display_name="Ravi Covered", email="ravi@synthetic.test")
    hr = RoleAssignment.objects.create(
        organization_id=facility_a.organization_id,
        user=ravi,
        role=system_roles["hr-credentialing-officer"],
        facility=facility_a,
    )
    hod = RoleAssignment.objects.create(
        organization_id=facility_a.organization_id,
        user=ravi,
        role=system_roles["department-head"],
        facility=facility_a,
        department=department_a,
    )
    return {
        "ravi": ravi,
        "hr": hr,
        "hod": hod,
        "asha": make_user(
            role=system_roles["basic-staff"],
            display_name="Asha Cover",
            email="asha@synthetic.test",
        ),
        "auditor": make_user(role=system_roles["auditor"], display_name="Ann Auditor"),
    }


def fresh(user) -> User:
    return User.objects.get(pk=user.pk)  # permissions are cached per user object


def arrange(client, people, *, days=7, **extra):
    body = {
        "delegator": str(people["ravi"].pk),
        "delegate": str(people["asha"].pk),
        "ends_at": (timezone.now() + timedelta(days=days)).isoformat(),
        "reason": "Annual leave",
        **extra,
    }
    return client.post(URL, body, format="json")


@pytest.mark.django_db
def test_cover_lends_copies_of_the_access_for_a_time(
    client_for, admin_user, people, facility_a, django_capture_on_commit_callbacks
):
    asha = people["asha"]
    assert not has_permission(fresh(asha), P.STAFF_MANAGE, facility_id=facility_a.pk)
    with django_capture_on_commit_callbacks(execute=True):
        response = arrange(client_for(admin_user), people)
    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["status"] == "active"
    assert body["delegator"]["display_name"] == "Ravi Covered"
    assert body["delegate"]["display_name"] == "Asha Cover"
    assert sorted(a["role_name"] for a in body["lent_access"]) == sorted(
        [people["hr"].role.name, people["hod"].role.name]
    )
    assert body["skipped"] == []

    copies = RoleAssignment.objects.filter(user=asha, delegation_id=body["id"])
    assert {c.delegated_from_id for c in copies} == {people["hr"].pk, people["hod"].pk}
    assert all(c.valid_until.isoformat()[:16] == body["ends_at"][:16] for c in copies)
    assert has_permission(fresh(asha), P.STAFF_MANAGE, facility_id=facility_a.pk)

    assert AuditEvent.objects.filter(
        action=AuditAction.ACCESS_DELEGATION_CREATED, resource_id=body["id"]
    ).exists()
    assert (
        AuditEvent.objects.filter(
            action=AuditAction.ROLE_ASSIGNED, metadata__delegation_id=body["id"]
        ).count()
        == 2
    )
    subjects = sorted(m.subject for m in mail.outbox)
    assert subjects == [
        "HIMS: Asha Cover is covering for you",
        "HIMS: you are covering for Ravi Covered",
    ]


@pytest.mark.django_db
def test_only_some_roles_can_be_lent(client_for, admin_user, people):
    response = arrange(client_for(admin_user), people, assignments=[str(people["hr"].pk)])
    assert response.status_code == 201
    assert [a["role_name"] for a in response.json()["lent_access"]] == [people["hr"].role.name]


@pytest.mark.django_db
def test_cover_can_start_later(client_for, admin_user, people, facility_a):
    starts = timezone.now() + timedelta(days=2)
    response = arrange(client_for(admin_user), people, starts_at=starts.isoformat(), days=5)
    assert response.json()["status"] == "scheduled"
    assert not has_permission(fresh(people["asha"]), P.STAFF_MANAGE, facility_id=facility_a.pk)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"delegate": "ravi"}, "SAME_PERSON"),
        ({"delegate": "admin"}, "SELF_ASSIGNMENT"),
        ({"days": 31}, "TOO_LONG"),
        ({"starts_at": -1}, "START_IN_PAST"),
        ({"assignments": []}, "NOTHING_TO_DELEGATE"),
    ],
)
def test_unsafe_cover_is_refused(client_for, admin_user, people, change, code):
    extra = {}
    if change.get("delegate") == "ravi":
        extra["delegate"] = str(people["ravi"].pk)
    if change.get("delegate") == "admin":
        extra["delegate"] = str(admin_user.pk)
    if "starts_at" in change:
        extra["starts_at"] = (timezone.now() - timedelta(hours=1)).isoformat()
    if "assignments" in change:
        extra["assignments"] = change["assignments"]
    response = arrange(client_for(admin_user), people, days=change.get("days", 7), **extra)
    assert response.status_code == 409, response.json()
    assert response.json()["code"] == code
    assert not AccessDelegation.objects.exists()


@pytest.mark.django_db
def test_switched_off_people_and_overlaps_are_refused(client_for, admin_user, people):
    client = client_for(admin_user)
    assert arrange(client, people).status_code == 201
    assert arrange(client, people, days=3).json()["code"] == "OVERLAPPING"
    people["asha"].is_active = False
    people["asha"].save()
    other = arrange(client, people)
    assert other.json()["code"] in {"ACCOUNT_INACTIVE", "OVERLAPPING"}


@pytest.mark.django_db
def test_auditor_access_and_lent_access_are_never_lent(client_for, admin_user, people):
    client = client_for(admin_user)
    rows = client.get(URL + "delegable/", {"user": str(people["auditor"].pk)}).json()
    auditor_row = next(r for r in rows if r["role_name"].startswith("Auditor"))
    assert auditor_row["can_lend"] is False
    assert "independent" in auditor_row["why_not"]
    refused = arrange(
        client, people, delegator=str(people["auditor"].pk), assignments=[auditor_row["id"]]
    )
    assert refused.json()["code"] == "NOT_DELEGABLE"
    assert "independent" in refused.json()["detail"]
    # Asha holds Ravi's access only as cover: she cannot lend it on to someone else.
    assert arrange(client, people).status_code == 201
    copy = RoleAssignment.objects.filter(user=people["asha"], delegation__isnull=False).first()
    response = client.post(
        URL,
        {
            "delegator": str(people["asha"].pk),
            "delegate": str(people["auditor"].pk),
            "ends_at": (timezone.now() + timedelta(days=2)).isoformat(),
            "reason": "Chain",
            "assignments": [str(copy.pk)],
        },
        format="json",
    )
    assert response.json()["code"] == "NOT_DELEGABLE"


@pytest.mark.django_db
def test_auditor_only_person_has_nothing_to_lend(client_for, admin_user, people):
    response = arrange(
        client_for(admin_user),
        people,
        delegator=str(people["auditor"].pk),
    )
    assert response.json()["code"] == "NOTHING_TO_DELEGATE"


@pytest.mark.django_db
def test_people_without_access_management_cannot_arrange_cover(client_for, people):
    client = client_for(people["ravi"])
    assert arrange(client, people).status_code == 403
    assert client.get(URL).status_code == 403


@pytest.mark.django_db
def test_ending_early_removes_the_lent_access_at_once(
    client_for, admin_user, people, facility_a, django_capture_on_commit_callbacks
):
    client = client_for(admin_user)
    created = arrange(client, people).json()
    mail.outbox.clear()
    stale = client.post(
        f"{URL}{created['id']}/end/", {"version": 99, "reason": "Back early"}, format="json"
    )
    assert stale.status_code == 409
    with django_capture_on_commit_callbacks(execute=True):
        ended = client.post(
            f"{URL}{created['id']}/end/",
            {"version": created["version"], "reason": "Back early"},
            format="json",
        )
    assert ended.status_code == 200, ended.json()
    body = ended.json()
    assert body["status"] == "ended_early"
    assert body["end_reason"] == "Back early"
    assert all(a["revoked_at"] for a in body["lent_access"])
    assert not has_permission(fresh(people["asha"]), P.STAFF_MANAGE, facility_id=facility_a.pk)
    assert len(mail.outbox) == 1 and mail.outbox[0].subject == "HIMS: cover arrangement ended"
    assert AuditEvent.objects.filter(action=AuditAction.ACCESS_DELEGATION_ENDED).exists()
    again = client.post(
        f"{URL}{created['id']}/end/", {"version": body["version"], "reason": "x"}, format="json"
    )
    assert again.json()["code"] == "ALREADY_ENDED"
    # Ravi's own access is untouched.
    assert RoleAssignment.objects.get(pk=people["hr"].pk).revoked_at is None


@pytest.mark.django_db
def test_removing_the_original_access_ends_its_cover(client_for, admin_user, people):
    arrange(client_for(admin_user), people)
    revoke_role_assignment(actor=admin_user, assignment_id=people["hr"].pk, reason="Moved")
    copy = RoleAssignment.objects.get(delegated_from=people["hr"])
    assert copy.revoked_at is not None
    assert "covered person's own access ended" in copy.revocation_reason
    assert RoleAssignment.objects.get(delegated_from=people["hod"]).revoked_at is None


@pytest.mark.django_db
@pytest.mark.parametrize("who", ["ravi", "asha"])
def test_switching_off_either_account_ends_the_cover(client_for, admin_user, people, who):
    created = arrange(client_for(admin_user), people).json()
    person = people[who]
    person.is_active = False
    person.save()
    delegation = AccessDelegation.objects.get(pk=created["id"])
    assert delegation.status == AccessDelegation.Status.ENDED_EARLY
    assert "account was switched off" in delegation.end_reason
    assert not delegation.assignments.filter(revoked_at__isnull=True).exists()


@pytest.mark.django_db
def test_lent_administrator_access_never_counts_as_an_administrator(
    client_for, admin_user, make_user, system_roles, people
):
    second = make_user(role=system_roles["organization-administrator"], display_name="Second")
    response = client_for(admin_user).post(
        URL,
        {
            "delegator": str(second.pk),
            "delegate": str(people["asha"].pk),
            "ends_at": (timezone.now() + timedelta(days=3)).isoformat(),
            "reason": "Cover while away",
        },
        format="json",
    )
    assert response.status_code == 201, response.json()
    assert people["asha"] not in active_administrators()
    assert has_permission(fresh(people["asha"]), P.ORGANIZATION_MANAGE)


@pytest.mark.django_db
def test_an_earlier_finished_cover_does_not_block_a_new_one(client_for, admin_user, people):
    client = client_for(admin_user)
    first = arrange(client, people).json()
    # Make the first cover lie in the past (as if it ran out last month).
    past = timezone.now() - timedelta(days=30)
    AccessDelegation.objects.filter(pk=first["id"]).update(
        starts_at=past, ends_at=past + timedelta(days=5)
    )
    RoleAssignment.objects.filter(delegation_id=first["id"]).update(
        valid_from=past, valid_until=past + timedelta(days=5)
    )
    second = arrange(client, people)
    assert second.status_code == 201, second.json()
    old = RoleAssignment.objects.filter(delegation_id=first["id"])
    assert all(a.revoked_at is not None for a in old)


@pytest.mark.django_db
def test_lists_filters_and_my_cover(client_for, admin_user, people, make_user):
    client = client_for(admin_user)
    created = arrange(client, people).json()
    assert [d["id"] for d in client.get(URL).json()] == [created["id"]]
    assert client.get(URL, {"status": "past"}).json() == []
    assert client.get(URL, {"person": str(people["asha"].pk)}).json()[0]["id"] == created["id"]
    assert client.get(URL, {"person": "not-an-id"}).status_code == 400
    assert client.get(URL, {"status": "nonsense"}).status_code == 400
    assert client.get(f"{URL}{created['id']}/").json()["reason"] == "Annual leave"

    mine = client_for(people["asha"]).get("/api/v1/my-delegations/").json()
    assert [d["id"] for d in mine] == [created["id"]]
    assert client_for(make_user()).get("/api/v1/my-delegations/").json() == []

    rows = client.get("/api/v1/role-assignments/", {"user": str(people["asha"].pk)}).json()
    lent = [r for r in rows["results"] if r["delegation"]]
    assert {r["covering_for_name"] for r in lent} == {"Ravi Covered"}


@pytest.mark.django_db
def test_access_reviews_show_lent_access_as_cover(client_for, admin_user, people):
    arrange(client_for(admin_user), people)
    response = client_for(admin_user).post(
        "/api/v1/access-reviews/", {"title": "Q4 review"}, format="json"
    )
    assert response.status_code == 201
    names = AccessReviewItem.objects.filter(person_email="asha@synthetic.test").values_list(
        "role_name", flat=True
    )
    assert any("(cover for Ravi Covered until" in name for name in names)


@pytest.mark.django_db
def test_admin_console_arranges_and_ends_cover(admin_user, people):
    console = Client()
    console.force_login(admin_user)
    start = timezone.localtime(timezone.now() + timedelta(minutes=1))
    end = start + timedelta(days=3)
    page = console.post(
        "/admin/access_control/accessdelegation/add/",
        {
            "delegator": str(people["ravi"].pk),
            "delegate": str(people["asha"].pk),
            "starts_at_0": start.strftime("%Y-%m-%d"),
            "starts_at_1": start.strftime("%H:%M:%S"),
            "ends_at_0": end.strftime("%Y-%m-%d"),
            "ends_at_1": end.strftime("%H:%M:%S"),
            "reason": "Conference",
        },
    )
    assert page.status_code == 302, page.content[:2000]
    delegation = AccessDelegation.objects.get()
    assert delegation.created_by == admin_user
    assert delegation.assignments.count() == 2

    refused = console.post(
        "/admin/access_control/accessdelegation/add/",
        {
            "delegator": str(people["ravi"].pk),
            "delegate": str(people["ravi"].pk),
            "starts_at_0": start.strftime("%Y-%m-%d"),
            "starts_at_1": start.strftime("%H:%M:%S"),
            "ends_at_0": end.strftime("%Y-%m-%d"),
            "ends_at_1": end.strftime("%H:%M:%S"),
            "reason": "Same person",
        },
    )
    assert refused.status_code == 200
    assert b"Choose two different people." in refused.content

    console.post(
        "/admin/access_control/accessdelegation/",
        {"action": "end_selected", "_selected_action": [str(delegation.pk)]},
    )
    delegation.refresh_from_db()
    assert delegation.ended_by == admin_user
    assert (
        console.get(f"/admin/access_control/accessdelegation/{delegation.pk}/change/").status_code
        == 200
    )
