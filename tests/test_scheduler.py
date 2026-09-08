import time
from datetime import datetime

import pytest

import launcher.api.runs as runs
import launcher.scheduler as scheduler
from launcher.scheduler import (
    parse_cron,
    next_after,
    describe_cron,
    run_tick,
    fire_schedule,
    _skip_missed,
)


def dt(*args):
    return datetime(*args)


@pytest.fixture
def sched_state(monkeypatch):
    """Fresh scheduler run-tracking state for each test."""
    monkeypatch.setattr(scheduler, "_last_scheduled_run", {})
    yield


def wait_done(run_id, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        info = runs.handle_poll(run_id)
        if info and info["status"] in ("completed", "failed"):
            return info
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} did not finish in time")


def seed_schedule(store, **overrides):
    sched = {
        "id": "s1",
        "name": "Hourly",
        "target_type": "profile",
        "target_id": "p1",
        "cron": "0 * * * *",
        "enabled": True,
        "created_at": 0,
        "last_run_at": None,
        "last_run_id": None,
        "last_status": None,
        "next_run_at": None,
    }
    sched.update(overrides)
    store.seed("schedules", [sched])
    return sched


# ---------------------------------------------------------------- parse_cron


def test_parse_cron_wildcards_match_everything():
    fields = parse_cron("* * * * *")
    assert fields["minute"] == set(range(60))
    assert fields["hour"] == set(range(24))
    assert fields["dom"] == set(range(1, 32))
    assert fields["month"] == set(range(1, 13))
    assert fields["dow"] == set(range(7))


def test_parse_cron_single_values():
    fields = parse_cron("30 9 5 3 1")
    assert fields["minute"] == {30}
    assert fields["hour"] == {9}
    assert fields["dom"] == {5}
    assert fields["month"] == {3}
    assert fields["dow"] == {1}


def test_parse_cron_steps_lists_and_ranges():
    assert parse_cron("*/15 * * * *")["minute"] == {0, 15, 30, 45}
    assert parse_cron("5,35 */2 * * *")["minute"] == {5, 35}
    assert parse_cron("0 9-17 * * *")["hour"] == set(range(9, 18))
    assert parse_cron("0 8-18/2 * * *")["hour"] == {8, 10, 12, 14, 16, 18}
    assert parse_cron("10/5 * * * *")["minute"] == set(range(10, 60, 5))
    assert parse_cron("0 0 * * 1-5")["dow"] == {1, 2, 3, 4, 5}


def test_parse_cron_dow_7_is_sunday():
    assert parse_cron("0 0 * * 7")["dow"] == {0}
    assert parse_cron("0 0 * * 5-7")["dow"] == {5, 6, 0}


@pytest.mark.parametrize("expr", [
    "0 0 * *",          # too few fields
    "0 0 * * * *",      # too many fields
    "61 * * * *",       # minute out of range
    "* 24 * * *",       # hour out of range
    "* * 0 * *",        # dom starts at 1
    "* * 32 * *",       # dom out of range
    "* * * 13 *",       # month out of range
    "* * * * 8",        # dow out of range
    "*/0 * * * *",      # zero step
    "*/90 * * * *",     # minute step larger than the field span
    "* * */40 * *",     # dom step larger than the field span
    "* * * * */8",      # dow step larger than the field span
    "a * * * *",        # non-numeric
    "1-0 * * * *",      # reversed range
    "",                 # empty
    "5, * * * *",       # empty list item
])
def test_parse_cron_rejects_invalid_expressions(expr):
    with pytest.raises(ValueError):
        parse_cron(expr)


def test_parse_cron_accepts_max_steps():
    assert parse_cron("*/59 * * * *")["minute"] == {0, 59}
    assert parse_cron("* * */30 * *")["dom"] == {1, 31}
    assert parse_cron("* * * * */7")["dow"] == {0}


# ---------------------------------------------------------------- next_after


def test_next_after_hourly():
    assert next_after("0 * * * *", dt(2026, 9, 8, 10, 30, 15)) == dt(2026, 9, 8, 11, 0)


def test_next_after_minute_within_the_hour():
    assert next_after("45 * * * *", dt(2026, 9, 8, 10, 30)) == dt(2026, 9, 8, 10, 45)


def test_next_after_daily_crosses_midnight():
    assert next_after("30 9 * * *", dt(2026, 9, 8, 9, 30)) == dt(2026, 9, 9, 9, 30)


def test_next_after_is_strictly_after_an_exact_hit():
    assert next_after("0 10 * * *", dt(2026, 9, 8, 10, 0)) == dt(2026, 9, 9, 10, 0)


def test_next_after_seconds_are_truncated():
    assert next_after("* * * * *", dt(2026, 9, 8, 10, 30, 59)) == dt(2026, 9, 8, 10, 31)


def test_next_after_step_minutes():
    assert next_after("*/15 * * * *", dt(2026, 9, 8, 0, 14, 59)) == dt(2026, 9, 8, 0, 15)
    assert next_after("*/15 * * * *", dt(2026, 9, 8, 0, 0)) == dt(2026, 9, 8, 0, 15)


