"""Index check, response times and synthetic volume (HIMS-DATA-002, HIMS-OPS-017).

Synthetic data only. The test database is small, so the index check takes its "small table" path:
each query must still pick its index once full reads are ruled out, which is what keeps the
indexes from being dropped or forgotten.
"""

import json
import re
from pathlib import Path

import pytest
from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.db import DatabaseError, connection, transaction

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.identity.models import User
from apps.performance import plans, services, timings, volume
from apps.performance.models import PerformanceCheck
from apps.performance.queries import QUERIES

CHECKS = "/api/v1/performance-checks/"
STATUS = "/api/v1/performance-checks/status/"
README = Path(settings.BASE_DIR).parent / "docs/architecture/data-architecture/README.md"


@pytest.fixture(autouse=True)
def _clear_throttles():
    cache.clear()


@pytest.fixture
def seeded(organization, system_roles):
    """A few hundred synthetic rows in every high-volume table."""
    return volume.seed(scale=0.0005)


# --- Index check (HIMS-DATA-002) -------------------------------------------------------------


def test_every_high_volume_query_has_its_index(seeded):
    results, rows = plans.run_index_check()
    failed = {item["key"]: item["detail"] for item in results if not item["passed"]}
    assert failed == {}
    assert {item["key"] for item in results} == {check.key for check in QUERIES}
    assert rows["audit_events"] > 0


