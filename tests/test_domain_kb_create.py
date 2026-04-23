"""Regression — /api/portal/domain-kb/create must actually create.

Bug: the old endpoint only created when ``hub.create_domain_knowledge_base``
existed, which it never did. It silently returned ``{"ok": True}`` → UI
thought success but nothing was persisted.

This test:
  * POSTs to /create with a new KB name
  * asserts 200 + "knowledge_base" in response
  * calls the direct store API → new KB is actually there
  * /list returns it
"""
from __future__ import annotations

import os
import sys
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Redirect data dir so the test doesn't touch the real store file.
    monkeypatch.setenv("TUDOU_CLAW_DATA_DIR", str(tmp_path))
    # Force a fresh store singleton.
    import app.rag_provider as rp
    # Reset the file path to tmp.
    new_file = tmp_path / "domain_knowledge_bases.json"
    monkeypatch.setattr(rp, "_DOMAIN_KB_FILE", new_file)
    # Force-rebuild singleton.
    if hasattr(rp, "_domain_kb_store_singleton"):
        monkeypatch.setattr(rp, "_domain_kb_store_singleton", None)

    # Minimal FastAPI app hosting just the knowledge router.
    from app.api.deps.auth import get_current_user, CurrentUser

    async def _fake_user():
        return CurrentUser(user_id="u", role="superAdmin")

    class _FakeHub:
        """Hub stub without create_domain_knowledge_base — must route
        through store directly. This mirrors the real hub."""
        agents: dict = {}

    from app.api.routers import knowledge as kn_router
    app = FastAPI()
    app.dependency_overrides[get_current_user] = _fake_user

    # knowledge router expects `hub=Depends(get_hub)`; override with our stub.
    from app.api.deps.hub import get_hub as _get_hub
    app.dependency_overrides[_get_hub] = lambda: _FakeHub()
    app.include_router(kn_router.router)

    with TestClient(app) as tc:
        yield tc


def test_create_domain_kb_actually_persists(client):
    r = client.post(
        "/api/portal/domain-kb/create",
        json={"name": "法律知识库", "description": "法规条款",
              "tags": ["compliance", "legal"]},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] is True
    assert "knowledge_base" in d, "create must return the new KB payload"
    kb = d["knowledge_base"]
    assert kb["name"] == "法律知识库"
    assert kb["id"].startswith("dkb_")
    assert "collection" in kb

    # Confirm: store actually has it.
    from app.rag_provider import get_domain_kb_store
    store = get_domain_kb_store()
    stored_ids = [k.id for k in store.list_all()]
    assert kb["id"] in stored_ids


def test_create_missing_name_returns_400(client):
    r = client.post(
        "/api/portal/domain-kb/create",
        json={"description": "no name"},
    )
    assert r.status_code == 400


def test_list_returns_kbs_after_create(client):
    client.post(
        "/api/portal/domain-kb/create",
        json={"name": "A"},
    )
    client.post(
        "/api/portal/domain-kb/create",
        json={"name": "B"},
    )
    r = client.post("/api/portal/domain-kb/list", json={})
    assert r.status_code == 200
    names = [k["name"] for k in r.json()["knowledge_bases"]]
    assert "A" in names
    assert "B" in names


def test_tags_are_cleaned(client):
    r = client.post(
        "/api/portal/domain-kb/create",
        json={"name": "T", "tags": ["x", "  y  ", "", "z"]},
    )
    assert r.status_code == 200
    kb = r.json()["knowledge_base"]
    # Empty strings dropped, whitespace stripped.
    assert "y" in kb["tags"]
    assert "" not in kb["tags"]


def test_tags_non_list_is_ignored(client):
    r = client.post(
        "/api/portal/domain-kb/create",
        json={"name": "NT", "tags": "not a list"},
    )
    assert r.status_code == 200
    assert r.json()["knowledge_base"]["tags"] == []
