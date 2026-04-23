"""Block 3 Day 1-2 — CheckpointStore tests.

Mirrors the test structure for the inbox store: tmp_path-backed SQLite,
reset_store_for_test() between cases, plus cross-restart and concurrency
checks.
"""
from __future__ import annotations

import os
import sys
import time
import threading

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


from app import checkpoint as ckpt  # noqa: E402
from app.checkpoint import (  # noqa: E402
    AgentCheckpoint, CheckpointStore,
    SCOPE_AGENT, SCOPE_MEETING, SCOPE_PROJECT_TASK,
    STATUS_OPEN, STATUS_RESTORED, STATUS_ARCHIVED,
    REASON_USER_ABORT, REASON_MANUAL,
)


@pytest.fixture
def store(tmp_path, monkeypatch):
    ckpt.reset_store_for_test()
    db = tmp_path / "ckpt.db"
    monkeypatch.setenv("TUDOU_CLAW_DATA_DIR", str(tmp_path))
    s = ckpt.get_store(db_path=str(db))
    yield s
    ckpt.reset_store_for_test()


# ── basic save / load ───────────────────────────────────────────────


def test_save_returns_id_and_roundtrips(store):
    cid = store.save(
        agent_id="a-alice",
        plan_json={"id": "p1", "task_summary": "build",
                   "steps": [{"id": "s1", "title": "code"}]},
        reason=REASON_USER_ABORT,
        metadata={"hint": "in the middle of tests"},
    )
    assert cid.startswith("ckpt_")
    c = store.load(cid)
    assert isinstance(c, AgentCheckpoint)
    assert c.agent_id == "a-alice"
    assert c.scope == SCOPE_AGENT
    assert c.reason == REASON_USER_ABORT
    assert c.plan_json["task_summary"] == "build"
    assert c.plan_json["steps"][0]["title"] == "code"
    assert c.metadata == {"hint": "in the middle of tests"}
    assert c.status == STATUS_OPEN
    assert c.restored_at == 0.0


def test_save_rejects_missing_agent_id(store):
    with pytest.raises(ValueError):
        store.save(agent_id="", plan_json={})


def test_save_rejects_invalid_scope(store):
    with pytest.raises(ValueError):
        store.save(agent_id="a", scope="weird", plan_json={})


def test_load_missing_returns_none(store):
    assert store.load("ckpt_does_not_exist") is None


def test_artifact_refs_and_chat_tail_roundtrip(store):
    refs = [
        {"id": "art1", "kind": "file",
         "path": "/tmp/report.pdf", "produced_at": 1234.5},
        {"id": "art2", "kind": "value",
         "path": "", "produced_at": 1235.0},
    ]
    tail = [
        {"role": "user", "content": "make a pdf",
         "source": "admin", "ts": 1000.0},
        {"role": "assistant",
         "content": "sure, will do", "source": "", "ts": 1001.0},
    ]
    cid = store.save(agent_id="a",
                     artifact_refs=refs, chat_tail=tail)
    c = store.load(cid)
    assert c.artifact_refs == refs
    assert c.chat_tail == tail


# ── state transitions ──────────────────────────────────────────────


def test_mark_restored_updates_status_and_timestamp(store):
    cid = store.save(agent_id="a", plan_json={})
    assert store.load(cid).status == STATUS_OPEN
    assert store.mark_restored(cid) is True
    c = store.load(cid)
    assert c.status == STATUS_RESTORED
    assert c.restored_at > 0


def test_mark_restored_unknown_returns_false(store):
    assert store.mark_restored("ckpt_missing") is False


def test_archive_transition(store):
    cid = store.save(agent_id="a", plan_json={})
    assert store.archive(cid) is True
    assert store.load(cid).status == STATUS_ARCHIVED


def test_update_digest(store):
    cid = store.save(agent_id="a", plan_json={})
    assert store.load(cid).digest == ""
    assert store.update_digest(cid, "summary of past work") is True
    assert store.load(cid).digest == "summary of past work"
    # Empty digest is allowed (resets)
    assert store.update_digest(cid, "") is True
    assert store.load(cid).digest == ""


# ── listing / filtering ────────────────────────────────────────────


def test_list_for_agent_returns_newest_first(store):
    c1 = store.save(agent_id="a", plan_json={"k": 1})
    time.sleep(0.001)
    c2 = store.save(agent_id="a", plan_json={"k": 2})
    time.sleep(0.001)
    c3 = store.save(agent_id="a", plan_json={"k": 3})
    ids = [c.id for c in store.list_for_agent("a")]
    assert ids == [c3, c2, c1]


def test_list_for_agent_filters_by_status(store):
    a = store.save(agent_id="x", plan_json={})
    b = store.save(agent_id="x", plan_json={})
    store.mark_restored(a)
    open_ids = [c.id for c in store.list_for_agent("x", status=STATUS_OPEN)]
    assert open_ids == [b]
    restored_ids = [c.id for c in store.list_for_agent(
        "x", status=STATUS_RESTORED)]
    assert restored_ids == [a]


def test_list_for_agent_filters_by_scope(store):
    store.save(agent_id="x", plan_json={}, scope=SCOPE_AGENT)
    m = store.save(agent_id="x", plan_json={},
                   scope=SCOPE_MEETING, scope_id="m1")
    p = store.save(agent_id="x", plan_json={},
                   scope=SCOPE_PROJECT_TASK, scope_id="t1")
    mtg = [c.id for c in store.list_for_agent("x", scope=SCOPE_MEETING)]
    assert mtg == [m]
    tsk = [c.id for c in store.list_for_agent("x",
                                              scope=SCOPE_PROJECT_TASK)]
    assert tsk == [p]


