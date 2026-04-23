"""Block 3 Day 9 — end-to-end checkpoint flow.

Covers the complete resume cycle a user encounters:

    1. Meeting abort → abort_with_checkpoint persists full snapshot
    2. Portal GET /list shows it; GET /{id}/digest returns computed text
    3. User clicks restore → /restore flips pending flag + returns digest
    4. Target agent's next chat turn consumes the digest (exactly once)
    5. Re-running chat does NOT re-inject the digest
    6. Archive removes from default open list
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


from app import abort_registry as ar   # noqa: E402
from app import checkpoint as ckpt    # noqa: E402


class _StubAgent:
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
def wiring(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="ckpt_e2e_")
    monkeypatch.setenv("TUDOU_CLAW_DATA_DIR", tmpdir)
    ckpt.reset_store_for_test()
    store = ckpt.get_store(db_path=os.path.join(tmpdir, "ckpt.db"))

    from app.api.deps.auth import get_current_user, CurrentUser
    from app.api.routers import checkpoints as ckpt_router

    async def _fake_user():
        return CurrentUser(user_id="u", role="superAdmin")

    app = FastAPI()
    app.dependency_overrides[get_current_user] = _fake_user
    app.include_router(ckpt_router.router)

    with TestClient(app) as tc:
        tc.store = store
        yield tc

    ckpt.reset_store_for_test()


# ── the full flow ──────────────────────────────────────────────────


def test_meeting_abort_to_agent_resume_complete_cycle(wiring):
    _attach_resume_method()
    tc = wiring

    # 1. Simulate meeting abort persisting a checkpoint.
    key = ar.meeting_key("m-42")
    ar.mark(key)
    result = ar.abort_with_checkpoint(
        key,
        snapshot_fn=lambda: {
            "agent_id": "a-alice",
            "scope": ckpt.SCOPE_MEETING,
            "scope_id": "m-42",
            "plan_json": {
                "task_summary": "build quarterly report",
                "steps": [
                    {"id": "s1", "title": "gather data",
                     "status": "completed", "order": 0,
                     "result_summary": "parsed 17 CSVs"},
                    {"id": "s2", "title": "generate pptx",
                     "status": "in_progress", "order": 1,
                     "acceptance": "≥ 5 slides, include charts"},
                    {"id": "s3", "title": "email to team",
                     "status": "pending", "order": 2},
                ],
            },
            "artifact_refs": [
                {"id": "art_1", "kind": "file",
                 "path": "/ws/data.csv", "size_bytes": 4096},
            ],
            "chat_tail": [
                {"role": "user", "content": "please build Q4 report"},
                {"role": "assistant",
                 "content": "starting now, gathering data first"},
            ],
            "reason": ckpt.REASON_USER_ABORT,
            "metadata": {"meeting_title": "Q4 Review"},
        },
    )
    assert result["aborted_now"] is True
    cid = result["checkpoint_id"]
    assert cid.startswith("ckpt_")
    ar.clear(key)

    # 2. Portal lists + gets digest
    r = tc.get("/api/portal/checkpoint/list",
               params={"scope": "meeting", "scope_id": "m-42"})
    assert r.status_code == 200
    assert r.json()["count"] == 1
    assert r.json()["checkpoints"][0]["id"] == cid

    r = tc.get(f"/api/portal/checkpoint/{cid}/digest")
    d = r.json()
    assert d["source"] == "computed"
    assert "gather data" in d["text"] or "已完成" in d["text"]
    assert "generate pptx" in d["text"] or "待完成" in d["text"]
    assert "email to team" in d["text"]

    # 3. User clicks restore.
    r = tc.post(f"/api/portal/checkpoint/{cid}/restore")
    rd = r.json()
    assert rd["agent_id"] == "a-alice"
    assert rd["pending_chat_delivery"] is True

    # 4. Alice's NEXT chat turn consumes the digest exactly once.
    alice = _StubAgent("a-alice")
    ctx, returned_id = alice._build_resume_digest_context()
    assert returned_id == cid
    assert "<checkpoint_resume>" in ctx
    assert cid in ctx
    # Digest content reached the agent.
    assert "已完成" in ctx or "completed" in ctx.lower()

    # 5. The SECOND turn does not re-inject.
    ctx2, id2 = alice._build_resume_digest_context()
    assert ctx2 is None
    assert id2 == ""


def test_restore_across_agents_isolates(wiring):
    _attach_resume_method()
    tc = wiring
    store = tc.store

    # Two distinct checkpoints, two distinct agents.
    cid_a = store.save(agent_id="alice", plan_json={})
    cid_b = store.save(agent_id="bob", plan_json={})
    tc.post(f"/api/portal/checkpoint/{cid_a}/restore")
    tc.post(f"/api/portal/checkpoint/{cid_b}/restore")

    alice = _StubAgent("alice")
    bob = _StubAgent("bob")

    ctx_a, id_a = alice._build_resume_digest_context()
    ctx_b, id_b = bob._build_resume_digest_context()
    assert id_a == cid_a
    assert id_b == cid_b
    # Neither can see the other's after consumption.
    assert alice._build_resume_digest_context() == (None, "")
    assert bob._build_resume_digest_context() == (None, "")


def test_archive_removes_from_default_list(wiring):
    tc = wiring
    store = tc.store
    cid = store.save(agent_id="alice", plan_json={})
    # Default list (status=open by default? no — status filter not passed
    # means no filter, so both show up). We'll filter by open explicitly.
    r = tc.get("/api/portal/checkpoint/list",
               params={"agent_id": "alice", "status": "open"})
    assert r.json()["count"] == 1
    tc.post(f"/api/portal/checkpoint/{cid}/archive")
    r2 = tc.get("/api/portal/checkpoint/list",
                params={"agent_id": "alice", "status": "open"})
    assert r2.json()["count"] == 0
    # But archived list still shows it.
    r3 = tc.get("/api/portal/checkpoint/list",
                params={"agent_id": "alice", "status": "archived"})
    assert r3.json()["count"] == 1


def test_rebuild_digest_caches_text_for_fast_reads(wiring):
    tc = wiring
    store = tc.store
    cid = store.save(
        agent_id="alice",
        plan_json={"steps": [
            {"id": "s1", "title": "coded", "status": "completed",
             "order": 0, "result_summary": "pushed"},
        ]},
    )
    # First fetch — no stored digest → computed.
    r1 = tc.get(f"/api/portal/checkpoint/{cid}/digest")
    assert r1.json()["source"] == "computed"
    # Rebuild → persists.
    tc.post(f"/api/portal/checkpoint/{cid}/digest/rebuild",
            json={"token_budget": 1000})
    # Now it comes from cache.
    r2 = tc.get(f"/api/portal/checkpoint/{cid}/digest")
    assert r2.json()["source"] == "stored"
    assert r2.json()["text"] == r1.json()["text"]


def test_pending_flag_consumed_after_agent_turn_not_on_rest_read(wiring):
    """Reading the digest via REST must NOT consume the pending flag —
    only the agent's chat hook should."""
    _attach_resume_method()
    tc = wiring
    store = tc.store
    cid = store.save(agent_id="a", plan_json={})
    tc.post(f"/api/portal/checkpoint/{cid}/restore")
    # Pull the digest via REST — should NOT clear the flag.
    tc.get(f"/api/portal/checkpoint/{cid}/digest")
    # Pending flag still set.
    reloaded = store.load(cid)
    assert reloaded.metadata.get("pending_chat_delivery") is True
    # Now the agent turn consumes.
    a = _StubAgent("a")
    ctx, _ = a._build_resume_digest_context()
    assert ctx is not None
    reloaded = store.load(cid)
    assert reloaded.metadata.get("pending_chat_delivery") is False
