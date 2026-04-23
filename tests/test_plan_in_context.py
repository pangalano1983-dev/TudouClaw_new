"""P0/P1 — Plan as first-class context.

Covers:
- ExecutionStep.acceptance ships through to_dict / from_dict round-trip
- ExecutionPlan.add_step accepts the acceptance kwarg
- format_plan_state_for_llm produces the stable <plan_state> block with
  current / done / pending / acceptance fields present
- _handle_plan_update(create_plan) passes acceptance to the plan
- _handle_plan_update(create_plan) warns on steps missing acceptance
- _handle_plan_update(complete_step) rejects short result_summary
- _handle_plan_update(complete_step) cites acceptance in the rejection
"""
from __future__ import annotations

import json
import time
import pytest
import types

from app.agent import (
    ExecutionPlan, ExecutionStep, StepStatus,
)


# ─── data model ──────────────────────────────────────────────────────

def test_acceptance_roundtrip():
    s = ExecutionStep(
        title="生成 PPTX 报告",
        acceptance="report.pptx ≥ 5 slides in $AGENT_WORKSPACE",
    )
    d = s.to_dict()
    assert d["acceptance"] == "report.pptx ≥ 5 slides in $AGENT_WORKSPACE"
    s2 = ExecutionStep.from_dict(d)
    assert s2.acceptance == s.acceptance


def test_acceptance_legacy_default_empty():
    """Old persisted plans have no acceptance field — should read as ''."""
    s = ExecutionStep.from_dict({"title": "legacy step"})
    assert s.acceptance == ""


def test_add_step_accepts_acceptance_kwarg():
    p = ExecutionPlan(task_summary="test")
    step = p.add_step(title="x", acceptance="must produce foo.txt")
    assert step.acceptance == "must produce foo.txt"


# ─── formatter ───────────────────────────────────────────────────────

def _stub_agent_with_plan(plan: ExecutionPlan):
    """Build a minimal shim exposing just format_plan_state_for_llm.

    Avoids the full Agent constructor (which needs hub/registry wiring)
    but reuses the real formatter method.
    """
    from app.agent import Agent
    shim = types.SimpleNamespace(_current_plan=plan)
    # Bind the unbound method to our shim
    shim.format_plan_state_for_llm = Agent.format_plan_state_for_llm.__get__(
        shim, type(shim)
    )
    return shim


def test_formatter_empty_plan_returns_empty_string():
    shim = _stub_agent_with_plan(ExecutionPlan(task_summary="nothing"))
    assert shim.format_plan_state_for_llm() == ""


def test_formatter_no_plan_returns_empty_string():
    shim = types.SimpleNamespace(_current_plan=None)
    from app.agent import Agent
    shim.format_plan_state_for_llm = Agent.format_plan_state_for_llm.__get__(
        shim, type(shim)
    )
    assert shim.format_plan_state_for_llm() == ""


def test_formatter_current_pending_done_partition():
    plan = ExecutionPlan(task_summary="Build a report")
    s1 = plan.add_step(title="search data", acceptance="≥3 sources")
    s2 = plan.add_step(title="build pptx", acceptance="report.pptx ≥ 5 slides")
    s3 = plan.add_step(title="send email", acceptance="message_id returned")
    s1.status = StepStatus.COMPLETED
    s1.result_summary = "found 4 sources"
    s2.status = StepStatus.IN_PROGRESS
    s2.started_at = time.time() - 10

    out = _stub_agent_with_plan(plan).format_plan_state_for_llm()
    assert "<plan_state>" in out and "</plan_state>" in out
    assert "task: Build a report" in out
    # Current section contains the in-progress step and its acceptance.
    assert "current:" in out
    assert "build pptx" in out
    assert "report.pptx ≥ 5 slides" in out
    # Done section lists the completed step.
    assert "done:" in out
    assert "search data" in out
    # Pending section includes the unstarted one.
    assert "pending:" in out
    assert "send email" in out
    # Rules are present when there's a current or pending step.
    assert "rules:" in out


def test_formatter_shows_acceptance_for_next_step_when_none_in_progress():
    """If no step is in_progress but pending exists, formatter tells the
    LLM which one to start — including its acceptance."""
    plan = ExecutionPlan(task_summary="t")
    s1 = plan.add_step(title="research", acceptance="≥3 sources")
    plan.add_step(title="write up", acceptance="draft.md present")
    s1.status = StepStatus.COMPLETED
    s1.result_summary = "ok"
    out = _stub_agent_with_plan(plan).format_plan_state_for_llm()
    assert "current: (none — next step to start)" in out
    assert "write up" in out
    assert "draft.md present" in out


