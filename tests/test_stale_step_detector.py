"""Stale step detector + manual resolution helpers.

The exact user-facing bug: plan shows step as in_progress, agent has
gone idle 10+ minutes ago, UI doesn't know anything's wrong.

Covers:
- IDLE agent + in_progress step → detected immediately (no threshold needed)
- BUSY agent + in_progress step + no recent events > threshold → detected
- BUSY agent + in_progress step + recent events → NOT detected (legit work)
- Empty plan / completed plan → no false positives
- Detector is side-effect free (doesn't mutate step state) — per user rule (a)
- Detector emits step_stale frame when emit_frames=True
- mark_step_failed / mark_step_skipped / resume_step each do the right thing
- Bus frames fire for mark_failed / mark_skipped
"""
from __future__ import annotations

import time
import pytest

from app.agent import Agent, ExecutionPlan, ExecutionStep, StepStatus
from app.agent_types import AgentStatus
from app.progress_bus import get_bus


def _make_agent_with_plan(plan_steps: list[ExecutionStep]) -> Agent:
    agent = Agent.__new__(Agent)
    agent.id = "test-agent"
    agent.status = AgentStatus.IDLE
    agent.events = []
    plan = ExecutionPlan(task_summary="t")
    plan.steps = plan_steps
    agent._current_plan = plan
    agent.execution_plans = [plan]
    agent._log = lambda *a, **kw: None
    return agent


# ─── detection signals ─────────────────────────────────────────────

def test_idle_agent_with_in_progress_step_is_stale():
    s = ExecutionStep(id="s1", title="Generate PPT",
                       status=StepStatus.IN_PROGRESS,
                       started_at=time.time() - 600)  # 10 min ago
    agent = _make_agent_with_plan([s])
    agent.status = AgentStatus.IDLE
    stale = agent._detect_stale_plan_steps(threshold_s=120, emit_frames=False)
    assert len(stale) == 1
    assert stale[0]["step_id"] == "s1"
    assert "IDLE" in stale[0]["reason"]
    assert stale[0]["stale_s"] >= 500  # ~10 min


def test_idle_agent_with_fresh_in_progress_step_still_stale():
    """Even if step just started, IDLE agent + in_progress is immediate inconsistency."""
    s = ExecutionStep(id="s1", title="Just started",
                       status=StepStatus.IN_PROGRESS,
                       started_at=time.time() - 3)  # 3 seconds ago
    agent = _make_agent_with_plan([s])
    agent.status = AgentStatus.IDLE
    stale = agent._detect_stale_plan_steps(threshold_s=120, emit_frames=False)
    assert len(stale) == 1  # still detected — IDLE is authoritative


def test_busy_agent_with_recent_events_not_stale():
    """Legit long-running op: agent BUSY, step in_progress 3 min, but
    events fired 5s ago. Should NOT be detected."""
    from app.agent_types import AgentEvent
    s = ExecutionStep(id="s1", title="Big op",
                       status=StepStatus.IN_PROGRESS,
                       started_at=time.time() - 180)
    agent = _make_agent_with_plan([s])
    agent.status = AgentStatus.BUSY
    # Recent event
    agent.events = [AgentEvent(time.time() - 5, "tool_call", {"name": "bash"})]
    stale = agent._detect_stale_plan_steps(threshold_s=120, emit_frames=False)
    assert stale == []


def test_busy_agent_no_activity_past_threshold_is_stale():
    """Agent BUSY, step in_progress > threshold, no events in last
    threshold_s → LLM / tool call hung. Stale."""
    from app.agent_types import AgentEvent
    s = ExecutionStep(id="s1", title="Hung op",
                       status=StepStatus.IN_PROGRESS,
                       started_at=time.time() - 400)
    agent = _make_agent_with_plan([s])
    agent.status = AgentStatus.BUSY
    # Last event was 300s ago — past the 120s threshold
    agent.events = [AgentEvent(time.time() - 300, "tool_call", {"name": "bash"})]
    stale = agent._detect_stale_plan_steps(threshold_s=120, emit_frames=False)
    assert len(stale) == 1
    assert "no tool activity" in stale[0]["reason"]