def test_next_after_dow_filter():
    # 2026-09-06 is a Sunday, 2026-09-07 is a Monday
    assert next_after("0 0 * * 1", dt(2026, 9, 6, 12, 0)) == dt(2026, 9, 7, 0, 0)


def test_next_after_feb_29():
    assert next_after("0 0 29 2 *", dt(2026, 9, 8)) == datetime(2028, 2, 29, 0, 0)


def test_next_after_month_and_dow_either_match():
    # 2026-09-08 is a Tuesday (cron dow 2). With both dom and dow restricted,
    # classic cron fires when either matches.
    assert next_after("0 0 15 * 2", dt(2026, 9, 8, 5, 0)) == dt(2026, 9, 15, 0, 0)
    assert next_after("0 0 10 * 2", dt(2026, 9, 8, 5, 0)) == dt(2026, 9, 10, 0, 0)
    assert next_after("0 0 20 * 3", dt(2026, 9, 8, 5, 0)) == dt(2026, 9, 9, 0, 0)


def test_next_after_impossible_expression_returns_none():
    assert next_after("0 0 31 2 *", dt(2026, 9, 8)) is None


# -------------------------------------------------------------- describe_cron


def test_describe_cron_common_shapes():
    assert describe_cron("* * * * *") == "Every minute"
    assert describe_cron("*/10 * * * *") == "Every 10 minutes"
    assert describe_cron("0 * * * *") == "Every hour"
    assert describe_cron("30 * * * *") == "Every hour at :30"
    assert describe_cron("0 */3 * * *") == "Every 3 hours"
    assert describe_cron("30 */3 * * *") == "Every 3 hours at :30"
    assert describe_cron("30 9 * * *") == "Daily at 09:30"
    assert describe_cron("0 8 * * 1-5") == "Weekdays at 08:00"
    assert describe_cron("0 8 * * 1") == "Weekly on Monday at 08:00"
    assert describe_cron("0 8 * * 1,5") == "Mondays & Fridays at 08:00"
    assert describe_cron("0 8 15 * *") == "Monthly on day 15 at 08:00"
    assert describe_cron("0 0 */3 * *") == "Every 3 days"
    assert describe_cron("0 9 */3 * *") == "Every 3 days at 09:00"


def test_describe_cron_falls_back_to_raw_expression():
    assert describe_cron("5 4 8 9 *") == "5 4 8 9 *"
    assert describe_cron("not a cron") == "not a cron"


# ------------------------------------------------------------------- run_tick


def test_run_tick_fires_due_schedule_and_persists_state(store, sched_state):
    seed_schedule(store, next_run_at=1000.0)
    now = dt(2026, 9, 8, 10, 30)
    fired = run_tick(now=now, fire=lambda s: "run_1")
    assert fired == [("s1", "run_1")]
    saved = store.read("schedules")[0]
    assert saved["last_run_id"] == "run_1"
    assert saved["last_run_at"] == pytest.approx(now.timestamp())
    assert saved["next_run_at"] > now.timestamp()


def test_run_tick_skips_disabled_schedules(store, sched_state):
    seed_schedule(store, enabled=False, next_run_at=1000.0)
    fired = run_tick(now=dt(2026, 9, 8, 10, 30), fire=lambda s: "run_1")
    assert fired == []
    assert store.read("schedules")[0]["next_run_at"] == 1000.0


def test_run_tick_computes_missing_next_run_without_firing(store, sched_state):
    seed_schedule(store, next_run_at=None)
    now = dt(2026, 9, 8, 10, 30)
    fired = run_tick(now=now, fire=lambda s: "run_1")
    assert fired == []
    assert store.read("schedules")[0]["next_run_at"] > now.timestamp()


def test_run_tick_ignores_invalid_cron(store, sched_state):
    seed_schedule(store, cron="not a cron", next_run_at=1000.0)
    fired = run_tick(now=dt(2026, 9, 8, 10, 30), fire=lambda s: "run_1")
    assert fired == []
    assert store.read("schedules")[0]["last_run_id"] is None


def test_run_tick_waits_while_previous_run_is_still_active(store, sched_state, monkeypatch):
    seed_schedule(store, next_run_at=1000.0)
    scheduler._last_scheduled_run["s1"] = "old_run"
    monkeypatch.setattr(runs, "active_runs", {"old_run": {"status": "running"}})
    fired = run_tick(now=dt(2026, 9, 8, 10, 30), fire=lambda s: "new_run")
    assert fired == []
    # Stays due so it fires on the next tick once the run finishes.
    assert store.read("schedules")[0]["next_run_at"] == 1000.0


def test_run_tick_fires_once_the_previous_run_finished(store, sched_state, monkeypatch):
    seed_schedule(store, next_run_at=1000.0)
    scheduler._last_scheduled_run["s1"] = "old_run"
    monkeypatch.setattr(runs, "active_runs", {"old_run": {"status": "completed"}})
    fired = run_tick(now=dt(2026, 9, 8, 10, 30), fire=lambda s: "new_run")
    assert fired == [("s1", "new_run")]
    assert "s1" not in scheduler._last_scheduled_run


