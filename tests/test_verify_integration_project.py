"""Block 2 — verify flow at the PROJECT level.

Covers Project.verify_task behavior when invoked after a task's status
changed to DONE:
- Tasks without verify config → ok=True no-op
- File-exists verifier passes → status stays DONE
- File-exists verifier fails (required=True) → status reverts to
  IN_PROGRESS, reason appended to task.result
- Required=False failure → status stays DONE but verifier result
  still attached (warning mode)
- ProjectTask.verify + acceptance + depends_on all round-trip via
  to_dict / from_dict
- Invalid verify config surfaces error, doesn't crash
"""
from __future__ import annotations

import tempfile
import time
from pathlib import Path
import pytest

from app.project import Project, ProjectTask, ProjectTaskStatus


@pytest.fixture
def project_with_ws(tmp_path):
    """A fresh project with a usable working_directory."""
    p = Project(id="proj-test", name="Test Project",
                working_directory=str(tmp_path))
    return p


def _add_done_task(p: Project, *, verify: dict, acceptance: str = "",
                    result: str = "done") -> ProjectTask:
    """Helper: create a task that's already marked DONE so verify_task
    has something to check."""
    t = ProjectTask(
        id="t1", title="Produce the thing",
        description="test task",
        status=ProjectTaskStatus.DONE,
        assigned_to="agent-1",
        verify=verify,
        acceptance=acceptance,
        result=result,
        updated_at=time.time() - 60,  # started 60s ago
    )
    p.tasks.append(t)
    return t


# ─── no-verify no-op ────────────────────────────────────────────────

def test_verify_task_without_config_returns_ok_noop(project_with_ws):
    t = _add_done_task(project_with_ws, verify={})
    r = project_with_ws.verify_task(t.id)
    assert r["ok"] is True
    assert r["verifier_kind"] == "none"
    # Task status unchanged
    assert t.status == ProjectTaskStatus.DONE


def test_verify_task_unknown_id_returns_failure_not_exception(project_with_ws):
    r = project_with_ws.verify_task("nonexistent")
    assert r["ok"] is False
    assert "not found" in r["summary"].lower() or "not_found" in r["error"]


# ─── file_exists passing ────────────────────────────────────────────

def test_file_exists_passing_keeps_task_done(project_with_ws, tmp_path):
    (tmp_path / "report.pptx").write_bytes(b"PK" + b"x" * 20000)
    t = _add_done_task(
        project_with_ws,
        verify={"kind": "file_exists",
                "config": {"pattern": "*.pptx", "min_size_bytes": 1000,
                           "newer_than_start": False}},
    )
    r = project_with_ws.verify_task(t.id)
    assert r["ok"] is True, f"expected pass, got {r}"
    assert t.status == ProjectTaskStatus.DONE


# ─── file_exists failing + required ─────────────────────────────────

def test_file_exists_failing_reverts_task_status(project_with_ws, tmp_path):
    """Agent claimed done but file is missing → verifier fails →
    task status reverts to IN_PROGRESS, reason appended to result."""
    # workspace empty, no pptx
    t = _add_done_task(
        project_with_ws,
        verify={"kind": "file_exists",
                "config": {"pattern": "*.pptx",
                           "newer_than_start": False},
                "required": True},
    )
    r = project_with_ws.verify_task(t.id)
    assert r["ok"] is False
    assert t.status == ProjectTaskStatus.IN_PROGRESS
    assert "verifier:file_exists" in t.result
    assert "expected" in t.result


# ─── file_exists failing + NOT required (warning mode) ──────────────

def test_file_exists_failing_not_required_keeps_done(project_with_ws, tmp_path):
    """required=False means verifier failure is a WARNING — task stays DONE."""
    t = _add_done_task(
        project_with_ws,
        verify={"kind": "file_exists",
                "config": {"pattern": "*.pptx",
                           "newer_than_start": False},
                "required": False},
    )
    r = project_with_ws.verify_task(t.id)
    assert r["ok"] is False  # verifier says fail...
    # ...but task status unchanged because not required
    assert t.status == ProjectTaskStatus.DONE
    # Result NOT mutated (no appended reason since not reverted)
    assert "verifier:" not in t.result


# ─── command verifier integration ───────────────────────────────────

def test_command_verifier_on_project_task(project_with_ws, tmp_path):
    (tmp_path / "marker.txt").write_text("ok")
    t = _add_done_task(
        project_with_ws,
        verify={"kind": "command",
                "config": {"command": "test -f marker.txt"}},
    )
    r = project_with_ws.verify_task(t.id)
    assert r["ok"] is True
    assert t.status == ProjectTaskStatus.DONE


