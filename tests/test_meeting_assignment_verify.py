"""P0 + P1 + Q2(x) — Meeting assignment verify + completion contract + re-execute.

Covers the bug user reported:
- agent edited build_report.py, went IDLE without running bash / sending email
- meeting assignment was marked DONE anyway (because old contract said
  "reply is non-empty → done")
- user received no email
- meeting task shows ✅ but work isn't actually done

Tests:
- MeetingAssignment.verify / acceptance / reexecute_count fields roundtrip
- Meeting.verify_assignment helper: pass/fail paths + no-verify legacy
- execute_meeting_assignment new completion contract:
    - reply ok + plan all done + verifier ok → DONE
    - reply ok + plan has unfinished steps → OPEN
    - reply ok + plan done + verifier fails → OPEN
    - reply error → OPEN
    - legacy (no verify, no plan) → DONE as before (backward compat)
- _build_resume_prompt: mentions completed steps + unfinished + workspace files
- spawn_meeting_assignment_reexecute: kicks off executor with resume=True
"""
from __future__ import annotations

import time
import tempfile
import threading
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from app.meeting import (
    Meeting, MeetingAssignment, AssignmentStatus, MeetingRegistry,
    execute_meeting_assignment, _build_resume_prompt,
)
from app.agent import Agent, ExecutionPlan, ExecutionStep, StepStatus
from app.agent_types import AgentStatus


# ─── data model ────────────────────────────────────────────────────

def test_meeting_assignment_verify_and_acceptance_roundtrip():
    a = MeetingAssignment(
        id="a1", title="生成 PPT + 发邮件",
        assignee_agent_id="xiaotu",
        acceptance="report.pptx 发送到 user@example.com，message_id 返回",
        verify={"kind": "file_exists",
                "config": {"pattern": "*.pptx", "newer_than_start": True}},
    )
    d = a.to_dict()
    assert d["acceptance"].startswith("report.pptx")
    assert d["verify"]["kind"] == "file_exists"
    a2 = MeetingAssignment.from_dict(d)
    assert a2.acceptance == a.acceptance
    assert a2.verify == a.verify
    assert a2.reexecute_count == 0


def test_legacy_assignment_no_new_fields_defaults():
    """Persisted assignments from before this change must still deserialize."""
    old = {"id": "legacy", "title": "x", "status": "open",
           "assignee_agent_id": "a1"}
    a = MeetingAssignment.from_dict(old)
    assert a.verify == {}
    assert a.acceptance == ""
    assert a.reexecute_count == 0
    assert a.last_reexecute_at == 0.0


def test_reexecute_count_roundtrip():
    a = MeetingAssignment(
        id="r1", title="t",
        reexecute_count=3, last_reexecute_at=1700000000.0,
    )
    d = a.to_dict()
    a2 = MeetingAssignment.from_dict(d)
    assert a2.reexecute_count == 3
    assert a2.last_reexecute_at == 1700000000.0


# ─── Meeting.verify_assignment helper ──────────────────────────────

def _make_meeting_with_assignment(tmp_path, *, verify: dict, acceptance: str = "",
                                     result: str = "") -> tuple[Meeting, MeetingAssignment]:
    m = Meeting(id="m1", title="t", workspace_dir=str(tmp_path))
    a = m.add_assignment(
        title="Produce report", assignee_agent_id="xiaotu",
        acceptance=acceptance, verify=verify,
    )
    a.result = result
    return m, a


def test_verify_assignment_no_config_is_noop(tmp_path):
    m, a = _make_meeting_with_assignment(tmp_path, verify={})
    r = m.verify_assignment(a.id)
    assert r["ok"] is True
    assert r["verifier_kind"] == "none"


def test_verify_assignment_passing_keeps_status(tmp_path):
    (tmp_path / "report.pptx").write_bytes(b"PK" + b"x" * 20000)
    m, a = _make_meeting_with_assignment(
        tmp_path,
        verify={"kind": "file_exists",
                "config": {"pattern": "*.pptx",
                           "newer_than_start": False}},
    )
    a.status = AssignmentStatus.DONE
    r = m.verify_assignment(a.id)
    assert r["ok"] is True
    # Status unchanged
    assert a.status == AssignmentStatus.DONE


def test_verify_assignment_failing_reverts_to_open(tmp_path):
    """Workspace has no pptx → verifier fails → revert DONE → OPEN + reason in result."""
    m, a = _make_meeting_with_assignment(
        tmp_path,
        verify={"kind": "file_exists",
                "config": {"pattern": "*.pptx",
                           "newer_than_start": False}},
    )
    a.status = AssignmentStatus.DONE
    r = m.verify_assignment(a.id)
    assert r["ok"] is False
    # Critical: status was reverted
    assert a.status == AssignmentStatus.OPEN
    # Reason appended so next turn can see what went wrong
    assert "[verifier:file_exists]" in a.result


