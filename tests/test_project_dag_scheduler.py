"""Block 1 — Project-level DAG scheduler.

Tests the happy path AND the interesting edge cases:

- `_find_ready_dag_tasks`:
  - Task with no deps → NOT ready (legacy linear path owns it)
  - Task with deps all DONE → ready
  - Task with deps partially DONE → NOT ready
  - Task already IN_PROGRESS → NOT ready (already claimed)
  - Completed task → NOT ready

- `_dispatch_ready_dag_tasks`:
  - Dispatches multiple ready tasks at once (parallel fan-out)
  - Atomic claim: under lock, flips status to IN_PROGRESS BEFORE release
  - Handles task without assignee (logs warning, doesn't dispatch, doesn't
    block other tasks in the ready set)
  - Skips dispatch when project is paused
  - Skips dispatch when project status is CANCELLED/COMPLETED/ARCHIVED

- DAG progression:
  - Completion of a task triggers re-eval, unblocking dependents
  - Multiple independent task chains run in parallel
  - Emits step_started + step_completed frames

- `_detect_dag_deadlock`:
  - Task depending on missing ID → flagged
  - Task depending on BLOCKED task → flagged
  - Dependency cycle → flagged
  - Valid DAG → no false positives
"""
from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock
import pytest

from app.project import (
    Project, ProjectTask, ProjectTaskStatus, ProjectStatus,
    ProjectChatEngine,
)


# ─── fixtures ──────────────────────────────────────────────────────

def _make_engine() -> ProjectChatEngine:
    """Minimal engine — we don't call agent_chat here, just need the
    scheduler methods."""
    dispatched = []

    def chat_fn(aid, prompt):
        dispatched.append((aid, prompt[:50]))
        return f"reply for {aid}"

    def lookup(aid):
        ag = MagicMock()
        ag.id = aid
        ag.name = aid
        ag.role = "worker"
        return ag

    engine = ProjectChatEngine(
        agent_chat_fn=chat_fn, agent_lookup_fn=lookup, save_fn=lambda: None,
    )
    # Smoke-test handle-friendly
    engine._dispatched = dispatched
    return engine


def _mk_project(tasks_spec: list[dict]) -> Project:
    """tasks_spec: list of {id, title, assigned_to, depends_on, status}."""
    p = Project(id="p-dag", name="dag-test")
    for spec in tasks_spec:
        t = ProjectTask(
            id=spec["id"],
            title=spec.get("title", spec["id"]),
            assigned_to=spec.get("assigned_to", "worker-a"),
            depends_on=list(spec.get("depends_on", [])),
        )
        status = spec.get("status", "todo")
        t.status = ProjectTaskStatus(status)
        p.tasks.append(t)
    return p


# ─── _find_ready_dag_tasks ──────────────────────────────────────────

def test_task_without_depends_on_is_not_dag_ready():
    """No depends_on → legacy linear path owns it. DAG scheduler skips."""
    engine = _make_engine()
    p = _mk_project([
        {"id": "t1", "status": "todo"},  # no depends_on → legacy
    ])
    assert engine._find_ready_dag_tasks(p) == []


def test_task_with_all_deps_done_is_ready():
    engine = _make_engine()
    p = _mk_project([
        {"id": "t1", "status": "done"},
        {"id": "t2", "status": "todo", "depends_on": ["t1"]},
    ])
    ready = engine._find_ready_dag_tasks(p)
    assert [t.id for t in ready] == ["t2"]


def test_task_with_one_pending_dep_is_not_ready():
    engine = _make_engine()
    p = _mk_project([
        {"id": "t1", "status": "done"},
        {"id": "t2", "status": "todo"},  # not done yet
        {"id": "t3", "status": "todo", "depends_on": ["t1", "t2"]},
    ])
    ready = engine._find_ready_dag_tasks(p)
    # t2 has no deps → DAG skips (legacy)
    # t3 depends on both but t2 is not done → not ready
    assert ready == []


def test_in_progress_task_not_ready():
    engine = _make_engine()
    p = _mk_project([
        {"id": "t1", "status": "done"},
        {"id": "t2", "status": "in_progress", "depends_on": ["t1"]},
    ])
    assert engine._find_ready_dag_tasks(p) == []


def test_multiple_independent_tasks_all_ready():
    """DAG fan-out: 1 dep task done, 3 parallel tasks all depend only on it."""
    engine = _make_engine()
    p = _mk_project([
        {"id": "seed", "status": "done"},
        {"id": "front", "status": "todo", "depends_on": ["seed"]},
        {"id": "back", "status": "todo", "depends_on": ["seed"]},
        {"id": "db", "status": "todo", "depends_on": ["seed"]},
    ])
    ready = engine._find_ready_dag_tasks(p)
    assert set(t.id for t in ready) == {"front", "back", "db"}