def test_list_for_agent_respects_limit(store):
    for _ in range(8):
        store.save(agent_id="a", plan_json={})
    assert len(store.list_for_agent("a", limit=3)) == 3
    assert len(store.list_for_agent("a", limit=500)) == 8


def test_list_for_agent_isolates_agents(store):
    store.save(agent_id="alice", plan_json={})
    store.save(agent_id="alice", plan_json={})
    store.save(agent_id="bob", plan_json={})
    assert len(store.list_for_agent("alice")) == 2
    assert len(store.list_for_agent("bob")) == 1
    assert len(store.list_for_agent("mallory")) == 0


# ── scope-based lookup ────────────────────────────────────────────


def test_list_for_scope_returns_only_matching(store):
    m1 = store.save(agent_id="a", plan_json={},
                    scope=SCOPE_MEETING, scope_id="m1")
    store.save(agent_id="b", plan_json={},
               scope=SCOPE_MEETING, scope_id="m2")
    m1b = store.save(agent_id="c", plan_json={},
                     scope=SCOPE_MEETING, scope_id="m1")
    ids = [c.id for c in store.list_for_scope(SCOPE_MEETING, "m1")]
    # Both meeting m1 checkpoints, newest first
    assert ids == [m1b, m1]


def test_list_for_scope_validates_scope(store):
    with pytest.raises(ValueError):
        store.list_for_scope("weird", "whatever")


def test_latest_open_for_scope_returns_most_recent_open(store):
    a = store.save(agent_id="x", plan_json={},
                   scope=SCOPE_MEETING, scope_id="m7")
    time.sleep(0.001)
    b = store.save(agent_id="y", plan_json={},
                   scope=SCOPE_MEETING, scope_id="m7")
    store.mark_restored(b)  # b is no longer OPEN
    latest = store.latest_open_for_scope(SCOPE_MEETING, "m7")
    assert latest.id == a
    # After restoring a too, none open.
    store.mark_restored(a)
    assert store.latest_open_for_scope(SCOPE_MEETING, "m7") is None


# ── prune / stats ─────────────────────────────────────────────────


def test_prune_older_than_only_archived_by_default(store):
    a = store.save(agent_id="x", plan_json={})  # open
    b = store.save(agent_id="x", plan_json={})
    store.archive(b)
    cutoff = time.time() + 10  # everything older than "now + 10s"
    removed = store.prune_older_than(cutoff)
    assert removed == 1       # only the archived one deleted
    assert store.load(a) is not None
    assert store.load(b) is None


def test_prune_can_be_forced_non_archived_only_with_flag(store):
    a = store.save(agent_id="x", plan_json={})
    b = store.save(agent_id="x", plan_json={})
    cutoff = time.time() + 10
    removed = store.prune_older_than(cutoff, only_archived=False)
    assert removed == 2
    assert store.load(a) is None
    assert store.load(b) is None


def test_stats_reflects_state(store):
    a = store.save(agent_id="x", plan_json={})
    store.save(agent_id="x", plan_json={},
               scope=SCOPE_MEETING, scope_id="m1")
    store.mark_restored(a)
    s = store.stats()
    assert s["total"] == 2
    assert s["by_status"].get(STATUS_RESTORED, 0) == 1
    assert s["by_status"].get(STATUS_OPEN, 0) == 1
    assert s["by_scope"].get(SCOPE_AGENT, 0) == 1
    assert s["by_scope"].get(SCOPE_MEETING, 0) == 1


# ── persistence across process restart ───────────────────────────


def test_messages_persist_across_store_recreation(tmp_path, monkeypatch):
    ckpt.reset_store_for_test()
    db = tmp_path / "ckpt.db"
    monkeypatch.setenv("TUDOU_CLAW_DATA_DIR", str(tmp_path))
    s1 = ckpt.get_store(db_path=str(db))
    cid = s1.save(agent_id="a", plan_json={"v": 1})
    ckpt.reset_store_for_test()
    s2 = ckpt.get_store(db_path=str(db))
    c = s2.load(cid)
    assert c is not None
    assert c.plan_json == {"v": 1}
    ckpt.reset_store_for_test()


# ── concurrency ───────────────────────────────────────────────────


def test_concurrent_saves_all_persist(store):
    ids: list[str] = []
    lock = threading.Lock()

    def worker():
        for _ in range(10):
            cid = store.save(agent_id="a", plan_json={"ts": time.time()})
            with lock:
                ids.append(cid)

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(ids) == 60
    assert len(set(ids)) == 60  # no id collisions
    # All readable back.
    assert all(store.load(i) is not None for i in ids)


# ── singleton ─────────────────────────────────────────────────────


def test_get_store_returns_same_instance(tmp_path, monkeypatch):
    ckpt.reset_store_for_test()
    db = tmp_path / "a.db"
    monkeypatch.setenv("TUDOU_CLAW_DATA_DIR", str(tmp_path))
    s1 = ckpt.get_store(db_path=str(db))
    s2 = ckpt.get_store()
    assert s1 is s2
    ckpt.reset_store_for_test()


def test_reset_store_for_test_gives_fresh_instance(tmp_path, monkeypatch):
    ckpt.reset_store_for_test()
    db = tmp_path / "a.db"
    monkeypatch.setenv("TUDOU_CLAW_DATA_DIR", str(tmp_path))
    s1 = ckpt.get_store(db_path=str(db))
    ckpt.reset_store_for_test()
    s2 = ckpt.get_store(db_path=str(db))
    assert s1 is not s2
    ckpt.reset_store_for_test()
