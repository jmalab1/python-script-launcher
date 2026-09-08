import time

import pytest

import launcher.api.profiles as profiles_api
import launcher.api.schedules as schedules_api
import launcher.api.runs as runs
import launcher.api.workflows as workflows_api
from launcher.storage import load_audit


@pytest.fixture
def profile_env(store, tmp_path):
    script = tmp_path / "job.py"
    script.write_text("print('ok')\n")
    store.seed("profiles", [
        {"id": "p1", "name": "Job", "script_path": str(script), "args": [], "custom_args": []},
        {"id": "p2", "name": "Trashed", "script_path": str(script), "args": [], "custom_args": [], "group": "__trash__"},
    ])
    store.seed("workflows", [
        {"id": "w1", "name": "Nightly", "steps": []},
    ])
    return script


def wait_done(run_id, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        info = runs.handle_poll(run_id)
        if info and info["status"] in ("completed", "failed"):
            return info
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} did not finish in time")


@pytest.fixture
def sched_state(monkeypatch):
    import launcher.scheduler as scheduler
    monkeypatch.setattr(scheduler, "_last_scheduled_run", {})
    yield


def make_data(**over):
    data = {
        "name": "Hourly job",
        "target_type": "profile",
        "target_id": "p1",
        "cron": "0 * * * *",
        "enabled": True,
    }
    data.update(over)
    return data


# -------------------------------------------------------------------- create


def test_create_returns_schedule_with_computed_next_run(store, profile_env):
    sched, error = schedules_api.handle_create(make_data())
    assert error is None
    assert sched["id"].startswith("sched_")
    assert sched["enabled"] is True
    assert sched["next_run_at"] > 0
    assert store.read("schedules")[0]["cron"] == "0 * * * *"


def test_list_enriches_with_target_name_and_description(store, profile_env):
    schedules_api.handle_create(make_data())
    listed = schedules_api.handle_list()
    assert listed[0]["target_name"] == "Job"
    assert listed[0]["description"] == "Every hour"
    assert listed[0]["target_trashed"] is False
    assert listed[0]["cron"] == "0 * * * *"


def test_create_rejects_invalid_cron(store, profile_env):
    sched, error = schedules_api.handle_create(make_data(cron="99 * * * *"))
    assert sched is None
    assert "Invalid cron" in error["error"]
    assert store.read("schedules") == []


def test_create_rejects_unknown_target(store, profile_env):
    _, error = schedules_api.handle_create(make_data(target_id="ghost"))
    assert "Target not found" in error["error"]


def test_create_rejects_trashed_target(store, profile_env):
    _, error = schedules_api.handle_create(make_data(target_id="p2"))
    assert "trash" in error["error"]


def test_create_rejects_unknown_target_type(store, profile_env):
    _, error = schedules_api.handle_create(make_data(target_type="banana"))
    assert error


def test_create_records_audit_entry(store, profile_env):
    sched, _ = schedules_api.handle_create(make_data())
    entry = load_audit()[-1]
    assert entry["action"] == "created"
    assert entry["entity_type"] == "schedule"
    assert entry["entity_id"] == sched["id"]
    assert entry["name"] == "Hourly job"


def test_disabled_schedule_has_no_next_run(store, profile_env):
    sched, _ = schedules_api.handle_create(make_data(enabled=False))
    assert sched["next_run_at"] is None


# -------------------------------------------------------------------- update


def test_update_keeps_next_run_when_cron_unchanged(store, profile_env):
    sched, _ = schedules_api.handle_create(make_data())
    first_next = sched["next_run_at"]
    updated, error = schedules_api.handle_create(make_data(id=sched["id"], name="Renamed"))
    assert error is None
    assert updated["name"] == "Renamed"
    assert updated["next_run_at"] == first_next
    assert len(store.read("schedules")) == 1


def test_update_recomputes_next_run_when_cron_changes(store, profile_env):
    sched, _ = schedules_api.handle_create(make_data(cron="* * * * *"))
    updated, _ = schedules_api.handle_create(make_data(id=sched["id"], cron="0 0 1 1 *"))
    assert updated["next_run_at"] != sched["next_run_at"]
    assert len(store.read("schedules")) == 1


def test_update_records_audit_with_changed_fields(store, profile_env):
    sched, _ = schedules_api.handle_create(make_data())
    schedules_api.handle_create(make_data(id=sched["id"], name="Renamed"))
    entry = load_audit()[-1]
    assert entry["action"] == "updated"
    assert "name" in entry["details"]["changed"]