def test_each_expected_index_exists_and_is_documented(db):
    with connection.cursor() as cursor:
        cursor.execute("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
        existing = {name for (name,) in cursor.fetchall()}
    documented = README.read_text(encoding="utf-8")
    for check in QUERIES:
        assert any(
            any(name.startswith(wanted) for name in existing)
            if wanted.endswith("_")
            else wanted in existing
            for wanted in check.indexes
        ), f"{check.key}: none of {check.indexes} exists"
        assert check.indexes[0] in documented or check.indexes[0].endswith("_"), (
            f"{check.key}: add {check.indexes[0]} to section 4 of the data architecture README"
        )


def test_a_missing_index_is_reported(seeded):
    from apps.performance.queries import QueryCheck

    wrong = QueryCheck(
        "wrong",
        "Messages by a made-up index",
        "notifications",
        ("no_such_idx",),
        QUERIES[9].build,
    )
    results, _ = plans.run_index_check((wrong,))
    assert results[0]["passed"] is False
    assert "No index serves this query" in results[0]["detail"]


def test_a_broken_query_is_reported_and_the_others_still_run(seeded):
    from apps.performance.queries import QueryCheck

    def broken(samples):
        raise DatabaseError("synthetic")

    bad = QueryCheck("bad", "Broken", "notifications", ("x",), broken)
    results, _ = plans.run_index_check((bad, QUERIES[0]))
    assert results[0]["passed"] is False
    assert results[0]["detail"].startswith("Could not be checked")
    assert results[1]["passed"] is True


def test_a_large_table_read_whole_fails(seeded, monkeypatch):
    monkeypatch.setattr(plans, "SMALL_TABLE_ROWS", 0)
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL enable_indexscan = off")
            cursor.execute("SET LOCAL enable_bitmapscan = off")
        results, _ = plans.run_index_check((QUERIES[1],))
    assert results[0]["passed"] is False
    assert "without the expected index" in results[0]["detail"]


# --- Recording, API and permissions ----------------------------------------------------------


def test_run_index_check_from_the_api_is_recorded_and_audited(client_for, admin_user, seeded):
    response = client_for(admin_user).post(CHECKS, {}, format="json")
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["kind"] == "indexes"
    assert body["outcome"] == "passed"
    assert body["requested_by_name"] == admin_user.display_name
    assert len(body["query_results"]) == len(QUERIES)
    assert body["screen_results"] == []
    assert body["dataset"]["audit_events"] > 0
    event = AuditEvent.objects.get(action=AuditAction.PERFORMANCE_CHECK_RUN)
    assert event.actor_id == admin_user.pk
    assert event.metadata["kind"] == "indexes"

    listed = client_for(admin_user).get(CHECKS).json()
    assert [row["id"] for row in listed] == [body["id"]]
    status = client_for(admin_user).get(STATUS).json()
    assert status["last_index_check"]["id"] == body["id"]
    assert status["last_volume_index_check"] is None
    assert status["page_target_ms"] == 300
    assert status["search_target_ms"] == 500
    assert status["can_measure_here"] is True
    detail = client_for(admin_user).get(f"{CHECKS}{body['id']}/").json()
    assert detail["query_results"][0]["key"] == QUERIES[0].key


def test_viewing_and_running_need_their_permissions(client_for, make_user, auditor_user, db):
    nobody = make_user()
    assert client_for(nobody).get(CHECKS).status_code == 403
    assert client_for(auditor_user).get(STATUS).status_code == 403
    assert client_for(auditor_user).post(CHECKS, {}, format="json").status_code == 403
    assert client_for().get(CHECKS).status_code in (401, 403)


def test_one_check_at_a_time(db):
    """While another connection runs a check, a second one is refused with "already running"."""
    from apps.recovery.pg_tools import connect
    from common.exceptions import ConflictError

    with connect(dict(connection.settings_dict)) as other:
        other.execute("SELECT pg_advisory_lock(%s)", [services._CHECK_LOCK])
        with pytest.raises(ConflictError, match="already running"), services._OneAtATime():
            pass
        other.execute("SELECT pg_advisory_unlock(%s)", [services._CHECK_LOCK])
    with services._OneAtATime():
        pass


def test_results_cannot_be_changed(admin_user, seeded):
    check = services.run_index_check(trigger=PerformanceCheck.Trigger.COMMAND)
    with pytest.raises(RuntimeError):
        check.save()
    with pytest.raises(DatabaseError), transaction.atomic():
        PerformanceCheck.objects.filter(pk=check.pk).update(summary="changed")
    with pytest.raises(DatabaseError), transaction.atomic():
        PerformanceCheck.objects.filter(pk=check.pk).delete()


# --- Response times (HIMS-OPS-017) -------------------------------------------------------------


def test_response_times_are_measured_and_nothing_is_left_behind(seeded):
    users_before = User.objects.count()
    events_before = AuditEvent.objects.count()
    results = timings.measure(samples=3)
    assert {item["key"] for item in results} == {e.key for e in timings.all_endpoints()}
    assert any(item["key"].startswith("console_") for item in results)  # console lists too
    not_ok = {
        item["key"]: (item["status"], item["detail"]) for item in results if item["status"] != 200
    }
    assert not_ok == {}
    for item in results:
        assert item["p50_ms"] <= item["p95_ms"] <= item["max_ms"]
        assert item["queries"] > 0
        assert item["target_ms"] in (timings.PAGE_MS, timings.SEARCH_MS)
    assert User.objects.count() == users_before
    assert not User.objects.filter(email="performance.measure@synthetic.test").exists()
    assert AuditEvent.objects.count() == events_before


def test_queries_per_screen_do_not_grow_with_the_records(organization, system_roles):
    """No screen makes one extra query per row (the "N+1" mistake that slows lists down)."""
    volume.seed(scale=0.0005)
    small = {item["key"]: item["queries"] for item in timings.measure(samples=3)}
    volume.seed(scale=0.002)
    large = {item["key"]: item["queries"] for item in timings.measure(samples=3)}
    grew = {key: (small[key], large[key]) for key in small if large[key] > small[key]}
    assert grew == {}


def test_a_slow_screen_misses_its_target(seeded, monkeypatch):
    fast = timings.Endpoint("me", "Who am I", lambda s: "/api/v1/auth/me/", target_ms=0.001)
    (result,) = timings.measure(samples=3, endpoints=(fast,))
    assert result["passed"] is False
    assert "over the" in result["detail"]


def test_percentile_is_nearest_rank():
    values = [float(n) for n in range(1, 21)]
    assert timings.percentile(values, 0.95) == 19.0
    assert timings.percentile(values, 0.5) == 10.0
    assert timings.percentile([5.0], 0.95) == 5.0


def test_response_times_only_on_a_developer_pc(settings, db):
    settings.HIMS_ENVIRONMENT = "production"
    with pytest.raises(services.PerformanceError):
        services.run_response_times(trigger=PerformanceCheck.Trigger.COMMAND)
    with pytest.raises(services.PerformanceError):
        services.run_volume_check(say=lambda message: None)


# --- Synthetic volume ----------------------------------------------------------------------------


def test_volume_fills_every_high_volume_table(seeded):
    for table in ("audit_events", "user_sessions", "notifications", "outbox_events", "shifts"):
        assert seeded[table] > 0
    assert User.objects.filter(email__endswith="@synthetic.test").count() >= 1
    assert (
        not User.objects.filter(email__endswith="@synthetic.test")
        .exclude(email__regex=r"^(staff\d{6}|user\d+)@synthetic\.test$")
        .exclude(email__startswith="user")
        .exists()
    )


def test_volume_refuses_a_real_hospital_database(settings, db, monkeypatch):
    with pytest.raises(volume.VolumeError, match="only into 'hims_volume'"):
        volume.check_safe("hims")
    volume.check_safe("hims_volume")
    settings.HIMS_ENVIRONMENT = "staging"
    with pytest.raises(volume.VolumeError, match="not local or test"):
        volume.check_safe("hims_volume")


def test_a_required_column_without_a_default_is_named(db):
    from apps.notifications.models import Notification

    field = Notification._meta.get_field("created_at")
    with pytest.raises(volume.VolumeError, match="has no column"):
        volume.insert_series(Notification, 1, {"no_such_column": "1"})
    assert volume._default_sql(field) == "now()"


# --- Commands -------------------------------------------------------------------------------------


def test_check_query_plans_command_writes_json(seeded, tmp_path):
    target = tmp_path / "plans.json"
    # Plan quality is test_every_high_volume_query_has_its_index's job; this checks the file.
    call_command("check_query_plans", f"--json={target}", "--no-fail")
    data = json.loads(target.read_text(encoding="utf-8"))
    assert len(data["results"]) == len(QUERIES)
    assert data["dataset"]["audit_events"] > 0
    assert not PerformanceCheck.objects.exists()  # --json writes the file instead of keeping it


def test_commands_keep_their_results(seeded, capsys):
    call_command("check_query_plans", "--no-fail")
    call_command("measure_response_times", "--samples=3", "--no-fail")
    kinds = set(PerformanceCheck.objects.values_list("kind", flat=True))
    assert kinds == {"indexes", "response_times"}
    out = capsys.readouterr().out
    assert re.search(r"(ok  |FAIL) Audit log: one person's actions: [\d.]+ ms", out)
    assert re.search(r"p95 \d+ ms", out)


def test_seed_command_refuses_this_database(db):
    from django.core.management.base import CommandError

    with pytest.raises(CommandError, match="--scale"):
        call_command("seed_volume_data", "--scale=0")