def test_verify_assignment_not_required_keeps_done(tmp_path):
    m, a = _make_meeting_with_assignment(
        tmp_path,
        verify={"kind": "file_exists",
                "config": {"pattern": "*.pptx",
                           "newer_than_start": False},
                "required": False},
    )
    a.status = AssignmentStatus.DONE
    r = m.verify_assignment(a.id)
    assert r["ok"] is False
    # not required → status unchanged even though verify failed
    assert a.status == AssignmentStatus.DONE


def test_verify_assignment_unknown_id_does_not_crash(tmp_path):
    m = Meeting(id="m-ghost", workspace_dir=str(tmp_path))
    r = m.verify_assignment("nonexistent")
    assert r["ok"] is False
    assert "not found" in r["summary"].lower() or "not_found" in r.get("error", "")


# ─── _build_resume_prompt ──────────────────────────────────────────

def _make_agent_with_plan(plan: ExecutionPlan):
    ag = MagicMock()
    ag._current_plan = plan
    ag.name = "xiaotu"
    ag.role = "executor"
    ag.id = "xiaotu"
    return ag


def test_resume_prompt_lists_completed_and_unfinished_steps(tmp_path):
    m = Meeting(id="m-rp", workspace_dir=str(tmp_path))
    a = m.add_assignment(title="Generate PPT",
                          assignee_agent_id="xiaotu",
                          acceptance="report.pptx ≥ 5 slides")
    plan = ExecutionPlan(task_summary="Generate PPT")
    s1 = plan.add_step(title="搜索数据", acceptance="3 sources")
    s1.status = StepStatus.COMPLETED
    s1.result_summary = "AWS 31%, Azure 25%, GCP 11%"
    s2 = plan.add_step(title="写 build_report.py", acceptance="script runs clean")
    s2.status = StepStatus.COMPLETED
    s2.result_summary = "written, passes py_compile"
    s3 = plan.add_step(title="生成 PPTX", acceptance="report.pptx produced")
    s3.status = StepStatus.IN_PROGRESS
    s3.result_summary = "script edited but not run"
    s4 = plan.add_step(title="发邮件", acceptance="mcp_call returns message_id")
    s4.status = StepStatus.PENDING

    ag = _make_agent_with_plan(plan)
    prompt = _build_resume_prompt(m, ag, a)

    # Completed steps appear with their summaries
    assert "搜索数据" in prompt
    assert "AWS 31%" in prompt
    assert "写 build_report.py" in prompt
    # Unfinished steps clearly marked
    assert "生成 PPTX" in prompt
    assert "in_progress" in prompt
    assert "发邮件" in prompt
    assert "pending" in prompt
    # acceptance surfaced for unfinished
    assert "report.pptx produced" in prompt
    assert "mcp_call returns message_id" in prompt
    # Continuation tone (not "start fresh")
    assert "继续" in prompt
    assert "不要重新生成已经存在的文件" in prompt or "不要" in prompt


def test_resume_prompt_lists_workspace_artifacts(tmp_path):
    m = Meeting(id="m-ws", workspace_dir=str(tmp_path))
    a = m.add_assignment(title="Produce stuff", assignee_agent_id="xiaotu")
    # Write files that should show up as "existing artifacts"
    (tmp_path / "build_report.py").write_bytes(b"x" * 23000)
    (tmp_path / "analysis.md").write_text("x" * 21000)
    # This one is older than assignment.created_at — should NOT be listed
    old = tmp_path / "ancient.txt"
    old.write_text("old")
    import os
    old_time = a.created_at - 3600
    os.utime(str(old), (old_time, old_time))

    ag = _make_agent_with_plan(ExecutionPlan(task_summary="t"))
    prompt = _build_resume_prompt(m, ag, a)
    assert "build_report.py" in prompt
    assert "analysis.md" in prompt
    # Older file NOT in the "existing artifacts" section
    assert "ancient.txt" not in prompt


def test_resume_prompt_mentions_interruption_reason_from_verifier(tmp_path):
    m = Meeting(id="m-reason", workspace_dir=str(tmp_path))
    a = m.add_assignment(title="T", assignee_agent_id="xiaotu")
    a.result = "initial reply\n[verifier:file_exists] expected *.pptx but none found"
    ag = _make_agent_with_plan(ExecutionPlan(task_summary="t"))
    prompt = _build_resume_prompt(m, ag, a)
    assert "上次中断原因" in prompt
    assert "verifier:file_exists" in prompt
    assert "expected" in prompt


def test_resume_prompt_handles_no_plan_gracefully(tmp_path):
    m = Meeting(id="m-noplan", workspace_dir=str(tmp_path))
    a = m.add_assignment(title="T", assignee_agent_id="xiaotu")
    ag = MagicMock()
    ag._current_plan = None
    ag.name = "xiaotu"
    ag.role = "executor"
    prompt = _build_resume_prompt(m, ag, a)
    # No plan section but still a valid continuation prompt
    assert "继续" in prompt
    assert "原任务" in prompt


# ─── execute_meeting_assignment new completion contract ─────────────

