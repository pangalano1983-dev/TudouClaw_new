"""Day 5 — `check_inbox` / `ack_message` / `reply_message` tool tests.

These exercise the three LLM-callable tools added to coordination.py.
They follow the same pattern as `test_send_message_inbox.py`: stub the
hub (so legacy routing from reply_message can be observed) and use a
tmp_path-backed inbox store.
"""
from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ── fake hub ────────────────────────────────────────────────────────


class _FakeAgent:
    def __init__(self, aid, name):
        self.id, self.name = aid, name


class _FakeHub:
    def __init__(self):
        self.agents: dict[str, _FakeAgent] = {}
        self.routed: list[tuple] = []

    def get_agent(self, k):
        return self.agents.get(k)

    def route_message(self, frm, to, content, msg_type="task",
                      source="api", metadata=None):
        self.routed.append((frm, to, content, msg_type, source))


@pytest.fixture
def fake_hub(monkeypatch):
    hub = _FakeHub()
    hub.agents["a-alice"] = _FakeAgent("a-alice", "Alice")
    hub.agents["a-bob"] = _FakeAgent("a-bob", "Bob")
    import app.tools_split._common as common
    import app.tools_split.coordination as coordination
    monkeypatch.setattr(common, "_get_hub", lambda: hub)
    monkeypatch.setattr(coordination, "_get_hub", lambda: hub)
    return hub


@pytest.fixture
def store(tmp_path, monkeypatch):
    from app import inbox
    inbox.reset_store_for_test()
    db = tmp_path / "inbox.db"
    monkeypatch.setenv("TUDOU_CLAW_DATA_DIR", str(tmp_path))
    s = inbox.get_store(db_path=str(db))
    yield s
    inbox.reset_store_for_test()


# ── check_inbox ─────────────────────────────────────────────────────


def test_check_inbox_empty(fake_hub, store):
    from app.tools_split.coordination import _tool_check_inbox
    out = _tool_check_inbox(_caller_agent_id="a-alice")
    assert "empty" in out.lower()


def test_check_inbox_lists_unread(fake_hub, store):
    from app.tools_split.coordination import _tool_check_inbox
    mid = store.send(to_agent="a-alice", from_agent="a-bob",
                     content="ping alice")
    out = _tool_check_inbox(_caller_agent_id="a-alice")
    assert "ping alice" in out
    assert mid in out
    assert "a-bob" in out
    # Still unread — check_inbox is read-only.
    assert store.unread_count("a-alice") == 1


def test_check_inbox_missing_caller_errors(fake_hub, store):
    from app.tools_split.coordination import _tool_check_inbox
    out = _tool_check_inbox()
    assert out.startswith("Error")


def test_check_inbox_limit_enforced(fake_hub, store):
    from app.tools_split.coordination import _tool_check_inbox
    for i in range(30):
        store.send(to_agent="a-alice", from_agent="a-bob",
                   content=f"msg {i}")
    out = _tool_check_inbox(limit=5, _caller_agent_id="a-alice")
    # Count per-message markers.
    assert out.count("[NEW ") == 5


def test_check_inbox_include_read(fake_hub, store):
    from app.tools_split.coordination import _tool_check_inbox
    mid = store.send(to_agent="a-alice", from_agent="a-bob",
                     content="older ping")
    store.mark_read([mid], "a-alice")
    # Without include_read — empty
    out1 = _tool_check_inbox(_caller_agent_id="a-alice")
    assert "empty" in out1.lower()
    # With include_read — should surface it
    out2 = _tool_check_inbox(include_read=True,
                             _caller_agent_id="a-alice")
    assert "older ping" in out2
    assert "[read" in out2


# ── ack_message ─────────────────────────────────────────────────────


def test_ack_message_single(fake_hub, store):
    from app.tools_split.coordination import _tool_ack_message
    mid = store.send(to_agent="a-alice", from_agent="a-bob",
                     content="to ack")
    out = _tool_ack_message(message_ids=mid,
                            _caller_agent_id="a-alice")
    assert "Acked 1/1" in out
    msg = store.get_by_id(mid)
    assert msg.state == "acked"


def test_ack_message_multiple_comma_and_whitespace(fake_hub, store):
    from app.tools_split.coordination import _tool_ack_message
    ids = [store.send(to_agent="a-alice", from_agent="a-bob",
                      content=f"m{i}") for i in range(3)]
    combined = f"{ids[0]}, {ids[1]} {ids[2]}"
    out = _tool_ack_message(message_ids=combined,
                            _caller_agent_id="a-alice")
    assert "Acked 3/3" in out
    for mid in ids:
        assert store.get_by_id(mid).state == "acked"


def test_ack_message_skips_foreign(fake_hub, store):
    from app.tools_split.coordination import _tool_ack_message
    mine = store.send(to_agent="a-alice", from_agent="a-bob", content="mine")
    theirs = store.send(to_agent="a-bob", from_agent="a-alice",
                        content="not mine")
    out = _tool_ack_message(message_ids=f"{mine},{theirs}",
                            _caller_agent_id="a-alice")
    assert "Acked 1/2" in out
    assert store.get_by_id(mine).state == "acked"
    assert store.get_by_id(theirs).state == "new"


