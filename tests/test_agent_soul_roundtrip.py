"""Regression — SOUL edit roundtrip.

Bug: GET /agent/{id}/soul returned the field as "soul" and called a
non-existent ``get_soul()`` method. Portal JS reads ``resp.soul_md``,
so it always saw undefined → loaded default template → users thought
edits "weren't taking effect".
"""
from __future__ import annotations

import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


class _FakeAgent:
    """Minimal Agent surface for the soul endpoints."""

    def __init__(self, aid="a-alice"):
        self.id = aid
        self.name = "Alice"
        self.role = "coder"
        self.soul_md = ""
        self.robot_avatar = ""
        self.system_prompt = ""
        self.messages = []

    def _build_system_prompt(self):
        return self.system_prompt or "(stub)"


class _FakeHub:
    def __init__(self):
        self.agents = {}

    def get_agent(self, aid):
        return self.agents.get(aid)

    def _save_agents(self):
        self._last_saved = list(self.agents.keys())


@pytest.fixture
def client(monkeypatch):
    from app.api.deps.auth import get_current_user, CurrentUser

    async def _fake_user():
        return CurrentUser(user_id="u", role="superAdmin")

    hub = _FakeHub()
    hub.agents["a-alice"] = _FakeAgent()

    from app.api.deps.hub import get_hub as _get_hub
    from app.api.routers import agents as ag_router

    app = FastAPI()
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[_get_hub] = lambda: hub
    app.include_router(ag_router.router)

    with TestClient(app) as tc:
        tc.hub = hub
        yield tc


# ── GET shape ─────────────────────────────────────────────


def test_get_soul_empty_returns_soul_md_key(client):
    r = client.get("/api/portal/agent/a-alice/soul")
    assert r.status_code == 200
    d = r.json()
    # New contract: JS reads `soul_md`.
    assert "soul_md" in d
    assert d["soul_md"] == ""
    # Back-compat legacy key still present.
    assert d["soul"] == ""
    assert d["role"] == "coder"
    assert "robot_avatar" in d


def test_get_soul_missing_agent_404(client):
    r = client.get("/api/portal/agent/does-not-exist/soul")
    assert r.status_code == 404


# ── POST then GET — core roundtrip ────────────────────────


def test_post_soul_then_get_returns_saved_value(client):
    # Save.
    content = "# 我是小艾\n\n我是一个 **资深后端工程师**，爱喝咖啡。"
    r1 = client.post("/api/portal/agent/a-alice/soul", json={
        "soul_md": content,
        "robot_avatar": "robot_coder",
    })
    assert r1.status_code == 200
    assert r1.json()["ok"] is True

    # Get.
    r2 = client.get("/api/portal/agent/a-alice/soul")
    d = r2.json()
    # THE CRITICAL ASSERTION — this was broken before the fix.
    assert d["soul_md"] == content
    assert d["robot_avatar"] == "robot_coder"


def test_post_soul_updates_underlying_agent(client):
    content = "fresh soul"
    client.post("/api/portal/agent/a-alice/soul", json={
        "soul_md": content,
    })
    agent = client.hub.agents["a-alice"]
    assert agent.soul_md == content
    assert agent.system_prompt == content


def test_empty_update_clears_soul(client):
    # Seed one.
    client.post("/api/portal/agent/a-alice/soul", json={"soul_md": "X"})
    assert client.hub.agents["a-alice"].soul_md == "X"
    # Overwrite with empty.
    client.post("/api/portal/agent/a-alice/soul", json={"soul_md": ""})
    r = client.get("/api/portal/agent/a-alice/soul")
    assert r.json()["soul_md"] == ""


def test_get_soul_exposes_role_for_default_template_loading(client):
    # JS uses `role` to fetch soul_{role}.md if soul_md is empty.
    r = client.get("/api/portal/agent/a-alice/soul")
    assert r.json()["role"] == "coder"