def test_completed_step_not_stale():
    s = ExecutionStep(id="s1", title="done",
                       status=StepStatus.COMPLETED)
    agent = _make_agent_with_plan([s])
    agent.status = AgentStatus.IDLE
    assert agent._detect_stale_plan_steps(emit_frames=False) == []


def test_pending_step_not_stale():
    s = ExecutionStep(id="s1", title="pending",
                       status=StepStatus.PENDING)
    agent = _make_agent_with_plan([s])
    agent.status = AgentStatus.IDLE
    assert agent._detect_stale_plan_steps(emit_frames=False) == []


def test_mixed_plan_only_in_progress_flagged():
    s1 = ExecutionStep(id="s1", status=StepStatus.COMPLETED)
    s2 = ExecutionStep(id="s2", title="Stuck",
                        status=StepStatus.IN_PROGRESS,
                        started_at=time.time() - 60)
    s3 = ExecutionStep(id="s3", status=StepStatus.PENDING)
    agent = _make_agent_with_plan([s1, s2, s3])
    agent.status = AgentStatus.IDLE
    stale = agent._detect_stale_plan_steps(emit_frames=False)
    assert [s["step_id"] for s in stale] == ["s2"]


def test_no_plan_returns_empty():
    agent = Agent.__new__(Agent)
    agent.id = "a"
    agent.status = AgentStatus.IDLE
    agent.events = []
    agent._current_plan = None
    assert agent._detect_stale_plan_steps(emit_frames=False) == []


def test_detector_is_side_effect_free():
    """Per user rule (a): detector must NOT mutate step state."""
    s = ExecutionStep(id="s1", title="stuck",
                       status=StepStatus.IN_PROGRESS,
                       started_at=time.time() - 600,
                       result_summary="original")
    agent = _make_agent_with_plan([s])
    agent.status = AgentStatus.IDLE
    original_status = s.status
    original_summary = s.result_summary
    agent._detect_stale_plan_steps(emit_frames=False)
    # Step unchanged
    assert s.status == original_status
    assert s.result_summary == original_summary


# ─── frame emission ────────────────────────────────────────────────

def test_detector_emits_step_stale_frame_to_bus():
    bus = get_bus()
    s = ExecutionStep(id="s-frame", title="Generate PPT",
                       status=StepStatus.IN_PROGRESS,
                       started_at=time.time() - 300)
    agent = _make_agent_with_plan([s])
    agent.status = AgentStatus.IDLE
    sub = bus.subscribe(f"plan:{agent._current_plan.id}")
    try:
        agent._detect_stale_plan_steps(emit_frames=True)
        f = sub.next(timeout=1.0)
        assert f is not None
        assert f.kind == "step_stale"
        assert f.step_id == "s-frame"
        assert f.data["title"] == "Generate PPT"
        assert f.data["stale_s"] >= 200
        assert "IDLE" in f.data["reason"]
    finally:
        bus.unsubscribe(sub)


def test_detector_no_emit_when_flag_false():
    """emit_frames=False (used by API GET endpoint) shouldn't pollute bus."""
    bus = get_bus()
    s = ExecutionStep(id="s-noemit", status=StepStatus.IN_PROGRESS,
                       started_at=time.time() - 300)
    agent = _make_agent_with_plan([s])
    agent.status = AgentStatus.IDLE
    sub = bus.subscribe(f"plan:{agent._current_plan.id}")
    try:
        agent._detect_stale_plan_steps(emit_frames=False)
        assert sub.next(timeout=0.2) is None  # no frame
    finally:
        bus.unsubscribe(sub)


# ─── manual resolution helpers ──────────────────────────────────────

def test_mark_step_failed_transitions_and_annotates():
    s = ExecutionStep(id="s1", title="stuck",
                       status=StepStatus.IN_PROGRESS,
                       result_summary="agent tried something")
    agent = _make_agent_with_plan([s])
    result = agent.mark_step_failed("s1", reason="taking too long")
    assert result is not None
    assert s.status == StepStatus.FAILED
    assert "manually marked FAILED" in s.result_summary
    assert "taking too long" in s.result_summary
    # Plan status is active (can't be completed if step failed)
    assert agent._current_plan.status == "active"


