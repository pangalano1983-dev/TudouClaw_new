"""Block 3 Day 8 — checkpoint resume injection tests.

Covers:
  * set_metadata_flag write + read roundtrip
  * consume_pending_resume returns the checkpoint AND flips the flag
  * consume_pending_resume is exactly-once under repeated calls
  * Agent._build_resume_digest_context wraps the digest correctly
  * REST /restore flips the pending flag (observable via store.load)
"""
from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


from app import checkpoint as ckpt  # noqa: E402


class _StubAgent:
    """Minimal surface — mirrors test_agent_inbox_pull pattern."""
    def __init__(self, aid: str):
        self.id = aid
        self.messages: list = []
        self.logs: list = []

    def _log(self, kind, payload):
        self.logs.append((kind, payload))


def _attach_resume_method():
    from app.agent import Agent as _Agent
    _StubAgent._build_resume_digest_context = _Agent._build_resume_digest_context


@pytest.fixture
def store(tmp_path, monkeypatch):
    ckpt.reset_store_for_test()
    db = tmp_path / "ckpt.db"
    monkeypatch.setenv("TUDOU_CLAW_DATA_DIR", str(tmp_path))
    s = ckpt.get_store(db_path=str(db))
    yield s
    ckpt.reset_store_for_test()


# ── metadata flag ──────────────────────────────────────────────────


def test_set_metadata_flag_merges(store):
    cid = store.save(agent_id="a", plan_json={},
                     metadata={"existing": "keep"})
    assert store.set_metadata_flag(cid, "new_flag", True) is True
    c = store.load(cid)
    assert c.metadata["existing"] == "keep"
    assert c.metadata["new_flag"] is True


def test_set_metadata_flag_unknown_returns_false(store):
    assert store.set_metadata_flag("ckpt_nope", "x", 1) is False


# ── consume_pending_resume ─────────────────────────────────────────


def test_consume_returns_none_when_nothing_pending(store):
    assert store.consume_pending_resume("a") is None


def test_consume_returns_none_when_no_pending_flag(store):
    cid = store.save(agent_id="a", plan_json={})
    store.mark_restored(cid)
    # pending flag never set → still no delivery.
    assert store.consume_pending_resume("a") is None


def test_consume_flips_flag_and_returns_checkpoint(store):
    cid = store.save(agent_id="a", plan_json={"task_summary": "build"})
    store.mark_restored(cid)
    store.set_metadata_flag(cid, "pending_chat_delivery", True)

    c = store.consume_pending_resume("a")
    assert c is not None
    assert c.id == cid
    # After consume: flag is False + delivered_at set.
    after = store.load(cid)
    assert after.metadata.get("pending_chat_delivery") is False
    assert after.metadata.get("delivered_at", 0) > 0


def test_consume_is_exactly_once(store):
    cid = store.save(agent_id="a", plan_json={})
    store.mark_restored(cid)
    store.set_metadata_flag(cid, "pending_chat_delivery", True)
    first = store.consume_pending_resume("a")
    assert first is not None
    second = store.consume_pending_resume("a")
    assert second is None


def test_consume_picks_most_recent_pending(store):
    old = store.save(agent_id="a", plan_json={})
    store.mark_restored(old)
    store.set_metadata_flag(old, "pending_chat_delivery", True)
    import time
    time.sleep(0.01)
    new = store.save(agent_id="a", plan_json={})
    store.mark_restored(new)
    store.set_metadata_flag(new, "pending_chat_delivery", True)
    picked = store.consume_pending_resume("a")
    assert picked.id == new


def test_consume_isolates_agents(store):
    cid_a = store.save(agent_id="alice", plan_json={})
    store.mark_restored(cid_a)
    store.set_metadata_flag(cid_a, "pending_chat_delivery", True)
    # Bob sees nothing; Alice still has hers pending.
    assert store.consume_pending_resume("bob") is None
    assert store.consume_pending_resume("alice").id == cid_a


# ── Agent._build_resume_digest_context ─────────────────────────────


def test_resume_context_empty_when_nothing_pending(store):
    _attach_resume_method()
    a = _StubAgent("no-one")
    ctx, cid = a._build_resume_digest_context()
    assert ctx is None
    assert cid == ""


def test_resume_context_wraps_digest(store):
    _attach_resume_method()
    cid = store.save(
        agent_id="a",
        plan_json={"task_summary": "build report",
                   "steps": [{"id": "s1", "title": "read",
                              "status": "completed", "order": 0}]},
    )
    store.mark_restored(cid)
    store.set_metadata_flag(cid, "pending_chat_delivery", True)

    a = _StubAgent("a")
    ctx, returned_id = a._build_resume_digest_context()
    assert returned_id == cid
    assert ctx is not None
    assert "<checkpoint_resume>" in ctx
    assert "</checkpoint_resume>" in ctx
    assert cid in ctx
    # Built digest mentions the completed step.
    assert "已完成" in ctx or "read" in ctx


def test_resume_context_prefers_stored_digest(store):
    _attach_resume_method()
    cid = store.save(agent_id="a", plan_json={})
    store.update_digest(cid, "MY-CACHED-DIGEST-TEXT")
    store.mark_restored(cid)
    store.set_metadata_flag(cid, "pending_chat_delivery", True)

    a = _StubAgent("a")
    ctx, _ = a._build_resume_digest_context()
    assert "MY-CACHED-DIGEST-TEXT" in ctx


def test_resume_context_is_consumed_exactly_once(store):
    _attach_resume_method()
    cid = store.save(agent_id="a", plan_json={})
    store.update_digest(cid, "x")
    store.mark_restored(cid)
    store.set_metadata_flag(cid, "pending_chat_delivery", True)
    a = _StubAgent("a")
    first, _ = a._build_resume_digest_context()
    assert first is not None
    second, _ = a._build_resume_digest_context()
    assert second is None


# ── /restore endpoint integration ──────────────────────────────────


def test_restore_endpoint_flips_pending_flag(tmp_path, monkeypatch):
    ckpt.reset_store_for_test()
    monkeypatch.setenv("TUDOU_CLAW_DATA_DIR", str(tmp_path))
    s = ckpt.get_store(db_path=str(tmp_path / "ckpt.db"))

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.deps.auth import get_current_user, CurrentUser
    from app.api.routers import checkpoints as ckpt_router

    async def _fake_user():
        return CurrentUser(user_id="u", role="superAdmin")

    app = FastAPI()
    app.dependency_overrides[get_current_user] = _fake_user
    app.include_router(ckpt_router.router)

    cid = s.save(agent_id="a", plan_json={})
    with TestClient(app) as tc:
        r = tc.post(f"/api/portal/checkpoint/{cid}/restore")
        assert r.status_code == 200
        d = r.json()
        assert d["pending_chat_delivery"] is True
    reloaded = s.load(cid)
    assert reloaded.status == ckpt.STATUS_RESTORED
    assert reloaded.metadata.get("pending_chat_delivery") is True
    ckpt.reset_store_for_test()
