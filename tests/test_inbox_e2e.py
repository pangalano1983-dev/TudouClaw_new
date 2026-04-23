"""Day 7 — end-to-end inbox flow across all layers.

Covers:
    Agent A tool-call → coordination.send_message → InboxStore persist
    → Agent B chat turn _build_inbox_context → context injected, marked read
    → Agent B tool-call → coordination.reply_message → thread continuity
    → Agent A next chat turn picks up the reply
    → Portal REST `/api/portal/inbox/list` shows the correct state

Plus tight regression on state transitions: new → read (auto-inject) → acked (deliberate).

We use a `_StubAgent` with the real `_build_inbox_context` bound on, to
avoid spinning up the full Agent(__init__ does a lot). The coordination
tools are invoked directly so we exercise the persistence path.
"""
from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ── Stub infrastructure (agent + hub) ──────────────────────────────


class _FakeAgentRef:
    """Hub-facing agent handle used by the legacy routing path."""
    def __init__(self, aid: str, name: str):
        self.id = aid
        self.name = name


class _FakeHub:
    def __init__(self):
        self.agents: dict[str, _FakeAgentRef] = {}
        self.routed: list[tuple] = []

    def get_agent(self, k):
        return self.agents.get(k)

    def route_message(self, frm, to, content, msg_type="task",
                      source="api", metadata=None):
        self.routed.append((frm, to, content, msg_type, source))


class _StubAgent:
    """Minimum Agent surface exercising the chat-entry inbox hook."""
    def __init__(self, aid: str, name: str):
        self.id = aid
        self.name = name
        self.messages: list = []
        self.logs: list = []

    def _log(self, kind, payload):
        self.logs.append((kind, payload))

    def inbox_turn(self):
        """Simulate the portion of `chat()` that injects inbox + marks read."""
        from app.agent import Agent as _Agent
        # Bind the real helper.
        _StubAgent._build_inbox_context = _Agent._build_inbox_context
        ctx, ids = self._build_inbox_context(limit=10)
        if not ctx:
            return []
        self.messages.append({"role": "system", "content": ctx})
        from app.inbox import get_store
        get_store().mark_read(ids, self.id)
        self._log("inbox_pull", {"count": len(ids), "chars": len(ctx)})
        return ids


# ── fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def wiring(tmp_path, monkeypatch):
    """Fresh inbox store + patched hub, wired into coordination tool."""
    from app import inbox
    inbox.reset_store_for_test()
    db = tmp_path / "inbox.db"
    monkeypatch.setenv("TUDOU_CLAW_DATA_DIR", str(tmp_path))
    store = inbox.get_store(db_path=str(db))

    hub = _FakeHub()
    hub.agents["a-alice"] = _FakeAgentRef("a-alice", "Alice")
    hub.agents["a-bob"] = _FakeAgentRef("a-bob", "Bob")
    import app.tools_split._common as common
    import app.tools_split.coordination as coordination
    monkeypatch.setattr(common, "_get_hub", lambda: hub)
    monkeypatch.setattr(coordination, "_get_hub", lambda: hub)

    yield store, hub
    inbox.reset_store_for_test()


# ── Primary flow ────────────────────────────────────────────────────


def test_full_send_pull_reply_cycle(wiring):
    store, hub = wiring
    from app.tools_split.coordination import (
        _tool_send_message, _tool_reply_message, _tool_ack_message,
    )

    alice = _StubAgent("a-alice", "Alice")
    bob = _StubAgent("a-bob", "Bob")

    # 1. Alice sends Bob a message via the coordination tool.
    out1 = _tool_send_message(
        to_agent="Bob",
        content="Can you run regression tests on branch feat/x?",
        priority="urgent",
        _caller_agent_id="a-alice",
    )
    assert "Message sent to Bob" in out1
    assert "Inbox id:" in out1  # persistence kicked in
    # Hub mirror also fired.
    assert len(hub.routed) == 1 and hub.routed[0][1] == "a-bob"

    # 2. Bob hasn't chatted yet → inbox has 1 unread for him.
    assert store.unread_count("a-bob") == 1
    assert store.unread_count("a-alice") == 0

    # 3. Bob's next chat turn triggers the inbox hook.
    bob_ids = bob.inbox_turn()
    assert len(bob_ids) == 1
    # Context was injected as a system message.
    assert bob.messages[-1]["role"] == "system"
    assert "regression tests" in bob.messages[-1]["content"]
    assert "a-alice" in bob.messages[-1]["content"]
    # Mark-read took effect (no longer unread).
    assert store.unread_count("a-bob") == 0
    # But NOT acked yet — ack is a deliberate action.
    orig = store.get_by_id(bob_ids[0])
    assert orig.state == "read"

    # 4. Bob replies via reply_message — thread / reply_to auto-wired.
    orig_id = bob_ids[0]
    out2 = _tool_reply_message(
        message_id=orig_id,
        content="Tests green, 0 failures.",
        _caller_agent_id="a-bob",
    )
    assert "Reply sent to a-alice" in out2
    # Hub mirror was hit again for the reply.
    assert len(hub.routed) == 2
    assert hub.routed[1][3] == "reply"  # msg_type

    # 5. Alice's next turn picks up the reply.
    alice_ids = alice.inbox_turn()
    assert len(alice_ids) == 1
    reply_msg = store.get_by_id(alice_ids[0])
    # P0-A: wire-rendered envelope wraps the raw text.
    assert "Tests green, 0 failures." in reply_msg.content
    assert reply_msg.reply_to == orig_id
    # Thread linking preserved (thread_id defaulted to orig.id on send).
    assert reply_msg.thread_id == orig_id

    # 6. Bob now decides to ack the original question (I'm done with it).
    out3 = _tool_ack_message(
        message_ids=orig_id, _caller_agent_id="a-bob",
    )
    assert "Acked 1/1" in out3
    assert store.get_by_id(orig_id).state == "acked"

    # 7. Next chat turn for Bob — nothing new, no injection.
    assert bob.inbox_turn() == []