def test_formatter_all_done_signals_wrap_up():
    plan = ExecutionPlan(task_summary="t")
    s = plan.add_step(title="x", acceptance="y")
    s.status = StepStatus.COMPLETED
    s.result_summary = "ok"
    out = _stub_agent_with_plan(plan).format_plan_state_for_llm()
    assert "all steps done" in out


def test_formatter_truncates_long_lines():
    plan = ExecutionPlan(task_summary="t" * 300)  # long task
    plan.add_step(title="s" * 200, acceptance="a" * 400)
    out = _stub_agent_with_plan(plan).format_plan_state_for_llm()
    # No line in the output should be absurdly long (the formatter
    # truncates to ~140 chars for acceptance, ~60 for titles).
    for line in out.splitlines():
        assert len(line) < 250, f"line too long: {line[:80]}..."


# ─── _handle_plan_update integration ─────────────────────────────────

def _make_agent_with_plan_support():
    """Construct a FakeAgent implementing just enough of Agent to exercise
    _handle_plan_update without touching the hub/registry constructor."""
    from app.agent import Agent
    agent = Agent.__new__(Agent)  # bypass __init__
    agent._current_plan = None
    agent.execution_plans = []
    # Stubs for side effects _handle_plan_update triggers
    agent._log = lambda *args, **kwargs: None
    agent._write_plan_to_memory = lambda *_a, **_kw: None
    agent._write_step_completion_to_memory = lambda *_a, **_kw: None
    agent._update_agent_phase = lambda: None
    return agent


def test_create_plan_stores_acceptance():
    agent = _make_agent_with_plan_support()
    resp = json.loads(agent._handle_plan_update({
        "action": "create_plan",
        "task_summary": "generate report",
        "steps": [
            {"title": "search", "acceptance": "≥3 sources"},
            {"title": "write pptx", "acceptance": "report.pptx ≥5 slides"},
        ],
    }))
    assert resp["ok"] is True
    assert "warning" not in resp
    # The plan is now in agent._current_plan — verify acceptance persisted
    assert agent._current_plan is not None
    assert len(agent._current_plan.steps) == 2
    assert agent._current_plan.steps[0].acceptance == "≥3 sources"
    assert agent._current_plan.steps[1].acceptance == "report.pptx ≥5 slides"


def test_create_plan_warns_on_missing_acceptance():
    agent = _make_agent_with_plan_support()
    resp = json.loads(agent._handle_plan_update({
        "action": "create_plan",
        "task_summary": "t",
        "steps": [
            {"title": "vague step"},  # missing acceptance
            {"title": "another", "acceptance": "ok"},
        ],
    }))
    assert resp["ok"] is True  # not fatal — plan still created
    assert "warning" in resp
    assert "acceptance" in resp["warning"]


def test_complete_step_rejects_empty_result_summary():
    agent = _make_agent_with_plan_support()
    agent._handle_plan_update({
        "action": "create_plan",
        "task_summary": "t",
        "steps": [{"title": "do the thing", "acceptance": "file.txt exists"}],
    })
    step_id = agent._current_plan.steps[0].id

    resp = json.loads(agent._handle_plan_update({
        "action": "complete_step",
        "step_id": step_id,
        "result_summary": "done",  # too short
    }))
    assert resp["ok"] is False
    assert "result_summary is too short" in resp["error"]
    # Must also cite the acceptance so the LLM knows what evidence to provide
    assert "file.txt exists" in resp["error"]


def test_complete_step_accepts_real_summary():
    agent = _make_agent_with_plan_support()
    agent._handle_plan_update({
        "action": "create_plan",
        "task_summary": "t",
        "steps": [{"title": "build file", "acceptance": "file.txt exists"}],
    })
    step_id = agent._current_plan.steps[0].id
    agent._handle_plan_update({
        "action": "start_step", "step_id": step_id,
    })
    resp = json.loads(agent._handle_plan_update({
        "action": "complete_step",
        "step_id": step_id,
        "result_summary": "wrote /tmp/file.txt (128 bytes) — verified readable",
    }))
    assert resp["ok"] is True
    assert agent._current_plan.steps[0].status == StepStatus.COMPLETED


def test_fail_step_also_requires_summary():
    """Same guard on fail_step — users shouldn't blank-label failures either."""
    agent = _make_agent_with_plan_support()
    agent._handle_plan_update({
        "action": "create_plan",
        "task_summary": "t",
        "steps": [{"title": "x", "acceptance": "y"}],
    })
    step_id = agent._current_plan.steps[0].id
    resp = json.loads(agent._handle_plan_update({
        "action": "fail_step",
        "step_id": step_id,
        "result_summary": "err",  # too short
    }))
    assert resp["ok"] is False
    assert "too short" in resp["error"]