class _ExecutorFixture:
    """Build an agent + meeting + assignment the way the real executor sees them."""

    def __init__(self, tmp_path, *, reply: str, plan_state: str = "all_done",
                 verify_cfg: dict = None, acceptance: str = ""):
        self.tmp_path = tmp_path
        self.reply = reply
        self.reg = MagicMock(spec=MeetingRegistry)
        self.meeting = Meeting(id="m-exec", title="t",
                                workspace_dir=str(tmp_path))
        self.assignment = self.meeting.add_assignment(
            title="do thing", assignee_agent_id="xiaotu",
            acceptance=acceptance, verify=verify_cfg or {},
        )
        # Start marked IN_PROGRESS to match real flow
        self.assignment.status = AssignmentStatus.IN_PROGRESS

        # Build agent stub — enough of an Agent surface for executor
        self.agent = MagicMock()
        self.agent.id = "xiaotu"
        self.agent.name = "xiaotu"
        self.agent.role = "executor"
        self.agent.shared_workspace = ""
        self.agent.events = []
        # Plan state
        plan = ExecutionPlan(task_summary="t")
        if plan_state == "all_done":
            s = plan.add_step(title="done-step")
            s.status = StepStatus.COMPLETED
        elif plan_state == "has_pending":
            plan.add_step(title="pending-step")  # stays PENDING
        elif plan_state == "has_in_progress":
            s = plan.add_step(title="stuck-step")
            s.status = StepStatus.IN_PROGRESS
        elif plan_state == "none":
            plan = None
        self.agent._current_plan = plan

    def _chat_fn(self, aid, prompt):
        return self.reply

    def _lookup(self, aid):
        return self.agent

    def run(self):
        execute_meeting_assignment(
            meeting=self.meeting,
            registry=self.reg,
            agent_chat_fn=self._chat_fn,
            agent_lookup_fn=self._lookup,
            assignment=self.assignment,
        )


def test_executor_reply_ok_plan_done_no_verify_marks_done(tmp_path):
    """Backward compat: no verify config → existing behavior (assumes ok)."""
    f = _ExecutorFixture(tmp_path,
                          reply="done, generated report",
                          plan_state="all_done",
                          verify_cfg={})
    f.run()
    assert f.assignment.status == AssignmentStatus.DONE


def test_executor_reply_ok_plan_has_unfinished_stays_open(tmp_path):
    """The USER'S BUG: LLM returns prose "done", but plan still has
    in_progress steps → executor no longer marks DONE."""
    f = _ExecutorFixture(tmp_path,
                          reply="already handled it, all good",
                          plan_state="has_in_progress",
                          verify_cfg={})
    f.run()
    assert f.assignment.status == AssignmentStatus.OPEN
    # Assistant message should cite the unfinished plan step
    assert "尚未完成" in f.assignment.result or "unfinished" in f.assignment.result


def test_executor_reply_ok_plan_done_verify_fails_stays_open(tmp_path):
    """Agent's plan says done, but verifier (file_exists) says no pptx → OPEN."""
    f = _ExecutorFixture(
        tmp_path,
        reply="report generated and email sent",
        plan_state="all_done",
        verify_cfg={"kind": "file_exists",
                    "config": {"pattern": "*.pptx",
                               "newer_than_start": False}},
    )
    # No pptx in workspace — verifier will fail
    f.run()
    assert f.assignment.status == AssignmentStatus.OPEN
    assert "verifier" in f.assignment.result.lower()


def test_executor_reply_ok_plan_done_verify_passes_marks_done(tmp_path):
    """Happy path: plan done + artifact on disk → verifier ok → DONE."""
    (tmp_path / "report.pptx").write_bytes(b"PK" + b"x" * 20000)
    f = _ExecutorFixture(
        tmp_path,
        reply="report generated successfully",
        plan_state="all_done",
        verify_cfg={"kind": "file_exists",
                    "config": {"pattern": "*.pptx",
                               "newer_than_start": False}},
    )
    f.run()
    assert f.assignment.status == AssignmentStatus.DONE


def test_executor_reply_error_stays_open_regardless_of_plan(tmp_path):
    f = _ExecutorFixture(tmp_path,
                          reply="❌ 任务执行失败: connection reset",
                          plan_state="all_done",
                          verify_cfg={})
    f.run()
    assert f.assignment.status == AssignmentStatus.OPEN


def test_executor_no_plan_no_verify_preserves_legacy_contract(tmp_path):
    """Assignments created the old way (no plan, no verify) should still
    flow through the old "reply non-empty → done" heuristic."""
    f = _ExecutorFixture(tmp_path,
                          reply="ok, done.",
                          plan_state="none",
                          verify_cfg={})
    f.run()
    assert f.assignment.status == AssignmentStatus.DONE


# ─── Resume reexecute_count bump ───────────────────────────────────

def test_resume_bumps_reexecute_count(tmp_path):
    f = _ExecutorFixture(tmp_path,
                          reply="continuing",
                          plan_state="all_done",
                          verify_cfg={})
    # Run in resume mode — simulating a "重新执行" click
    execute_meeting_assignment(
        meeting=f.meeting, registry=f.reg,
        agent_chat_fn=f._chat_fn, agent_lookup_fn=f._lookup,
        assignment=f.assignment, resume=True,
    )
    assert f.assignment.reexecute_count == 1
    assert f.assignment.last_reexecute_at > 0
