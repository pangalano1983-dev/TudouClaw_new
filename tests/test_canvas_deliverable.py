"""Tests for the canvas-executor deliverable variable contract.

Companion to docs/superpowers/specs/2026-05-02-canvas-deliverable-design.md.
"""
from __future__ import annotations
import time
from pathlib import Path
from unittest.mock import MagicMock

from app import canvas_artifacts as ca
from app import canvas_executor as ce
from app.canvas_executor import WorkflowEngine, WorkflowRun, RunState


def test_outputs_dict_has_deliverable_no_legacy_keys(tmp_path, monkeypatch):
    """Behavior test: outputs returned by _exec_agent contain
    `deliverable` and `deliverable_relative` but NOT the legacy
    `deliverable_type` or `success_marker_file` keys.

    Drives _exec_agent end-to-end with a mocked agent + chat_async to
    verify the actual returned dict shape — not just source-grep.
    """
    # Reset + init artifact store at tmp dir so each test is hermetic.
    monkeypatch.setattr(ca, "_STORE", None)
    ca.init_store(tmp_path)
    store = ca.get_store()

    # Build a minimal Run + WorkflowEngine mock
    run = WorkflowRun(
        id="run-test",
        workflow_id="wf-test",
        workflow_name="t",
        state=RunState.RUNNING,
        started_at=time.time(),
    )
    engine = MagicMock(spec=WorkflowEngine)
    engine.hub = MagicMock()
    engine.artifact_store = store

    # Fake task: COMPLETED, with simple result.
    fake_task = MagicMock()
    from app.chat_task import ChatTaskStatus
    fake_task.status = ChatTaskStatus.COMPLETED
    fake_task.id = "fake-task-id"
    fake_task.result = "fake reply"
    fake_task.created_at = time.time()
    fake_task.updated_at = time.time()
    fake_task.error = None

    fake_agent = MagicMock()
    fake_agent.id = "ag-x"
    fake_agent.name = "test-agent"
    fake_agent._lock = MagicMock()
    fake_agent._lock.__enter__ = MagicMock(return_value=None)
    fake_agent._lock.__exit__ = MagicMock(return_value=None)
    fake_agent._active_context_id = "solo"
    fake_agent._messages_by_context = {}
    fake_agent._switch_context = MagicMock()
    fake_agent.working_dir = ""

    # chat_async writes a real file into the per-node subdir that the
    # executor sets via agent.working_dir BEFORE this is called. This
    # also keeps the test valid once Task 3's EMPTY_DELIVERABLE check
    # lands.
    def fake_chat_async(prompt, source=""):
        Path(fake_agent.working_dir, "x.txt").write_text("y")
        return fake_task

    fake_agent.chat_async = fake_chat_async
    engine.hub.get_agent = MagicMock(return_value=fake_agent)

    node = {"id": "n1", "label": "test", "type": "agent", "config": {
        "agent_id": "ag-x", "prompt": "go", "timeout": 5,
    }}

    outputs = ce._exec_agent(engine, run, node, node["config"])

    assert "deliverable" in outputs
    assert "deliverable_relative" in outputs
    assert "deliverable_type" not in outputs
    assert "success_marker_file" not in outputs
