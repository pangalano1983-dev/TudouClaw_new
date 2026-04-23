"""Block 2 — end-to-end verify flow at the AGENT level.

Covers:
- plan_update(create_plan) with a step carrying verify config
- plan_update(complete_step) triggers the verifier
- Verifier PASS → step stays COMPLETED, response ok=True, verify attached
- Verifier FAIL → step rolled back to FAILED, result_summary gets verifier
  reason appended, response ok=False with hint to replan
- Plan state after verify fail: next plan_in_context snapshot shows
  the failure to LLM
- No verify config → existing behavior preserved (no regression)
- Verify crash doesn't kill the agent turn (defensive)
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
import pytest

from app.agent import Agent, StepStatus, ExecutionStep
from app import sandbox as _sandbox


def _make_agent_with_plan_support():
    """Same shim as test_plan_in_context — bypass heavy constructor."""
    agent = Agent.__new__(Agent)
    agent._current_plan = None
    agent.execution_plans = []
    agent._log = lambda *a, **kw: None
    agent._write_plan_to_memory = lambda *a, **kw: None
    agent._write_step_completion_to_memory = lambda *a, **kw: None
    agent._update_agent_phase = lambda: None
    # Needed by _run_step_verifier's llm_call bridge
    agent.id = "test-agent-1"
    agent.shared_workspace = ""
    agent.working_dir = ""
    # _resolve_effective_provider_model isn't available on the stub but
    # won't be called unless we use llm_judge verifier (which mocks llm_call).
    return agent


# ─── no-verify regression ──────────────────────────────────────────

def test_no_verify_config_preserves_existing_behavior():
    """Step with no verify → old flow (no extra fields in response)."""
    agent = _make_agent_with_plan_support()
    agent._handle_plan_update({
        "action": "create_plan",
        "task_summary": "t",
        "steps": [{"title": "do the thing", "acceptance": "file exists"}],
    })
    step_id = agent._current_plan.steps[0].id
    agent._handle_plan_update({"action": "start_step", "step_id": step_id})
    resp = json.loads(agent._handle_plan_update({
        "action": "complete_step", "step_id": step_id,
        "result_summary": "wrote /tmp/thing.txt (128 bytes), verified readable",
    }))
    assert resp["ok"] is True
    assert "verify" not in resp  # no verify was attached
    assert agent._current_plan.steps[0].status == StepStatus.COMPLETED


# ─── passing verify ────────────────────────────────────────────────

def test_passing_file_exists_verify_keeps_step_completed(tmp_path):
    """Step with verify → agent creates expected file → complete_step
    succeeds, verify=ok in response."""
    agent = _make_agent_with_plan_support()
    agent.working_dir = str(tmp_path)
    agent._handle_plan_update({
        "action": "create_plan",
        "task_summary": "generate report",
        "steps": [{
            "title": "Create report.md",
            "acceptance": "report.md exists in workspace",
            "verify": {
                "kind": "file_exists",
                "config": {"pattern": "report.md",
                           "newer_than_start": False},
            },
        }],
    })
    step_id = agent._current_plan.steps[0].id
    agent._handle_plan_update({"action": "start_step", "step_id": step_id})
    # Agent "produces" the expected file
    (tmp_path / "report.md").write_text("# report\nstuff happened")
    # Now claim completion
    resp = json.loads(agent._handle_plan_update({
        "action": "complete_step", "step_id": step_id,
        "result_summary": "created report.md in workspace (verified)",
    }))
    assert resp["ok"] is True, f"expected pass, got {resp}"
    assert "verify" in resp
    assert resp["verify"]["ok"] is True
    assert agent._current_plan.steps[0].status == StepStatus.COMPLETED


# ─── failing verify rolls back ──────────────────────────────────────

def test_failing_file_exists_verify_rolls_back_to_failed(tmp_path):
    """Agent claims complete but didn't actually produce the file →
    verifier fails → step → FAILED with verifier reason spliced into
    result_summary; response ok=False with replan hint."""
    agent = _make_agent_with_plan_support()
    agent.working_dir = str(tmp_path)
    agent._handle_plan_update({
        "action": "create_plan",
        "task_summary": "generate pptx",
        "steps": [{
            "title": "Create report.pptx",
            "acceptance": "report.pptx ≥ 1KB in workspace",
            "verify": {
                "kind": "file_exists",
                "config": {"pattern": "*.pptx",
                           "min_size_bytes": 1024,
                           "newer_than_start": False},
            },
        }],
    })
    step_id = agent._current_plan.steps[0].id
    agent._handle_plan_update({"action": "start_step", "step_id": step_id})
    # Agent didn't create any .pptx — claim done anyway
    resp = json.loads(agent._handle_plan_update({
        "action": "complete_step", "step_id": step_id,
        "result_summary": "created the pptx, all looks good",
    }))
    assert resp["ok"] is False
    assert "REJECTED by verifier" in resp["error"]
    assert resp["verify"]["ok"] is False
    assert "hint" in resp
    # Step is now FAILED on the plan
    step = agent._current_plan.steps[0]
    assert step.status == StepStatus.FAILED
    # Verifier reason is spliced into result_summary for LLM visibility
    assert "verifier:file_exists" in step.result_summary
    assert "expected ≥1" in step.result_summary or "expected" in step.result_summary


def test_failing_verify_keeps_plan_active_not_completed(tmp_path):
    """If the failing step was the last one, update_plan_step may have
    incorrectly marked plan=completed. Verifier rollback must undo that."""
    agent = _make_agent_with_plan_support()
    agent.working_dir = str(tmp_path)
    agent._handle_plan_update({
        "action": "create_plan",
        "task_summary": "t",
        "steps": [{
            "title": "single step",
            "acceptance": "some.txt exists",
            "verify": {
                "kind": "file_exists",
                "config": {"pattern": "some.txt",
                           "newer_than_start": False},
            },
        }],
    })
    step_id = agent._current_plan.steps[0].id
    agent._handle_plan_update({"action": "start_step", "step_id": step_id})
    # File not created
    resp = json.loads(agent._handle_plan_update({
        "action": "complete_step", "step_id": step_id,
        "result_summary": "done — file written",
    }))
    assert resp["ok"] is False
    assert agent._current_plan.status == "active"


# ─── verifier visible in plan-state (LLM context) ──────────────────

def test_failed_verify_shows_in_plan_state_snapshot(tmp_path):
    """After verify fail, format_plan_state_for_llm() must surface the
    failure so the next LLM turn sees it."""
    agent = _make_agent_with_plan_support()
    agent.working_dir = str(tmp_path)
    agent._handle_plan_update({
        "action": "create_plan",
        "task_summary": "produce report",
        "steps": [{
            "title": "Write report.md",
            "acceptance": "report.md exists",
            "verify": {
                "kind": "file_exists",
                "config": {"pattern": "report.md",
                           "newer_than_start": False},
            },
        }],
    })
    step_id = agent._current_plan.steps[0].id
    agent._handle_plan_update({"action": "start_step", "step_id": step_id})
    # Don't create the file
    agent._handle_plan_update({
        "action": "complete_step", "step_id": step_id,
        "result_summary": "wrote the report all good",
    })
    # Now check plan-in-context snapshot
    snapshot = agent.format_plan_state_for_llm()
    assert "failed:" in snapshot
    assert "Write report.md" in snapshot
    # The verifier reason should surface in the "error" line
    assert "verifier:file_exists" in snapshot or "expected" in snapshot


# ─── command verifier integration ──────────────────────────────────

def test_command_verifier_integration(tmp_path):
    """Command verifier runs and fails → step rolls back."""
    agent = _make_agent_with_plan_support()
    agent.working_dir = str(tmp_path)
    agent._handle_plan_update({
        "action": "create_plan",
        "task_summary": "validate",
        "steps": [{
            "title": "Check env",
            "acceptance": "FOO_REQUIRED is set",
            "verify": {
                "kind": "command",
                # This env var is not set — verifier will fail
                "config": {"command": "test -n \"$FOO_REQUIRED_NOT_SET\""},
            },
        }],
    })
    step_id = agent._current_plan.steps[0].id
    agent._handle_plan_update({"action": "start_step", "step_id": step_id})
    resp = json.loads(agent._handle_plan_update({
        "action": "complete_step", "step_id": step_id,
        "result_summary": "env set up properly, confirmed with test -n",
    }))
    assert resp["ok"] is False
    assert "REJECTED" in resp["error"]
    assert resp["verify"]["verifier_kind"] == "command"


# ─── verifier crash is non-fatal ───────────────────────────────────

def test_verifier_crash_does_not_kill_agent_turn(tmp_path, monkeypatch):
    """If the verifier itself throws, we still return a well-formed
    response (and step is rolled back since we can't prove success)."""
    from app import verifier as _vmod
    def _crasher(ctx, cfg):
        raise RuntimeError("verifier implementation bug")
    _vmod.register_verifier("test_will_crash", _crasher)
    try:
        agent = _make_agent_with_plan_support()
        agent._handle_plan_update({
            "action": "create_plan",
            "task_summary": "t",
            "steps": [{
                "title": "x", "acceptance": "y",
                "verify": {"kind": "test_will_crash"},
            }],
        })
        step_id = agent._current_plan.steps[0].id
        agent._handle_plan_update({"action": "start_step", "step_id": step_id})
        resp = json.loads(agent._handle_plan_update({
            "action": "complete_step", "step_id": step_id,
            "result_summary": "totally fine definitely done",
        }))
        # Verifier says not-ok (since it crashed), so step is failed
        assert resp["ok"] is False
        assert resp["verify"]["ok"] is False
    finally:
        _vmod._VERIFIER_REGISTRY.pop("test_will_crash", None)


# ─── ExecutionStep serialization ──────────────────────────────────

def test_execution_step_verify_field_roundtrips():
    step = ExecutionStep(
        title="x", acceptance="y",
        verify={"kind": "run_tests", "config": {"paths": "tests/"},
                "required": True},
    )
    d = step.to_dict()
    assert d["verify"]["kind"] == "run_tests"
    step2 = ExecutionStep.from_dict(d)
    assert step2.verify == step.verify


def test_legacy_step_no_verify_defaults_empty():
    """Old persisted steps have no 'verify' key — should read as {}."""
    step = ExecutionStep.from_dict({"title": "old-step", "acceptance": "x"})
    assert step.verify == {}


# ─── invalid verify config ──────────────────────────────────────────

def test_invalid_verify_config_surfaces_as_fail(tmp_path):
    """If verify dict is malformed (no kind), verifier returns structured
    failure rather than crashing the whole agent turn."""
    agent = _make_agent_with_plan_support()
    agent.working_dir = str(tmp_path)
    agent._handle_plan_update({
        "action": "create_plan",
        "task_summary": "t",
        "steps": [{
            "title": "x", "acceptance": "y",
            "verify": {"config": {"stuff": 1}},  # missing 'kind'
        }],
    })
    step_id = agent._current_plan.steps[0].id
    agent._handle_plan_update({"action": "start_step", "step_id": step_id})
    resp = json.loads(agent._handle_plan_update({
        "action": "complete_step", "step_id": step_id,
        "result_summary": "done with specifics from memory",
    }))
    assert resp["ok"] is False
    assert "invalid" in resp["verify"]["summary"].lower() or \
           "invalid" in resp["verify"].get("error", "").lower()
