"""Tests for `_tool_send_message` persistence upgrade.

Verifies that the coordination tool now BOTH:
  1. Invokes the hub's canonical `route_message` (legacy in-memory path).
  2. Persists the message into the durable inbox store.

Inbox persistence must be additive only — a failure in the inbox layer
must NOT break the primary delivery.
"""
from __future__ import annotations

import os
import sys
import types

import pytest


# Ensure repo root is importable when running this test in isolation.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ── Fake hub infrastructure ─────────────────────────────────────────


class _FakeAgent:
    def __init__(self, aid: str, name: str):
        self.id = aid
        self.name = name


class _FakeHub:
    def __init__(self):
        self.agents: dict[str, _FakeAgent] = {}
        self.routed: list[tuple] = []

    def get_agent(self, key: str):
        return self.agents.get(key)

    def route_message(self, frm, to, content, msg_type="task",
                      source="api", metadata=None):
        self.routed.append((frm, to, content, msg_type, source))
        return types.SimpleNamespace(id="msg-1")


@pytest.fixture
def fake_hub(monkeypatch):
    hub = _FakeHub()
    hub.agents["a-bob"] = _FakeAgent("a-bob", "Bob")
    # `coordination.py` does `from ._common import _get_hub`, so the name
    # lives in its own namespace. Patch there (and in _common, defensively).
    import app.tools_split._common as common
    import app.tools_split.coordination as coordination
    monkeypatch.setattr(common, "_get_hub", lambda: hub)
    monkeypatch.setattr(coordination, "_get_hub", lambda: hub)
    return hub


@pytest.fixture
def fresh_inbox(tmp_path, monkeypatch):
    from app import inbox
    inbox.reset_store_for_test()
    db = tmp_path / "inbox.db"
    monkeypatch.setenv("TUDOU_CLAW_DATA_DIR", str(tmp_path))
    store = inbox.get_store(db_path=str(db))
    yield store
    inbox.reset_store_for_test()


# ── Tests ───────────────────────────────────────────────────────────


def test_legacy_route_still_called(fake_hub, fresh_inbox):
    from app.tools_split.coordination import _tool_send_message

    out = _tool_send_message(
        to_agent="a-bob", content="hello bob", msg_type="task",
        _caller_agent_id="a-alice",
    )
    assert "Message sent to Bob" in out
    assert len(fake_hub.routed) == 1
    frm, to, content, msg_type, source = fake_hub.routed[0]
    assert frm == "a-alice" and to == "a-bob"
    # P0-A: wire-rendered envelope wraps the raw content but still
    # contains the text as a Summary or Detail line.
    assert "hello bob" in content
    assert source == "tool_send_message"


def test_inbox_receives_persisted_copy(fake_hub, fresh_inbox):
    from app.tools_split.coordination import _tool_send_message

    out = _tool_send_message(
        to_agent="Bob", content="persist me", msg_type="task",
        _caller_agent_id="a-alice",
    )
    assert "Inbox id:" in out
    msgs = fresh_inbox.fetch_unread("a-bob")
    assert len(msgs) == 1
    m = msgs[0]
    # P0-A: m.content is now the wire-rendered envelope; raw text is in
    # metadata.detail_full. Legacy callers w/ only `content` still get
    # their raw text back via detail_full AND have it appear in the
    # rendered text.
    assert "persist me" in m.content
    assert m.metadata.get("detail_full") == "persist me"
    assert m.from_agent == "a-alice"
    assert m.to_agent == "a-bob"
    # metadata annotations survive.
    assert m.metadata.get("msg_type") == "task"
    assert m.metadata.get("source") == "tool_send_message"


def test_thread_id_and_reply_to_flow_into_inbox(fake_hub, fresh_inbox):
    from app.tools_split.coordination import _tool_send_message

    _tool_send_message(
        to_agent="Bob", content="first", msg_type="task",
        thread_id="t-42",
        _caller_agent_id="a-alice",
    )
    first = fresh_inbox.fetch_unread("a-bob")[0]

    _tool_send_message(
        to_agent="Bob", content="follow-up", msg_type="task",
        thread_id="t-42", reply_to=first.id,
        _caller_agent_id="a-alice",
    )
    thread = fresh_inbox.get_thread("t-42")
    assert len(thread) == 2
    # Envelope-wrapped content still contains the original text.
    assert "first" in thread[0].content
    assert "follow-up" in thread[1].content
    assert thread[1].reply_to == first.id


def test_priority_urgent_fetched_before_normal(fake_hub, fresh_inbox):
    from app.tools_split.coordination import _tool_send_message

    _tool_send_message(to_agent="Bob", content="low prio",
                       priority="normal",
                       _caller_agent_id="a-alice")
    _tool_send_message(to_agent="Bob", content="URGENT",
                       priority="urgent",
                       _caller_agent_id="a-alice")
    msgs = fresh_inbox.fetch_unread("a-bob")
    assert "URGENT" in msgs[0].content
    assert "low prio" in msgs[1].content


def test_ttl_zero_default(fake_hub, fresh_inbox):
    from app.tools_split.coordination import _tool_send_message

    _tool_send_message(to_agent="Bob", content="persistent",
                       _caller_agent_id="a-alice")
    m = fresh_inbox.fetch_unread("a-bob")[0]
    assert m.ttl_s == 0


def test_inbox_failure_does_not_break_primary_delivery(
        fake_hub, monkeypatch, caplog):
    """If the inbox store raises, `route_message` must still succeed and
    the tool must still return an OK reply."""
    from app.tools_split.coordination import _tool_send_message

    def _boom(db_path=None):
        raise RuntimeError("disk is on fire")

    import app.inbox as _inbox_mod
    monkeypatch.setattr(_inbox_mod, "get_store", _boom)

    out = _tool_send_message(
        to_agent="Bob", content="still works",
        _caller_agent_id="a-alice",
    )
    # Hub routing still occurred.
    assert len(fake_hub.routed) == 1
    # No inbox id tail in the reply (persistence failed silently).
    assert "Message sent to Bob" in out
    assert "Inbox id:" not in out


def test_unknown_recipient_returns_error_and_no_inbox_entry(
        fake_hub, fresh_inbox):
    from app.tools_split.coordination import _tool_send_message

    out = _tool_send_message(
        to_agent="nobody", content="void",
        _caller_agent_id="a-alice",
    )
    assert "not found" in out.lower()
    assert fake_hub.routed == []
    assert fresh_inbox.unread_count("nobody") == 0