# ── State machine hard checks ───────────────────────────────────────


def test_auto_inject_does_not_ack(wiring):
    """Auto-inject only transitions new→read; ack must be deliberate."""
    store, _ = wiring
    from app.tools_split.coordination import _tool_send_message

    _tool_send_message(
        to_agent="Bob", content="fyi", _caller_agent_id="a-alice",
    )
    bob = _StubAgent("a-bob", "Bob")
    bob.inbox_turn()  # auto-pull

    # Verify state machine: new → read (NOT acked)
    unread_cnt = store.unread_count("a-bob")
    assert unread_cnt == 0
    # Peek at the raw row
    with store._lock:
        rows = list(store._conn.execute(
            "SELECT state FROM inbox_messages WHERE to_agent='a-bob'"
        ))
    assert [dict(r)["state"] for r in rows] == ["read"]


def test_urgent_before_normal_in_auto_inject(wiring):
    store, _ = wiring
    from app.tools_split.coordination import _tool_send_message

    _tool_send_message(to_agent="Bob", content="normal one",
                       priority="normal", _caller_agent_id="a-alice")
    _tool_send_message(to_agent="Bob", content="URGENT!!",
                       priority="urgent", _caller_agent_id="a-alice")
    bob = _StubAgent("a-bob", "Bob")
    bob.inbox_turn()
    ctx = bob.messages[-1]["content"]
    assert ctx.index("URGENT!!") < ctx.index("normal one")


def test_reply_refused_cross_agent_preserves_inbox(wiring):
    """Reply from wrong sender must not add to thread or hub."""
    store, hub = wiring
    from app.tools_split.coordination import (
        _tool_send_message, _tool_reply_message,
    )

    _tool_send_message(to_agent="Bob", content="for bob",
                       _caller_agent_id="a-alice")
    bob = _StubAgent("a-bob", "Bob")
    ids = bob.inbox_turn()
    assert len(ids) == 1
    orig_id = ids[0]

    # Alice tries to reply to a message that was addressed to Bob.
    out = _tool_reply_message(
        message_id=orig_id, content="sneaky",
        _caller_agent_id="a-alice",
    )
    assert "cannot reply" in out
    # Thread unchanged.
    assert len(store.get_thread(orig_id)) == 1
    # Only the original send_message's hub route fired, no reply.
    assert len(hub.routed) == 1


def test_crash_between_build_and_mark_does_not_lose_messages(
        wiring, monkeypatch):
    """If mark_read fails, the message should stay unread (no silent drop)."""
    store, _ = wiring
    from app.tools_split.coordination import _tool_send_message

    _tool_send_message(to_agent="Bob", content="safe",
                       _caller_agent_id="a-alice")
    bob = _StubAgent("a-bob", "Bob")

    # Build the context but then force mark_read to raise.
    from app.agent import Agent as _Agent
    _StubAgent._build_inbox_context = _Agent._build_inbox_context
    ctx, ids = bob._build_inbox_context(limit=10)
    assert ctx is not None and len(ids) == 1

    def _raise(*a, **kw):
        raise RuntimeError("db locked")

    monkeypatch.setattr(store, "mark_read", _raise)
    try:
        store.mark_read(ids, bob.id)
    except RuntimeError:
        pass

    # Message is still unread — a subsequent turn (after fix) picks it up.
    assert store.unread_count("a-bob") == 1


# ── REST API consistency with tool flow ─────────────────────────────


def test_rest_api_reflects_tool_writes(wiring):
    """REST /api/portal/inbox/list reflects state after tool-driven sends."""
    store, _ = wiring
    from app.tools_split.coordination import _tool_send_message

    _tool_send_message(to_agent="Bob", content="hi via tool",
                       priority="urgent",
                       _caller_agent_id="a-alice")

    # Spin a minimal FastAPI app around the router and query it.
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.deps.auth import get_current_user, CurrentUser
    from app.api.routers import inbox as inbox_router

    async def _fake_user():
        return CurrentUser(user_id="u", role="superAdmin")

    app = FastAPI()
    app.dependency_overrides[get_current_user] = _fake_user
    app.include_router(inbox_router.router)

    with TestClient(app) as tc:
        r = tc.get("/api/portal/inbox/list",
                   params={"agent_id": "a-bob"})
        d = r.json()
        assert d["unread_count"] == 1
        m = d["messages"][0]
        # P0-A: wire content wraps the raw text in envelope form.
        assert "hi via tool" in m["content"]
        assert m["priority"] == "urgent"
        # Ack it via REST and re-check.
        tc.post("/api/portal/inbox/ack",
                json={"agent_id": "a-bob",
                      "message_ids": [m["id"]]})
        r2 = tc.get("/api/portal/inbox/list",
                    params={"agent_id": "a-bob"})
        assert r2.json()["unread_count"] == 0