def test_mark_step_failed_unknown_id_returns_none():
    agent = _make_agent_with_plan([])
    assert agent.mark_step_failed("nope") is None


def test_mark_step_skipped_transitions_and_can_complete_plan():
    """Skipping the last remaining step should complete the plan."""
    s1 = ExecutionStep(id="s1", status=StepStatus.COMPLETED)
    s2 = ExecutionStep(id="s2", status=StepStatus.IN_PROGRESS)
    agent = _make_agent_with_plan([s1, s2])
    agent.mark_step_skipped("s2", reason="not essential")
    assert s2.status == StepStatus.SKIPPED
    assert "manually SKIPPED" in s2.result_summary
    # Plan is now all-done (completed + skipped) → plan completed
    assert agent._current_plan.status == "completed"


def test_resume_step_restarts_the_clock():
    original_start = time.time() - 600
    s = ExecutionStep(id="s1", status=StepStatus.IN_PROGRESS,
                       started_at=original_start)
    agent = _make_agent_with_plan([s])
    agent.resume_step("s1")
    # started_at was bumped to ~now
    assert s.started_at > original_start + 500
    # Status unchanged
    assert s.status == StepStatus.IN_PROGRESS


def test_resume_step_on_completed_does_not_mutate():
    """resume on a COMPLETED step is a no-op (don't reset clock)."""
    s = ExecutionStep(id="s1", status=StepStatus.COMPLETED,
                       started_at=100.0, completed_at=200.0)
    agent = _make_agent_with_plan([s])
    agent.resume_step("s1")
    assert s.started_at == 100.0  # unchanged
    assert s.status == StepStatus.COMPLETED


# ─── end-to-end bug scenario ────────────────────────────────────────

def test_end_to_end_user_bug_scenario():
    """The exact scenario from the user's screenshot:
    - Step '生成PPTX格式报告' in_progress
    - Agent IDLE (the chat loop returned without complete_step)
    - Last tool event 10+ minutes ago

    Expected: detector flags it, UI gets a warning frame, human can
    pick mark_failed / skip / resume. After mark_failed, plan-in-context
    shows the failure so LLM replans on next turn.
    """
    from app.agent_types import AgentEvent
    s1 = ExecutionStep(id="s1", title="检查共享工作区已有文件",
                        status=StepStatus.COMPLETED,
                        result_summary="scan done")
    s2 = ExecutionStep(id="s2", title="基于最新2025-2026年数据优化报告内容",
                        status=StepStatus.COMPLETED,
                        result_summary="drafted")
    s3 = ExecutionStep(id="s3", title="生成PPTX格式报告",
                        status=StepStatus.IN_PROGRESS,
                        started_at=time.time() - 620,  # 10m ago
                        acceptance="report.pptx in workspace")
    agent = _make_agent_with_plan([s1, s2, s3])
    agent.status = AgentStatus.IDLE  # the bug condition
    agent.events = [AgentEvent(time.time() - 615, "tool_result",
                                 {"name": "edit_file"})]

    # Detector finds s3 stale
    bus = get_bus()
    sub = bus.subscribe(f"plan:{agent._current_plan.id}")
    try:
        stale = agent._detect_stale_plan_steps(emit_frames=True)
        assert len(stale) == 1
        assert stale[0]["step_id"] == "s3"
        # UI receives warning
        f = sub.next(timeout=1.0)
        assert f.kind == "step_stale"
        assert "PPTX" in f.data["title"]
    finally:
        bus.unsubscribe(sub)

    # Human clicks "mark failed"
    agent.mark_step_failed("s3", reason="agent hung 10 minutes")
    assert s3.status == StepStatus.FAILED

    # On next LLM turn, plan_state snapshot surfaces the failure
    snapshot = agent.format_plan_state_for_llm()
    assert "failed:" in snapshot
    assert "PPTX" in snapshot or "生成" in snapshot
    assert "manually marked FAILED" in s3.result_summary