# -------------------------------------------------------------------- toggle


def test_toggle_enables_and_recomputes_next_run(store, profile_env):
    sched, _ = schedules_api.handle_create(make_data(enabled=False))
    assert sched["next_run_at"] is None
    toggled, error = schedules_api.handle_toggle(sched["id"])
    assert error is None
    assert toggled["enabled"] is True
    assert toggled["next_run_at"] > 0


def test_toggle_disables_and_clears_next_run(store, profile_env):
    sched, _ = schedules_api.handle_create(make_data())
    toggled, _ = schedules_api.handle_toggle(sched["id"])
    assert toggled["enabled"] is False
    assert toggled["next_run_at"] is None


def test_toggle_missing_schedule_returns_error(store):
    _, error = schedules_api.handle_toggle("nope")
    assert error == {"error": "Schedule not found"}


# ------------------------------------------------------------------- run_now


def test_run_now_starts_a_run_and_records_last_run(store, profile_env, new_run, sched_state):
    sched, _ = schedules_api.handle_create(make_data())
    result, error = schedules_api.handle_run_now(sched["id"])
    assert error is None
    assert result["run_id"]
    saved = store.read("schedules")[0]
    assert saved["last_run_id"] == result["run_id"]
    assert saved["last_run_at"] > 0
    # "Run now" is an extra run outside the cadence: next_run_at untouched
    assert saved["next_run_at"] == sched["next_run_at"]
    info = wait_done(result["run_id"])
    assert info["status"] == "completed"
    entry = [e for e in store.read("history") if e["run_id"] == result["run_id"]][-1]
    assert entry["trigger"] == "scheduled" and entry["schedule_name"] == "Hourly job"


def test_run_now_missing_schedule_returns_error(store):
    _, error = schedules_api.handle_run_now("nope")
    assert error


def test_run_now_records_an_audit_entry(store, profile_env, new_run, sched_state):
    sched, _ = schedules_api.handle_create(make_data())
    result, _ = schedules_api.handle_run_now(sched["id"])
    wait_done(result["run_id"])  # join the background run thread before it can leak
    entry = load_audit()[-1]
    assert entry["action"] == "run_now"
    assert entry["entity_type"] == "schedule"
    assert entry["entity_id"] == sched["id"]
    assert entry["details"]["run_id"] == result["run_id"]


# -------------------------------------------------------------------- delete


def test_delete_removes_schedule_and_audits(store, profile_env):
    sched, _ = schedules_api.handle_create(make_data())
    result, error = schedules_api.handle_delete(sched["id"])
    assert error is None
    assert result == {"ok": True}
    assert store.read("schedules") == []
    actions = [a["action"] for a in load_audit()]
    assert "created" in actions and "deleted" in actions


# ------------------------------------------------------------------- cascade


def test_profile_permanent_delete_removes_its_schedules(store, profile_env):
    sched, _ = schedules_api.handle_create(make_data())
    profiles_api.handle_permanent_delete("p1")
    assert store.read("schedules") == []
    entry = load_audit()[-1]
    assert entry["details"]["schedules_removed"] == [sched["id"]]


def test_workflow_permanent_delete_removes_its_schedules(store, profile_env):
    schedules_api.handle_create(make_data(target_type="workflow", target_id="w1"))
    workflows_api.handle_permanent_delete("w1")
    assert store.read("schedules") == []


def test_soft_delete_keeps_schedule_but_flags_target_trashed(store, profile_env):
    schedules_api.handle_create(make_data())
    profiles_api.handle_delete("p1")
    listed = schedules_api.handle_list()
    assert listed[0]["target_trashed"] is True
    assert listed[0]["target_name"] == "Job"


# ------------------------------------------------------------------- preview


def test_preview_returns_upcoming_runs():
    result, error = schedules_api.handle_preview("*/15 * * * *")
    assert error is None
    assert result["description"] == "Every 15 minutes"
    assert len(result["next"]) == 3
    stamps = [n["ts"] for n in result["next"]]
    assert stamps == sorted(stamps)
    assert all(n["local"] for n in result["next"])


def test_preview_rejects_invalid_cron():
    result, error = schedules_api.handle_preview("nope nope")
    assert result is None
    assert "Invalid cron" in error["error"]
