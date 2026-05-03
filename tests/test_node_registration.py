"""Tests for the worker-node ↔ master registration MVP.

Covers:
  - Boot-time POST /api/hub/register from a downstream node
  - X-Hub-Secret authentication on /register and /heartbeat
  - Heartbeat auto-upserts a node the master doesn't know about
  - Worker-node JWT downgrade superAdmin → admin

These tests run against a fresh FastAPI app + isolated tmp data dir
so they never touch the operator's real ~/.tudou_claw.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_data_dir(tmp_path, monkeypatch):
    """Fresh data dir, no upstream hub configured (= master mode)."""
    monkeypatch.setenv("TUDOU_CLAW_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("TUDOU_CLAW_HOME", raising=False)
    monkeypatch.delenv("TUDOU_UPSTREAM_HUB", raising=False)
    monkeypatch.delenv("TUDOU_UPSTREAM_SECRET", raising=False)
    monkeypatch.delenv("TUDOU_NODE_URL", raising=False)
    return tmp_path


# ---------------------------------------------------------------------------
# /register endpoint — auth + behaviour
# ---------------------------------------------------------------------------


def test_register_requires_secret_when_master_has_one(isolated_data_dir, monkeypatch):
    """When master has TUDOU_SECRET set, /register without X-Hub-Secret is 401."""
    from fastapi.testclient import TestClient
    from fastapi import FastAPI

    monkeypatch.setenv("TUDOU_SECRET", "master-secret-xyz")
    # Re-init auth singleton so it picks up the env var.
    from app.auth import init_auth
    init_auth(data_dir=str(isolated_data_dir), shared_secret="master-secret-xyz")

    from app.api.routers import hub_sync
    from app.api.deps.hub import get_hub
    fake_hub = MagicMock()
    fake_hub.register_node = MagicMock(return_value=None)
    fake_hub.remote_nodes = {}

    app = FastAPI()
    app.dependency_overrides[get_hub] = lambda: fake_hub
    app.include_router(hub_sync.router)
    client = TestClient(app)

    # No X-Hub-Secret → 401
    r = client.post("/api/hub/register", json={"node_id": "n1", "endpoint": "http://n1:9090"})
    assert r.status_code == 401, r.text

    # Wrong secret → 401
    r = client.post(
        "/api/hub/register",
        json={"node_id": "n1", "endpoint": "http://n1:9090"},
        headers={"X-Hub-Secret": "wrong"},
    )
    assert r.status_code == 401

    # Correct secret → 200 + register_node called
    r = client.post(
        "/api/hub/register",
        json={"node_id": "n1", "endpoint": "http://n1:9090", "name": "Node One"},
        headers={"X-Hub-Secret": "master-secret-xyz"},
    )
    assert r.status_code == 200, r.text
    fake_hub.register_node.assert_called_once()
    kwargs = fake_hub.register_node.call_args.kwargs
    assert kwargs["node_id"] == "n1"
    assert kwargs["url"] == "http://n1:9090"
    assert kwargs["name"] == "Node One"


def test_register_dev_mode_when_master_has_no_secret(isolated_data_dir, monkeypatch):
    """If master never set TUDOU_SECRET, calls go through (dev mode)."""
    from fastapi.testclient import TestClient
    from fastapi import FastAPI

    monkeypatch.delenv("TUDOU_SECRET", raising=False)
    from app.auth import init_auth
    init_auth(data_dir=str(isolated_data_dir), shared_secret="")

    from app.api.routers import hub_sync
    from app.api.deps.hub import get_hub
    fake_hub = MagicMock()
    fake_hub.register_node = MagicMock(return_value=None)
    fake_hub.remote_nodes = {}

    app = FastAPI()
    app.dependency_overrides[get_hub] = lambda: fake_hub
    app.include_router(hub_sync.router)
    client = TestClient(app)

    r = client.post(
        "/api/hub/register",
        json={"node_id": "n2", "endpoint": "http://n2:9090"},
    )
    assert r.status_code == 200
    fake_hub.register_node.assert_called_once()


def test_register_rejects_missing_node_id(isolated_data_dir, monkeypatch):
    """node_id is required."""
    from fastapi.testclient import TestClient
    from fastapi import FastAPI

    monkeypatch.delenv("TUDOU_SECRET", raising=False)
    from app.auth import init_auth
    init_auth(data_dir=str(isolated_data_dir), shared_secret="")

    from app.api.routers import hub_sync
    from app.api.deps.hub import get_hub
    fake_hub = MagicMock()
    fake_hub.remote_nodes = {}

    app = FastAPI()
    app.dependency_overrides[get_hub] = lambda: fake_hub
    app.include_router(hub_sync.router)
    client = TestClient(app)

    r = client.post("/api/hub/register", json={"endpoint": "http://x:9090"})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# /heartbeat endpoint — bumps last_seen, auto-upserts unknown nodes
# ---------------------------------------------------------------------------


def test_heartbeat_bumps_last_seen_for_known_node(isolated_data_dir, monkeypatch):
    """Heartbeat from a known node updates its last_seen."""
    from fastapi.testclient import TestClient
    from fastapi import FastAPI

    monkeypatch.delenv("TUDOU_SECRET", raising=False)
    from app.auth import init_auth
    init_auth(data_dir=str(isolated_data_dir), shared_secret="")

    from app.api.routers import hub_sync
    from app.api.deps.hub import get_hub

    # Existing node with stale last_seen.
    existing = MagicMock()
    existing.last_seen = 100.0
    existing.name = "Old Name"
    fake_hub = MagicMock()
    fake_hub.remote_nodes = {"n3": existing}
    fake_hub.register_node = MagicMock()

    app = FastAPI()
    app.dependency_overrides[get_hub] = lambda: fake_hub
    app.include_router(hub_sync.router)
    client = TestClient(app)

    r = client.post(
        "/api/hub/heartbeat",
        json={"node_id": "n3", "name": "Updated Name"},
    )
    assert r.status_code == 200, r.text
    # last_seen should be bumped to now (much greater than 100.0).
    assert existing.last_seen > 1000.0
    # Should NOT have re-registered (already known).
    fake_hub.register_node.assert_not_called()
    # Name updates from heartbeat (cheap to update, useful when
    # operator renames on the node side).
    assert existing.name == "Updated Name"


def test_heartbeat_auto_upserts_unknown_node(isolated_data_dir, monkeypatch):
    """First heartbeat from an unknown node triggers register fallback."""
    from fastapi.testclient import TestClient
    from fastapi import FastAPI

    monkeypatch.delenv("TUDOU_SECRET", raising=False)
    from app.auth import init_auth
    init_auth(data_dir=str(isolated_data_dir), shared_secret="")

    from app.api.routers import hub_sync
    from app.api.deps.hub import get_hub

    fake_hub = MagicMock()
    fake_hub.remote_nodes = {}  # empty — master forgot about us
    fake_hub.register_node = MagicMock()

    app = FastAPI()
    app.dependency_overrides[get_hub] = lambda: fake_hub
    app.include_router(hub_sync.router)
    client = TestClient(app)

    r = client.post(
        "/api/hub/heartbeat",
        json={
            "node_id": "n4",
            "name": "Recovered Node",
            "url": "http://n4:9090",
        },
    )
    assert r.status_code == 200
    # Auto-recovered via register_node.
    fake_hub.register_node.assert_called_once()
    kwargs = fake_hub.register_node.call_args.kwargs
    assert kwargs["node_id"] == "n4"
    assert kwargs["name"] == "Recovered Node"
    assert kwargs["url"] == "http://n4:9090"


def test_heartbeat_requires_node_id(isolated_data_dir, monkeypatch):
    from fastapi.testclient import TestClient
    from fastapi import FastAPI

    monkeypatch.delenv("TUDOU_SECRET", raising=False)
    from app.auth import init_auth
    init_auth(data_dir=str(isolated_data_dir), shared_secret="")

    from app.api.routers import hub_sync
    from app.api.deps.hub import get_hub
    fake_hub = MagicMock()
    fake_hub.remote_nodes = {}

    app = FastAPI()
    app.dependency_overrides[get_hub] = lambda: fake_hub
    app.include_router(hub_sync.router)
    client = TestClient(app)

    r = client.post("/api/hub/heartbeat", json={})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Worker-node identity + role cap
# ---------------------------------------------------------------------------


def test_is_worker_node_property():
    """Hub exposes is_worker_node based on TUDOU_UPSTREAM_HUB."""
    from app.api.deps.auth import _cap_role_for_worker_node

    # Not a worker → role unchanged
    fake_hub = MagicMock()
    fake_hub.is_worker_node = False
    with patch("app.api.deps.hub.get_hub", return_value=fake_hub):
        assert _cap_role_for_worker_node("superAdmin") == "superAdmin"
        assert _cap_role_for_worker_node("admin") == "admin"

    # Worker → superAdmin downgraded
    fake_hub.is_worker_node = True
    with patch("app.api.deps.hub.get_hub", return_value=fake_hub):
        assert _cap_role_for_worker_node("superAdmin") == "admin"
        # Other roles untouched
        assert _cap_role_for_worker_node("admin") == "admin"
        assert _cap_role_for_worker_node("user") == "user"


def test_cap_safe_when_hub_uninitialised():
    """During early startup the hub may not be ready — cap is a no-op."""
    from app.api.deps.auth import _cap_role_for_worker_node

    with patch(
        "app.api.deps.hub.get_hub",
        side_effect=RuntimeError("hub not ready"),
    ):
        # Should not raise; should return role unchanged.
        assert _cap_role_for_worker_node("superAdmin") == "superAdmin"