def test_run_tick_end_to_end_with_real_fire(store, tmp_path, new_run, sched_state):
    script = tmp_path / "job.py"
    script.write_text("print('tick')\n")
    store.seed("profiles", [
        {"id": "p1", "name": "Job", "script_path": str(script), "args": [], "custom_args": []},
    ])
    now = dt(2026, 9, 8, 10, 30, 5)
    seed_schedule(store, cron="*/5 * * * *", next_run_at=now.timestamp() - 60)
    fired = run_tick(now=now)
    assert len(fired) == 1
    run_id = fired[0][1]
    saved = store.read("schedules")[0]
    assert saved["last_run_id"] == run_id
    assert saved["next_run_at"] > now.timestamp()
    info = wait_done(run_id)
    assert info["status"] == "completed"
    entry = store.read("history")[-1]
    assert entry["trigger"] == "scheduled"
    assert entry["schedule_id"] == "s1"
    assert entry["schedule_name"] == "Hourly"


# ----------------------------------------------------------------- _skip_missed


def test_skip_missed_advances_stale_next_run_without_firing(store, sched_state):
    seed_schedule(store, next_run_at=1000.0)
    now = dt(2026, 9, 8, 10, 30)
    _skip_missed(now=now)
    saved = store.read("schedules")[0]
    assert saved["next_run_at"] > now.timestamp()
    assert saved["last_run_id"] is None


def test_skip_missed_leaves_future_next_run_untouched(store, sched_state):
    future = dt(2026, 9, 8, 11, 0).timestamp()
    seed_schedule(store, next_run_at=future)
    _skip_missed(now=dt(2026, 9, 8, 10, 30))
    assert store.read("schedules")[0]["next_run_at"] == future


def test_skip_missed_ignores_disabled_and_invalid_schedules(store, sched_state):
    seed_schedule(store, enabled=False, next_run_at=1000.0)
    _skip_missed(now=dt(2026, 9, 8, 10, 30))
    assert store.read("schedules")[0]["next_run_at"] == 1000.0


# --------------------------------------------------------------- fire_schedule


def test_fire_schedule_starts_a_profile_run(store, tmp_path, new_run, sched_state):
    script = tmp_path / "job.py"
    script.write_text("print('tick')\n")
    store.seed("profiles", [
        {"id": "p1", "name": "Job", "script_path": str(script), "args": [], "custom_args": []},
    ])
    seed_schedule(store)
    run_id = fire_schedule(store.read("schedules")[0])
    assert run_id
    assert runs.active_runs[run_id]["trigger"] == "scheduled"
    assert runs.active_runs[run_id]["schedule_name"] == "Hourly"
    info = wait_done(run_id)
    assert info["status"] == "completed"
    entry = store.read("history")[-1]
    assert entry["run_id"] == run_id and entry["type"] == "profile"
    assert entry["trigger"] == "scheduled"


def test_fire_schedule_starts_a_workflow_run(store, tmp_path, new_run, sched_state):
    script = tmp_path / "job.py"
    script.write_text("print('ok')\n")
    store.seed("profiles", [
        {"id": "p1", "name": "Job", "script_path": str(script), "args": [], "custom_args": []},
    ])
    store.seed("workflows", [
        {"id": "w1", "name": "Nightly", "steps": [{"type": "sequential", "profile_id": "p1"}]},
    ])
    seed_schedule(store, target_type="workflow", target_id="w1")
    run_id = fire_schedule(store.read("schedules")[0])
    info = wait_done(run_id)
    assert info["status"] == "completed"
    entry = store.read("history")[-1]
    assert entry["type"] == "workflow" and entry["trigger"] == "scheduled"


def test_fire_schedule_skips_missing_target(store, sched_state):
    seed_schedule(store, target_id="ghost")
    assert fire_schedule(store.read("schedules")[0]) is None


def test_fire_schedule_skips_trashed_target(store, sched_state):
    store.seed("profiles", [
        {"id": "p1", "name": "Trashed", "script_path": "/x.py", "group": "__trash__"},
    ])
    seed_schedule(store)
    assert fire_schedule(store.read("schedules")[0]) is None


def test_fire_schedule_skips_missing_script(store, tmp_path, sched_state):
    store.seed("profiles", [
        {"id": "p1", "name": "Job", "script_path": str(tmp_path / "nope.py"), "args": [], "custom_args": []},
    ])
    seed_schedule(store)
    assert fire_schedule(store.read("schedules")[0]) is None


def test_fire_schedule_uses_profile_custom_arg_values(store, tmp_path, new_run, sched_state):
    script = tmp_path / "echo.py"
    script.write_text("import sys\nprint(' '.join(sys.argv[1:]))\n")
    store.seed("profiles", [
        {
            "id": "p1", "name": "Echo", "script_path": str(script), "args": ["static"],
            "custom_args": [{"name": "--flag", "type": "text", "value": "stored"}],
        },
    ])
    seed_schedule(store)
    run_id = fire_schedule(store.read("schedules")[0])
    info = wait_done(run_id)
    assert info["output"] == ["static --flag stored\n"], info["output"]