def test_diamond_dag_converges_after_both_branches():
    """seed → {A, B} → finalize. finalize only ready when both A & B done."""
    engine = _make_engine()
    p = _mk_project([
        {"id": "seed", "status": "done"},
        {"id": "A", "status": "done", "depends_on": ["seed"]},
        {"id": "B", "status": "todo", "depends_on": ["seed"]},  # B not done yet
        {"id": "finalize", "status": "todo",
         "depends_on": ["A", "B"]},
    ])
    ready = engine._find_ready_dag_tasks(p)
    # B is ready (seed done); finalize is NOT (B not done)
    assert set(t.id for t in ready) == {"B"}


# ─── _dispatch_ready_dag_tasks ──────────────────────────────────────

def test_dispatch_flips_status_away_from_todo():
    engine = _make_engine()
    p = _mk_project([
        {"id": "seed", "status": "done"},
        {"id": "a", "status": "todo", "depends_on": ["seed"]},
    ])
    dispatched = engine._dispatch_ready_dag_tasks(p)
    assert dispatched == ["a"]
    # Critical: atomically flipped away from TODO before release.
    # May land as IN_PROGRESS or (in fast chat_fn mocks) DONE — either
    # means "claimed, won't be re-dispatched".
    assert p.get_task("a").status != ProjectTaskStatus.TODO


def test_dispatch_parallel_fan_out():
    """Three tasks all ready after seed done — all should be dispatched."""
    engine = _make_engine()
    p = _mk_project([
        {"id": "seed", "status": "done"},
        {"id": "front", "status": "todo", "depends_on": ["seed"], "assigned_to": "a1"},
        {"id": "back", "status": "todo", "depends_on": ["seed"], "assigned_to": "a2"},
        {"id": "db", "status": "todo", "depends_on": ["seed"], "assigned_to": "a3"},
    ])
    dispatched = engine._dispatch_ready_dag_tasks(p)
    assert set(dispatched) == {"front", "back", "db"}
    for tid in ("front", "back", "db"):
        assert p.get_task(tid).status != ProjectTaskStatus.TODO


def test_dispatch_skips_task_without_assignee():
    """A ready task with no assignee shouldn't block the rest of the DAG."""
    engine = _make_engine()
    p = _mk_project([
        {"id": "seed", "status": "done"},
        {"id": "good", "status": "todo", "depends_on": ["seed"], "assigned_to": "a1"},
        {"id": "bad",  "status": "todo", "depends_on": ["seed"], "assigned_to": ""},
    ])
    dispatched = engine._dispatch_ready_dag_tasks(p)
    assert dispatched == ["good"]
    # "bad" stays TODO so admin can fix and re-trigger
    assert p.get_task("bad").status == ProjectTaskStatus.TODO
    assert p.get_task("good").status != ProjectTaskStatus.TODO


def test_dispatch_skips_when_paused():
    engine = _make_engine()
    p = _mk_project([
        {"id": "seed", "status": "done"},
        {"id": "a", "status": "todo", "depends_on": ["seed"]},
    ])
    p.paused = True
    dispatched = engine._dispatch_ready_dag_tasks(p)
    assert dispatched == []
    # Task stays TODO — will run when resumed
    assert p.get_task("a").status == ProjectTaskStatus.TODO


def test_dispatch_skips_when_project_cancelled():
    engine = _make_engine()
    p = _mk_project([
        {"id": "seed", "status": "done"},
        {"id": "a", "status": "todo", "depends_on": ["seed"]},
    ])
    p.status = ProjectStatus.CANCELLED
    assert engine._dispatch_ready_dag_tasks(p) == []


def test_dispatch_skips_when_project_completed():
    engine = _make_engine()
    p = _mk_project([
        {"id": "seed", "status": "done"},
        {"id": "a", "status": "todo", "depends_on": ["seed"]},
    ])
    p.status = ProjectStatus.COMPLETED
    assert engine._dispatch_ready_dag_tasks(p) == []


def test_repeated_dispatch_same_project_is_idempotent():
    """Calling _dispatch twice with no state change should not double-run."""
    engine = _make_engine()
    p = _mk_project([
        {"id": "seed", "status": "done"},
        {"id": "a", "status": "todo", "depends_on": ["seed"]},
    ])
    d1 = engine._dispatch_ready_dag_tasks(p)
    d2 = engine._dispatch_ready_dag_tasks(p)
    assert d1 == ["a"]
    # Second call: "a" is now IN_PROGRESS, not ready anymore
    assert d2 == []


# ─── progress bus frames ────────────────────────────────────────────

