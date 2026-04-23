"""Block 3 Day 3 — checkpoint integration with abort_registry.

Covers:
  * save_for_abort helper persists + emits a ProgressBus frame.
  * abort_with_checkpoint calls snapshot_fn first, then abort.
  * Snapshot failures never block the actual abort.
  * Frame emission failures never block save.
"""
from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


from app import abort_registry as ar  # noqa: E402
from app import checkpoint as ckpt   # noqa: E402
from app import progress_bus as pb   # noqa: E402


@pytest.fixture
def store(tmp_path, monkeypatch):
    ckpt.reset_store_for_test()
    db = tmp_path / "ckpt.db"
    monkeypatch.setenv("TUDOU_CLAW_DATA_DIR", str(tmp_path))
    s = ckpt.get_store(db_path=str(db))
    yield s
    ckpt.reset_store_for_test()


# ── save_for_abort ──────────────────────────────────────────────────


def test_save_for_abort_persists_checkpoint(store):
    cid = ckpt.save_for_abort(
        agent_id="a-alice",
        plan_json={"task_summary": "x", "steps": []},
        reason=ckpt.REASON_USER_ABORT,
    )
    assert cid.startswith("ckpt_")
    c = store.load(cid)
    assert c.agent_id == "a-alice"
    assert c.reason == ckpt.REASON_USER_ABORT


def test_save_for_abort_emits_progress_frame(store):
    bus = pb.get_bus()
    received: list = []
    sub = bus.subscribe("global")
    try:
        cid = ckpt.save_for_abort(
            agent_id="a-alice",
            scope=ckpt.SCOPE_MEETING,
            scope_id="m-42",
            plan_json={"task_summary": "y"},
        )
        # Drain whatever landed in the queue.
        while True:
            f = sub.next(timeout=0.2)
            if f is None:
                break
            received.append(f)
    finally:
        bus.unsubscribe(sub)
    kinds = [f.kind for f in received]
    assert "checkpoint_created" in kinds
    match = [f for f in received
             if f.kind == "checkpoint_created"
             and f.data.get("checkpoint_id") == cid]
    assert match, "no matching checkpoint_created frame emitted"
    f = match[0]
    assert f.data.get("scope") == ckpt.SCOPE_MEETING
    assert f.data.get("scope_id") == "m-42"


def test_save_for_abort_emit_frame_false_is_silent(store, monkeypatch):
    sub = pb.get_bus().subscribe("global")
    try:
        ckpt.save_for_abort(
            agent_id="x", plan_json={}, emit_frame=False,
        )
        f = sub.next(timeout=0.2)
        if f is not None:
            assert f.kind != "checkpoint_created"
    finally:
        pb.get_bus().unsubscribe(sub)


def test_save_for_abort_returns_empty_on_db_failure(monkeypatch):
    """Never raises — returns "" if the store itself is broken."""
    # Force get_store to fail.
    def _boom(*a, **kw):
        raise RuntimeError("disk on fire")
    monkeypatch.setattr(ckpt, "get_store", _boom)
    out = ckpt.save_for_abort(agent_id="a", plan_json={})
    assert out == ""


def test_save_for_abort_frame_failure_does_not_break_save(
        store, monkeypatch):
    """Even if publishing the frame fails, the checkpoint must persist."""
    import app.progress_bus as _pb_mod
    orig_get_bus = _pb_mod.get_bus

    class _BrokenBus:
        def publish(self, *a, **kw):
            raise RuntimeError("bus on fire")

    monkeypatch.setattr(_pb_mod, "get_bus", lambda: _BrokenBus())
    cid = ckpt.save_for_abort(agent_id="a", plan_json={"ok": True})
    assert cid  # non-empty
    assert store.load(cid).plan_json == {"ok": True}
    monkeypatch.setattr(_pb_mod, "get_bus", orig_get_bus)


# ── abort_with_checkpoint ──────────────────────────────────────────


def test_abort_with_checkpoint_snapshots_then_aborts(store):
    key = ar.meeting_key("m-1")
    ar.mark(key)
    called = {"snap": 0}

    def _snap():
        called["snap"] += 1
        return {
            "agent_id": "alice",
            "scope": ckpt.SCOPE_MEETING,
            "scope_id": "m-1",
            "plan_json": {"task_summary": "meet",
                          "steps": [{"id": "s1", "status": "in_progress"}]},
            "chat_tail": [{"role": "user", "content": "go"}],
            "reason": ckpt.REASON_USER_ABORT,
            "metadata": {"hint": "test"},
        }

    result = ar.abort_with_checkpoint(key, snapshot_fn=_snap)
    assert called["snap"] == 1
    assert result["found"] is True
    assert result["aborted_now"] is True
    assert result["checkpoint_id"].startswith("ckpt_")
    c = store.load(result["checkpoint_id"])
    assert c.scope == ckpt.SCOPE_MEETING
    assert c.scope_id == "m-1"
    assert c.plan_json["task_summary"] == "meet"
    assert c.chat_tail == [{"role": "user", "content": "go"}]
    # Registry actually aborted.
    assert ar.is_aborted(key) is True
    ar.clear(key)


def test_snapshot_exception_does_not_prevent_abort(store):
    key = ar.meeting_key("m-2")
    ar.mark(key)

    def _snap():
        raise RuntimeError("snapshot broke")

    result = ar.abort_with_checkpoint(key, snapshot_fn=_snap)
    # Abort still occurred.
    assert result["found"] is True
    assert result["aborted_now"] is True
    # No checkpoint because snapshot raised → save_for_abort got empty
    # snap, saved a mostly-empty record. It should still return an id
    # (per our design: save_for_abort uses defaults for missing fields).
    # We don't assert contents — only that the abort side succeeded.
    assert ar.is_aborted(key) is True
    ar.clear(key)


def test_snapshot_returning_non_dict_is_tolerated(store):
    key = ar.agent_key("a-ghost")
    ar.mark(key)

    def _snap():
        return None  # malformed

    result = ar.abort_with_checkpoint(key, snapshot_fn=_snap)
    assert result["found"] is True
    ar.clear(key)


def test_abort_with_checkpoint_on_unknown_key_is_safe(store):
    # Key never registered — found should be False, but no crash.
    result = ar.abort_with_checkpoint(
        ar.meeting_key("never-seen"),
        snapshot_fn=lambda: {"agent_id": "x", "plan_json": {}},
    )
    assert result["found"] is False
    # Snapshot still ran and checkpoint got saved though — that's a
    # feature, not a bug: user clicks pause on something already
    # stopped, we still record what we know so it can be resumed.
    assert result.get("checkpoint_id", "")
