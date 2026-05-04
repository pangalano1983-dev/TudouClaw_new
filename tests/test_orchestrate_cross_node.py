"""Tests for cross-node orchestrate (master → multiple nodes).

orchestrate(task, agent_ids) should run the task on every listed
agent in parallel, regardless of whether each agent lives on this
hub (local) or a remote worker. Each agent's result lands in the
returned dict under its agent_id key.

Local agents → ``supervisor.delegate``. Remote agents →
``proxy_chat_sync`` with X-Hub-Secret. Unknown agents → an error
string in the result so the caller can see what went wrong without
the whole call failing.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Local-only path — single-master invariant must stay intact
# ---------------------------------------------------------------------------


def test_orchestrate_local_only_default_targets():
    """No agent_ids → run on all LOCAL agents (preserves single-master)."""
    from app.hub._core import Hub

    hub = Hub.__new__(Hub)
    # Two local agents
    hub.agents = {"a1": MagicMock(), "a2": MagicMock()}
    hub.remote_nodes = {}
    hub.supervisor = MagicMock()
    hub.supervisor.delegate = MagicMock(side_effect=lambda aid, task, from_agent: f"local-{aid}")

    out = Hub.orchestrate(hub, "do thing")
    assert set(out.keys()) == {"a1", "a2"}
    assert out["a1"] == "local-a1"
    assert out["a2"] == "local-a2"


def test_orchestrate_explicit_agent_ids_local():
    """Explicit list of local agent_ids."""
    from app.hub._core import Hub

    hub = Hub.__new__(Hub)
    hub.agents = {"a1": MagicMock(), "a2": MagicMock(), "a3": MagicMock()}
    hub.remote_nodes = {}
    hub.supervisor = MagicMock()
    hub.supervisor.delegate = MagicMock(side_effect=lambda aid, task, from_agent: f"OK-{aid}")

    out = Hub.orchestrate(hub, "task-x", agent_ids=["a1", "a3"])
    # Only the requested ones, not a2
    assert set(out.keys()) == {"a1", "a3"}


# ---------------------------------------------------------------------------
# Remote path
# ---------------------------------------------------------------------------


def test_orchestrate_remote_agent_uses_proxy_chat_sync():
    """A remote agent_id triggers proxy_chat_sync to its node."""
    from app.hub._core import Hub
    from app.hub.types import RemoteNode

    hub = Hub.__new__(Hub)
    hub.agents = {}  # no local
    hub.remote_nodes = {
        "worker-01": RemoteNode(
            node_id="worker-01",
            name="W",
            url="http://w:9090",
            agents=[{"id": "remote_agent_xyz", "name": "scout"}],
            last_seen=1.0,
            secret="",
        ),
    }
    hub.supervisor = MagicMock()
    hub.find_agent_node = lambda aid: hub.remote_nodes["worker-01"] if aid == "remote_agent_xyz" else None
    hub.proxy_chat_sync = MagicMock(return_value="response from worker")

    out = Hub.orchestrate(hub, "do thing", agent_ids=["remote_agent_xyz"])

    assert out == {"remote_agent_xyz": "response from worker"}
    hub.proxy_chat_sync.assert_called_once()
    # Was called with (agent_id, node, task)
    call_args = hub.proxy_chat_sync.call_args
    assert call_args[0][0] == "remote_agent_xyz"
    assert call_args[0][1].node_id == "worker-01"
    assert call_args[0][2] == "do thing"


def test_orchestrate_mixed_local_and_remote():
    """A target list that mixes local + remote agents — both run."""
    from app.hub._core import Hub
    from app.hub.types import RemoteNode

    hub = Hub.__new__(Hub)
    hub.agents = {"local_a": MagicMock()}
    hub.remote_nodes = {
        "w-01": RemoteNode(
            node_id="w-01", name="W", url="http://w:9090",
            agents=[{"id": "remote_b", "name": "scout"}],
            last_seen=1.0, secret="",
        ),
    }
    hub.supervisor = MagicMock()
    hub.supervisor.delegate = MagicMock(return_value="LOCAL OUT")
    hub.find_agent_node = lambda aid: hub.remote_nodes["w-01"] if aid == "remote_b" else None
    hub.proxy_chat_sync = MagicMock(return_value="REMOTE OUT")

    out = Hub.orchestrate(hub, "task", agent_ids=["local_a", "remote_b"])
    assert out == {"local_a": "LOCAL OUT", "remote_b": "REMOTE OUT"}


def test_orchestrate_unknown_agent_returns_error_string():
    """Unknown agent_id doesn't crash — returns a marker string."""
    from app.hub._core import Hub

    hub = Hub.__new__(Hub)
    hub.agents = {}
    hub.remote_nodes = {}
    hub.supervisor = MagicMock()
    hub.find_agent_node = lambda aid: None

    out = Hub.orchestrate(hub, "task", agent_ids=["ghost"])
    assert "ghost" in out
    assert "not found" in out["ghost"].lower()


def test_orchestrate_remote_failure_isolated():
    """If one remote call raises, other agents still run + return."""
    from app.hub._core import Hub
    from app.hub.types import RemoteNode

    hub = Hub.__new__(Hub)
    hub.agents = {"local_a": MagicMock()}
    hub.remote_nodes = {
        "w": RemoteNode(node_id="w", name="W", url="http://w:9090",
                        agents=[{"id": "boom"}], last_seen=1.0, secret=""),
    }
    hub.supervisor = MagicMock()
    hub.supervisor.delegate = MagicMock(return_value="OK")
    hub.find_agent_node = lambda aid: hub.remote_nodes["w"] if aid == "boom" else None
    hub.proxy_chat_sync = MagicMock(side_effect=ValueError("network down"))

    out = Hub.orchestrate(hub, "task", agent_ids=["local_a", "boom"])
    assert out["local_a"] == "OK"
    assert "remote error" in out["boom"]
    assert "network down" in out["boom"]
