"""Day 4 tests — Agent chat pulls unread inbox at turn start.

Focus: `Agent._build_inbox_context` + the `chat()` hook that injects the
formatted block into `self.messages` and marks those messages read.

We don't run a full `chat()` loop (that spins up the LLM). Instead we
exercise the helper directly, and the hook by injecting a stub agent
into the path where the hook expects the inbox store.
"""
from __future__ import annotations

import os
import sys
import types

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ── Minimal Agent stub: exposes id + the method under test ─────────


class _StubAgent:
    """The absolute minimum Agent surface `_build_inbox_context` needs.

    We bind the real method onto this stub so the test exercises the
    production code path, just without the 200+ lines of Agent init.
    """

    def __init__(self, aid: str):
        self.id = aid
        self.messages: list = []
        self.logs: list = []

    def _log(self, kind, payload):
        self.logs.append((kind, payload))


def _attach_inbox_method():
    """Bind Agent._build_inbox_context onto our stub class."""
    from app.agent import Agent as _Agent
    _StubAgent._build_inbox_context = _Agent._build_inbox_context


@pytest.fixture(autouse=True)
def _bind(tmp_path, monkeypatch):
    _attach_inbox_method()
    from app import inbox
    inbox.reset_store_for_test()
    db = tmp_path / "inbox.db"
    monkeypatch.setenv("TUDOU_CLAW_DATA_DIR", str(tmp_path))
    inbox.get_store(db_path=str(db))
    yield
    inbox.reset_store_for_test()


# ── Core helper behavior ────────────────────────────────────────────


def test_no_unread_returns_none():
    a = _StubAgent("a-carol")
    ctx, ids = a._build_inbox_context()
    assert ctx is None
    assert ids == []


def test_unread_returns_formatted_block():
    from app.inbox import get_store
    store = get_store()
    mid = store.send(to_agent="a-carol", from_agent="a-alice",
                     content="hey carol, status?", priority="normal")

    a = _StubAgent("a-carol")
    ctx, ids = a._build_inbox_context()
    assert ctx is not None
    assert "<inbox>" in ctx and "</inbox>" in ctx
    assert "1 条未读消息" in ctx
    assert "hey carol, status?" in ctx
    assert "a-alice" in ctx
    assert mid in ids
    # NOTE: the helper does NOT mark read — caller owns that.
    assert store.unread_count("a-carol") == 1


def test_limit_caps_context_size():
    from app.inbox import get_store
    store = get_store()
    for i in range(20):
        store.send(to_agent="a-dave", from_agent="a-alice",
                   content=f"msg {i}")

    a = _StubAgent("a-dave")
    ctx, ids = a._build_inbox_context(limit=5)
    assert len(ids) == 5
    # Default (limit=10) also respected when passed explicitly.
    ctx10, ids10 = a._build_inbox_context(limit=10)
    assert len(ids10) == 10


def test_priority_order_in_context():
    from app.inbox import get_store
    store = get_store()
    store.send(to_agent="a-eve", from_agent="a-alice",
               content="normal one", priority="normal")
    store.send(to_agent="a-eve", from_agent="a-bob",
               content="URGENT!!", priority="urgent")

    a = _StubAgent("a-eve")
    ctx, _ = a._build_inbox_context()
    # urgent should appear BEFORE normal in the rendered block.
    assert ctx.index("URGENT!!") < ctx.index("normal one")


def test_truncates_long_body():
    from app.inbox import get_store
    store = get_store()
    big = "X" * 3000
    store.send(to_agent="a-frank", from_agent="a-alice", content=big)

    a = _StubAgent("a-frank")
    ctx, _ = a._build_inbox_context()
    assert "…(truncated)" in ctx
    # Should be roughly the cap (1200) not 3000.
    assert ctx.count("X") < 1500


def test_only_sees_own_messages():
    from app.inbox import get_store
    store = get_store()
    store.send(to_agent="a-grace", from_agent="x", content="for grace")
    store.send(to_agent="a-henry", from_agent="x", content="for henry")

    g = _StubAgent("a-grace")
    ctx, ids = g._build_inbox_context()
    assert "for grace" in ctx
    assert "for henry" not in ctx
    assert len(ids) == 1


def test_thread_and_reply_metadata_shown():
    from app.inbox import get_store
    store = get_store()
    root = store.send(to_agent="a-ivan", from_agent="a-alice",
                      content="start", thread_id="t-7")
    store.send(to_agent="a-ivan", from_agent="a-alice",
               content="follow", thread_id="t-7", reply_to=root)

    a = _StubAgent("a-ivan")
    ctx, _ = a._build_inbox_context()
    assert "thread=t-7" in ctx
    assert f"reply_to={root}" in ctx


def test_store_failure_returns_none_gracefully(monkeypatch):
    import app.inbox as ibx
    def _boom(db_path=None):
        raise RuntimeError("disk on fire")
    monkeypatch.setattr(ibx, "get_store", _boom)

    a = _StubAgent("a-julia")
    ctx, ids = a._build_inbox_context()
    assert ctx is None and ids == []


# ── End-to-end verification that the chat() hook marks read ─────────
# We don't run the LLM; we just simulate the hook block to confirm
# mark_read semantics line up with the helper contract.


def test_mark_read_transitions_after_injection():
    from app.inbox import get_store
    store = get_store()
    mid_a = store.send(to_agent="a-kate", from_agent="x", content="one")
    mid_b = store.send(to_agent="a-kate", from_agent="x", content="two")
    assert store.unread_count("a-kate") == 2

    a = _StubAgent("a-kate")
    ctx, ids = a._build_inbox_context()
    assert set(ids) == {mid_a, mid_b}
    # Simulate the chat() hook post-injection step.
    store.mark_read(ids, "a-kate")
    assert store.unread_count("a-kate") == 0


def test_repeated_build_after_mark_returns_empty():
    from app.inbox import get_store
    store = get_store()
    mid = store.send(to_agent="a-lee", from_agent="x", content="first")

    a = _StubAgent("a-lee")
    ctx1, ids1 = a._build_inbox_context()
    assert ids1 == [mid]
    store.mark_read(ids1, "a-lee")

    # A second chat turn: nothing new → nothing to inject.
    ctx2, ids2 = a._build_inbox_context()
    assert ctx2 is None and ids2 == []