def test_command_verifier_fails_reverts_task(project_with_ws, tmp_path):
    t = _add_done_task(
        project_with_ws,
        verify={"kind": "command",
                "config": {"command": "test -f marker_missing.txt"}},
    )
    r = project_with_ws.verify_task(t.id)
    assert r["ok"] is False
    assert t.status == ProjectTaskStatus.IN_PROGRESS


# ─── llm_judge on task with injected llm_call ───────────────────────

def test_llm_judge_on_task_calls_injected_llm(project_with_ws):
    """ProjectChatEngine will inject the assignee's llm_call. Here we
    verify the mechanism works with a mock."""
    calls = []
    def fake_llm(messages, opts):
        calls.append(messages)
        return {"message": {"content": '{"ok": true, "reason": "looks good"}'}}
    t = _add_done_task(
        project_with_ws,
        verify={"kind": "llm_judge"},
        acceptance="PPT with 5+ slides, covering X/Y/Z",
        result="created report.pptx with 7 slides covering all requested sections",
    )
    r = project_with_ws.verify_task(t.id, llm_call=fake_llm)
    assert r["ok"] is True
    assert len(calls) == 1
    # System + user prompt shape
    assert calls[0][0]["role"] == "system"
    assert "PPT with 5" in calls[0][1]["content"] or \
           "5+ slides" in calls[0][1]["content"]


def test_llm_judge_rejection_reverts_task(project_with_ws):
    def fake_llm(messages, opts):
        return {"message": {"content": '{"ok": false, "reason": "vague"}'}}
    t = _add_done_task(
        project_with_ws,
        verify={"kind": "llm_judge"},
        acceptance="Produce a detailed landing zone design",
        result="design done",  # vague
    )
    r = project_with_ws.verify_task(t.id, llm_call=fake_llm)
    assert r["ok"] is False
    assert t.status == ProjectTaskStatus.IN_PROGRESS
    assert "verifier:llm_judge" in t.result


# ─── ProjectTask serialization including new fields ────────────────

def test_project_task_roundtrip_with_verify_and_acceptance_and_deps():
    t = ProjectTask(
        id="t42", title="x", assigned_to="a1",
        verify={"kind": "run_tests", "config": {"paths": "tests/"}},
        acceptance="all tests green",
        depends_on=["t40", "t41"],
    )
    d = t.to_dict()
    assert d["verify"]["kind"] == "run_tests"
    assert d["acceptance"] == "all tests green"
    assert d["depends_on"] == ["t40", "t41"]
    t2 = ProjectTask.from_dict(d)
    assert t2.verify == t.verify
    assert t2.acceptance == t.acceptance
    assert t2.depends_on == t.depends_on


def test_legacy_project_task_no_new_fields_defaults():
    """Persisted tasks from before this change should read cleanly."""
    old = {"id": "old", "title": "legacy",
           "status": "todo", "assigned_to": ""}
    t = ProjectTask.from_dict(old)
    assert t.verify == {}
    assert t.acceptance == ""
    assert t.depends_on == []


# ─── invalid verify config ──────────────────────────────────────────

def test_invalid_verify_config_does_not_crash_or_revert(project_with_ws):
    """Malformed verify dict should surface a clean failure without
    reverting task (we can't prove anything either way)."""
    t = _add_done_task(project_with_ws, verify={"config": {"x": 1}})  # missing kind
    r = project_with_ws.verify_task(t.id)
    assert r["ok"] is False
    assert "malformed" in r["summary"].lower() or "invalid" in r["summary"].lower()
    # Undeterminate verifier = don't revert; leave task DONE
    assert t.status == ProjectTaskStatus.DONE


# ─── progress bus emission ─────────────────────────────────────────

def test_verify_task_emits_progress_frame(project_with_ws, tmp_path):
    from app.progress_bus import get_bus
    bus = get_bus()
    sub = bus.subscribe("project:proj-test")
    try:
        (tmp_path / "out.txt").write_text("ok")
        t = _add_done_task(
            project_with_ws,
            verify={"kind": "file_exists",
                    "config": {"pattern": "out.txt",
                               "newer_than_start": False}},
        )
        project_with_ws.verify_task(t.id)
        f = sub.next(timeout=1.0)
        assert f is not None
        assert f.kind == "verify_result"
        assert f.data["ok"] is True
        assert f.data["verifier_kind"] == "file_exists"
        assert f.data["task_title"] == t.title
    finally:
        bus.unsubscribe(sub)