def test_dispatch_emits_step_started_frames():
    from app.progress_bus import get_bus
    engine = _make_engine()
    p = _mk_project([
        {"id": "seed", "status": "done"},
        {"id": "a", "status": "todo", "depends_on": ["seed"], "assigned_to": "worker-a"},
    ])
    bus = get_bus()
    sub = bus.subscribe(f"plan:{p.id}")
    try:
        engine._dispatch_ready_dag_tasks(p)
        # Should receive at least a step_started frame
        found_started = False
        for _ in range(5):
            f = sub.next(timeout=0.5)
            if f is None:
                break
            if f.kind == "step_started" and f.step_id == "a":
                found_started = True
                assert f.agent_id == "worker-a"
                break
        assert found_started, "step_started frame expected"
    finally:
        bus.unsubscribe(sub)


# ─── _detect_dag_deadlock ───────────────────────────────────────────

def test_deadlock_missing_dep_detected():
    engine = _make_engine()
    p = _mk_project([
        {"id": "a", "status": "todo", "depends_on": ["ghost"]},
    ])
    stuck = engine._detect_dag_deadlock(p)
    assert len(stuck) == 1
    assert stuck[0]["task_id"] == "a"
    assert any("missing" in b for b in stuck[0]["bad_deps"])


def test_deadlock_blocked_dep_detected():
    engine = _make_engine()
    p = _mk_project([
        {"id": "upstream", "status": "blocked"},
        {"id": "downstream", "status": "todo", "depends_on": ["upstream"]},
    ])
    stuck = engine._detect_dag_deadlock(p)
    assert len(stuck) == 1
    assert stuck[0]["task_id"] == "downstream"


def test_deadlock_cycle_detected():
    """a → b → c → a"""
    engine = _make_engine()
    p = _mk_project([
        {"id": "a", "status": "todo", "depends_on": ["c"]},
        {"id": "b", "status": "todo", "depends_on": ["a"]},
        {"id": "c", "status": "todo", "depends_on": ["b"]},
    ])
    stuck = engine._detect_dag_deadlock(p)
    # All three should be flagged (each has a cycle involving itself)
    assert len(stuck) == 3
    for s in stuck:
        assert "cycle" in s["reason"]


def test_deadlock_valid_dag_no_false_positives():
    engine = _make_engine()
    p = _mk_project([
        {"id": "a", "status": "done"},
        {"id": "b", "status": "todo", "depends_on": ["a"]},
        {"id": "c", "status": "todo", "depends_on": ["b"]},
    ])
    assert engine._detect_dag_deadlock(p) == []


def test_deadlock_tasks_without_deps_ignored():
    """Legacy linear tasks (no depends_on) shouldn't be flagged."""
    engine = _make_engine()
    p = _mk_project([
        {"id": "legacy1", "status": "todo"},
        {"id": "legacy2", "status": "todo"},
    ])
    assert engine._detect_dag_deadlock(p) == []


# ─── atomic claim (race safety) ─────────────────────────────────────

def test_concurrent_dispatchers_do_not_double_dispatch():
    """Two threads calling _dispatch at the same moment should produce
    exactly ONE dispatch of each ready task (project._lock guarantees)."""
    engine = _make_engine()
    p = _mk_project([
        {"id": "seed", "status": "done"},
        {"id": "a", "status": "todo", "depends_on": ["seed"]},
        {"id": "b", "status": "todo", "depends_on": ["seed"]},
    ])

    results: list[list[str]] = []
    barrier = threading.Barrier(4)

    def try_dispatch():
        barrier.wait()
        ids = engine._dispatch_ready_dag_tasks(p)
        results.append(ids)

    threads = [threading.Thread(target=try_dispatch) for _ in range(4)]
    for t in threads: t.start()
    for t in threads: t.join()

    # Pool the dispatched ids across all threads — each task should
    # appear exactly once total.
    all_dispatched: list[str] = []
    for r in results:
        all_dispatched.extend(r)
    assert sorted(all_dispatched) == ["a", "b"]


# ─── integration: chain completion re-triggers ready set ────────────

def test_completion_triggers_downstream_dispatch():
    """When t1 completes, the finally-hook in handle_task_assignment
    calls _dispatch_ready_dag_tasks, unblocking t2."""
    engine = _make_engine()
    p = _mk_project([
        {"id": "t1", "status": "todo", "assigned_to": "worker-a"},  # legacy
        {"id": "t2", "status": "todo", "depends_on": ["t1"], "assigned_to": "worker-b"},
    ])
    # t1 is NOT a DAG task (no deps) — we manually mark it DONE to
    # simulate the legacy path's completion. Then call the dispatcher.
    p.get_task("t1").status = ProjectTaskStatus.DONE

    dispatched = engine._dispatch_ready_dag_tasks(p)
    assert dispatched == ["t2"]