def test_ack_message_empty_ids_errors(fake_hub, store):
    from app.tools_split.coordination import _tool_ack_message
    out = _tool_ack_message(message_ids="",
                            _caller_agent_id="a-alice")
    assert out.startswith("Error")


def test_ack_message_missing_caller_errors(fake_hub, store):
    from app.tools_split.coordination import _tool_ack_message
    out = _tool_ack_message(message_ids="xyz")
    assert out.startswith("Error")


# ── reply_message ───────────────────────────────────────────────────


def test_reply_message_preserves_thread(fake_hub, store):
    from app.tools_split.coordination import _tool_reply_message
    # Bob pings Alice.
    orig = store.send(to_agent="a-alice", from_agent="a-bob",
                      content="status?", thread_id="t-99")
    out = _tool_reply_message(message_id=orig, content="all good",
                              _caller_agent_id="a-alice")
    assert "Reply sent to a-bob" in out
    assert "thread t-99" in out
    # New message exists on thread and points at the original.
    thread = store.get_thread("t-99")
    assert len(thread) == 2
    reply = thread[1]
    assert reply.from_agent == "a-alice"
    assert reply.to_agent == "a-bob"
    assert reply.reply_to == orig
    assert "all good" in reply.content


def test_reply_message_defaults_thread_to_original_id(fake_hub, store):
    from app.tools_split.coordination import _tool_reply_message
    orig = store.send(to_agent="a-alice", from_agent="a-bob", content="hi")
    # No explicit thread_id on original; the store default is thread=self.
    _tool_reply_message(message_id=orig, content="hey back",
                        _caller_agent_id="a-alice")
    thread = store.get_thread(orig)
    assert len(thread) == 2
    assert thread[1].reply_to == orig


def test_reply_message_mirrors_to_hub(fake_hub, store):
    from app.tools_split.coordination import _tool_reply_message
    orig = store.send(to_agent="a-alice", from_agent="a-bob", content="ping")
    _tool_reply_message(message_id=orig, content="pong",
                        _caller_agent_id="a-alice")
    assert len(fake_hub.routed) == 1
    frm, to, content, msg_type, source = fake_hub.routed[0]
    assert frm == "a-alice" and to == "a-bob"
    assert "pong" in content
    assert msg_type == "reply"
    assert source == "tool_reply_message"


def test_reply_message_refuses_if_not_addressed_to_caller(fake_hub, store):
    from app.tools_split.coordination import _tool_reply_message
    # Message was sent to Bob, not Alice.
    orig = store.send(to_agent="a-bob", from_agent="a-alice",
                      content="for bob only")
    out = _tool_reply_message(message_id=orig, content="sneaky",
                              _caller_agent_id="a-alice")
    assert "cannot reply" in out
    # No reply was persisted.
    assert len(store.get_thread(orig)) == 1
    # No hub routing either.
    assert fake_hub.routed == []


def test_reply_message_unknown_id_errors(fake_hub, store):
    from app.tools_split.coordination import _tool_reply_message
    out = _tool_reply_message(message_id="msg_does_not_exist",
                              content="whatever",
                              _caller_agent_id="a-alice")
    assert "not found" in out.lower()


def test_reply_message_requires_caller_and_fields(fake_hub, store):
    from app.tools_split.coordination import _tool_reply_message
    # Missing caller
    out1 = _tool_reply_message(message_id="x", content="y")
    assert out1.startswith("Error")
    # Missing content
    out2 = _tool_reply_message(message_id="", content="",
                               _caller_agent_id="a-alice")
    assert out2.startswith("Error")


# ── schema / registry wiring ────────────────────────────────────────


def test_tools_registered_in_dispatcher():
    from app.tools import _TOOL_FUNCS
    for name in ("check_inbox", "ack_message", "reply_message"):
        assert name in _TOOL_FUNCS, f"{name} missing from dispatcher"


def test_tools_have_openai_schemas():
    from app.tools import TOOL_DEFINITIONS
    names = {
        t["function"]["name"] for t in TOOL_DEFINITIONS
        if isinstance(t, dict) and t.get("type") == "function"
    }
    for name in ("check_inbox", "ack_message", "reply_message"):
        assert name in names, f"{name} missing from TOOL_DEFINITIONS"


def test_priority_flows_through_reply(fake_hub, store):
    from app.tools_split.coordination import _tool_reply_message
    orig = store.send(to_agent="a-alice", from_agent="a-bob", content="?")
    _tool_reply_message(message_id=orig, content="!",
                        priority="urgent",
                        _caller_agent_id="a-alice")
    new_msgs = store.fetch_unread("a-bob")
    assert len(new_msgs) == 1
    assert new_msgs[0].priority == "urgent"
