"""Block 3 Day 6 — checkpoint REST endpoints."""
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


from app import checkpoint as ckpt  # noqa: E402


@pytest.fixture
def client(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="ckpt_api_")
    monkeypatch.setenv("TUDOU_CLAW_DATA_DIR", tmpdir)
    ckpt.reset_store_for_test()
    store = ckpt.get_store(db_path=os.path.join(tmpdir, "ckpt.db"))

    from app.api.deps.auth import get_current_user, CurrentUser

    async def _fake_user():
        return CurrentUser(user_id="u", role="superAdmin")

    from app.api.routers import checkpoints as ckpt_router
    app = FastAPI()
    app.dependency_overrides[get_current_user] = _fake_user
    app.include_router(ckpt_router.router)

    with TestClient(app) as tc:
        tc.store = store
        yield tc

    ckpt.reset_store_for_test()


# ── list ───────────────────────────────────────────────────────────


def test_list_by_agent_id(client):
    c1 = client.store.save(agent_id="alice", plan_json={"v": 1})
    c2 = client.store.save(agent_id="alice", plan_json={"v": 2})
    client.store.save(agent_id="bob", plan_json={"v": 3})
    r = client.get("/api/portal/checkpoint/list",
                   params={"agent_id": "alice"})
    assert r.status_code == 200
    d = r.json()
    assert d["count"] == 2
    ids = [c["id"] for c in d["checkpoints"]]
    assert c2 in ids and c1 in ids


def test_list_by_scope_and_scope_id(client):
    client.store.save(agent_id="x", plan_json={},
                      scope=ckpt.SCOPE_MEETING, scope_id="m1")
    client.store.save(agent_id="y", plan_json={},
                      scope=ckpt.SCOPE_MEETING, scope_id="m2")
    r = client.get("/api/portal/checkpoint/list",
                   params={"scope": "meeting", "scope_id": "m1"})
    assert r.status_code == 200
    assert r.json()["count"] == 1


def test_list_filter_by_status(client):
    a = client.store.save(agent_id="alice", plan_json={})
    client.store.save(agent_id="alice", plan_json={})
    client.store.mark_restored(a)
    r = client.get("/api/portal/checkpoint/list",
                   params={"agent_id": "alice",
                           "status": ckpt.STATUS_RESTORED})
    assert r.json()["count"] == 1


def test_list_without_filter_rejected(client):
    r = client.get("/api/portal/checkpoint/list")
    assert r.status_code == 400


def test_list_respects_limit(client):
    for _ in range(8):
        client.store.save(agent_id="alice", plan_json={})
    r = client.get("/api/portal/checkpoint/list",
                   params={"agent_id": "alice", "limit": 3})
    assert r.json()["count"] == 3


# ── single-row GET ─────────────────────────────────────────────────


def test_get_checkpoint_roundtrips(client):
    cid = client.store.save(
        agent_id="alice",
        plan_json={"task_summary": "build",
                   "steps": [{"id": "s1", "title": "code"}]},
    )
    r = client.get(f"/api/portal/checkpoint/{cid}")
    assert r.status_code == 200
    d = r.json()
    assert d["id"] == cid
    assert d["agent_id"] == "alice"
    assert d["plan_json"]["task_summary"] == "build"


def test_get_checkpoint_missing_returns_404(client):
    r = client.get("/api/portal/checkpoint/ckpt_does_not_exist")
    assert r.status_code == 404


# ── digest ─────────────────────────────────────────────────────────


def test_digest_returns_computed_when_not_stored(client):
    cid = client.store.save(agent_id="alice",
                            plan_json={"steps": [
                                {"id": "s1", "title": "read",
                                 "status": "completed", "order": 0},
                            ]})
    r = client.get(f"/api/portal/checkpoint/{cid}/digest")
    assert r.status_code == 200
    d = r.json()
    assert d["source"] == "computed"
    assert "已完成" in d["text"]
    assert d["token_estimate"] > 0


def test_digest_returns_stored_when_present(client):
    cid = client.store.save(agent_id="alice", plan_json={})
    client.store.update_digest(cid, "PRECOMPUTED-SUMMARY")
    r = client.get(f"/api/portal/checkpoint/{cid}/digest")
    d = r.json()
    assert d["source"] == "stored"
    assert d["text"] == "PRECOMPUTED-SUMMARY"


def test_digest_use_stored_false_recomputes(client):
    cid = client.store.save(agent_id="alice", plan_json={})
    client.store.update_digest(cid, "PRECOMPUTED")
    r = client.get(f"/api/portal/checkpoint/{cid}/digest",
                   params={"use_stored": "false"})
    d = r.json()
    assert d["source"] == "computed"
    assert "PRECOMPUTED" not in d["text"]


def test_digest_missing_404(client):
    r = client.get("/api/portal/checkpoint/ckpt_missing/digest")
    assert r.status_code == 404


def test_digest_rebuild_writes_back(client):
    cid = client.store.save(agent_id="alice",
                            plan_json={"steps": [
                                {"id": "s1", "title": "x",
                                 "status": "completed", "order": 0},
                            ]})
    r = client.post(f"/api/portal/checkpoint/{cid}/digest/rebuild",
                    json={"token_budget": 3000})
    assert r.status_code == 200
    d = r.json()
    assert d["checkpoint_id"] == cid
    # Row now has a digest stored.
    reloaded = client.store.load(cid)
    assert reloaded.digest == d["text"]


# ── restore / archive ──────────────────────────────────────────────


def test_restore_marks_status_and_returns_digest(client):
    cid = client.store.save(agent_id="alice",
                            plan_json={"steps": [
                                {"id": "s1", "title": "pending work",
                                 "status": "in_progress", "order": 0,
                                 "acceptance": "tests pass"},
                            ]})
    r = client.post(f"/api/portal/checkpoint/{cid}/restore")
    assert r.status_code == 200
    d = r.json()
    assert d["checkpoint_id"] == cid
    assert d["agent_id"] == "alice"
    assert "待完成" in d["digest"]
    # Row transitioned.
    assert client.store.load(cid).status == ckpt.STATUS_RESTORED


def test_restore_missing_404(client):
    r = client.post("/api/portal/checkpoint/ckpt_missing/restore")
    assert r.status_code == 404


def test_archive_transitions_state(client):
    cid = client.store.save(agent_id="alice", plan_json={})
    r = client.post(f"/api/portal/checkpoint/{cid}/archive")
    assert r.status_code == 200
    assert client.store.load(cid).status == ckpt.STATUS_ARCHIVED


def test_archive_missing_404(client):
    r = client.post("/api/portal/checkpoint/ckpt_missing/archive")
    assert r.status_code == 404


# ── stats ──────────────────────────────────────────────────────────


def test_stats_endpoint(client):
    client.store.save(agent_id="alice", plan_json={})
    client.store.save(agent_id="alice", plan_json={},
                      scope=ckpt.SCOPE_MEETING, scope_id="m1")
    r = client.get("/api/portal/checkpoint/stats")
    d = r.json()
    assert d["total"] == 2
    assert d["by_scope"].get("agent", 0) == 1
    assert d["by_scope"].get("meeting", 0) == 1
