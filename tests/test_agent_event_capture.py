"""Tests for the project / meeting event-capture helper.

The helper lets non-streaming chat surfaces (project chat, meeting chat)
replay the tool_call / tool_result / ui_block events that happened
during an agent's chat turn — giving them UX parity with the streaming
agent page.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.agent_event_capture import (
    _MAX_EVENTS_PER_TURN,
    capture_events_since,
    snapshot_event_count,
)


def _fake_event(kind: str, data: dict | None = None, ts: float = 0.0):
    """Shape-compatible stand-in for app.agent_types.AgentEvent."""
    return SimpleNamespace(kind=kind, data=data or {}, timestamp=ts)


def _fake_agent(events=None):
    return SimpleNamespace(events=list(events or []))


# ── snapshot_event_count ─────────────────────────────────────────────

def test_snapshot_returns_zero_for_agent_without_events():
    agent = SimpleNamespace()  # no events attr
    assert snapshot_event_count(agent) == 0


def test_snapshot_returns_current_length():
    agent = _fake_agent([
        _fake_event("message"),
        _fake_event("tool_call"),
    ])
    assert snapshot_event_count(agent) == 2


# ── capture_events_since ─────────────────────────────────────────────

def test_capture_returns_empty_when_no_events():
    assert capture_events_since(_fake_agent(), 0) == []


def test_capture_returns_empty_when_no_events_after_cursor():
    agent = _fake_agent([_fake_event("tool_call")])
    assert capture_events_since(agent, 1) == []  # nothing added since


def test_capture_only_keeps_renderable_kinds():
    """message / thinking / plan_update should be filtered out — they
    either show up elsewhere or are internal noise."""
    agent = _fake_agent([
        _fake_event("message", {"text": "hi"}, ts=1.0),
        _fake_event("tool_call", {"name": "read_file",
                                  "args": '{"path":"x.py"}'}, ts=2.0),
        _fake_event("thinking", {"phase": "..."}, ts=3.0),
        _fake_event("tool_result", {"name": "read_file",
                                    "result": "file content"}, ts=4.0),
        _fake_event("plan_update", {"plan": "..."}, ts=5.0),
        _fake_event("ui_block", {"block": {"kind": "choice",
                                            "prompt": "go?",
                                            "options": []}}, ts=6.0),
    ])
    out = capture_events_since(agent, 0)
    kinds = [e["kind"] for e in out]
    assert kinds == ["tool_call", "tool_result", "ui_block"]


def test_capture_snapshot_then_capture_isolates_new_events():
    """The canonical usage: snapshot → chat → capture. Only events added
    DURING the chat window should be returned."""
    agent = _fake_agent([_fake_event("tool_call", ts=1.0)])  # "old" event
    cursor = snapshot_event_count(agent)
    # Simulate chat — agent emits one tool_call and one ui_block
    agent.events.append(_fake_event("tool_call", {"name": "bash"}, ts=2.0))
    agent.events.append(_fake_event("ui_block",
                                    {"block": {"kind": "choice",
                                               "prompt": "ok?",
                                               "options": []}}, ts=3.0))
    out = capture_events_since(agent, cursor)
    assert len(out) == 2
    assert out[0]["kind"] == "tool_call"
    assert out[0]["data"]["name"] == "bash"
    assert out[1]["kind"] == "ui_block"


def test_capture_truncates_long_tool_args():
    agent = _fake_agent([
        _fake_event("tool_call", {"name": "write_file",
                                  "args": "x" * 5000}),
    ])
    out = capture_events_since(agent, 0)
    # Args truncated to <= 200 chars, ending with "..."
    assert len(out[0]["data"]["args"]) <= 200
    assert out[0]["data"]["args"].endswith("...")


def test_capture_truncates_long_tool_results():
    agent = _fake_agent([
        _fake_event("tool_result", {"name": "bash",
                                    "result": "Y" * 5000}),
    ])
    out = capture_events_since(agent, 0)
    assert len(out[0]["data"]["result_preview"]) <= 400
    assert out[0]["data"]["result_preview"].endswith("...")


def test_capture_enforces_max_events_per_turn():
    events = [_fake_event("tool_call", {"name": f"t{i}"})
              for i in range(_MAX_EVENTS_PER_TURN + 10)]
    agent = _fake_agent(events)
    out = capture_events_since(agent, 0)
    # _MAX cap events + one synthetic ellipsis marker.
    assert len(out) == _MAX_EVENTS_PER_TURN + 1
    assert out[-1]["kind"] == "ellipsis"
    assert out[-1]["data"]["dropped"] == 10


def test_capture_preserves_timestamps():
    agent = _fake_agent([
        _fake_event("tool_call", {"name": "read_file"}, ts=1234.5),
    ])
    out = capture_events_since(agent, 0)
    assert out[0]["timestamp"] == 1234.5


# ── ProjectMessage / MeetingMessage round-trip ───────────────────────

def test_project_message_blocks_roundtrip():
    from app.project import ProjectMessage
    original = ProjectMessage(
        sender="agent1", content="done",
        blocks=[{"kind": "ui_block",
                 "data": {"block": {"kind": "choice",
                                    "prompt": "?",
                                    "options": []}}}],
    )
    d = original.to_dict()
    restored = ProjectMessage.from_dict(d)
    assert restored.blocks == original.blocks


def test_project_message_from_old_dict_gets_empty_blocks():
    """Backward-compat: persisted messages from before this change
    don't have a blocks key — loading must not crash."""
    from app.project import ProjectMessage
    old_style = {
        "id": "x", "sender": "a", "content": "hi",
        # no "blocks" key
    }
    msg = ProjectMessage.from_dict(old_style)
    assert msg.blocks == []


def test_meeting_message_blocks_roundtrip():
    from app.meeting import MeetingMessage
    original = MeetingMessage(
        sender="agent1", content="done",
        blocks=[{"kind": "tool_call",
                 "data": {"name": "bash", "args": "ls"}}],
    )
    d = original.to_dict()
    restored = MeetingMessage.from_dict(d)
    assert restored.blocks == original.blocks


def test_meeting_message_from_old_dict_gets_empty_blocks():
    from app.meeting import MeetingMessage
    old_style = {"sender": "a", "content": "hi"}
    msg = MeetingMessage.from_dict(old_style)
    assert msg.blocks == []


# ── post_message / add_message accept blocks ─────────────────────────

def test_project_post_message_stores_blocks():
    from app.project import Project
    project = Project(id="p1", name="Demo")
    blocks = [{"kind": "tool_call", "data": {"name": "read_file"}}]
    msg = project.post_message(
        sender="agent1", sender_name="coder-Alice",
        content="done", blocks=blocks,
    )
    assert msg.blocks == blocks
    assert project.chat_history[-1].blocks == blocks


def test_meeting_add_message_stores_blocks():
    from app.meeting import Meeting
    meeting = Meeting(id="m1", title="demo")
    blocks = [{"kind": "ui_block",
               "data": {"block": {"kind": "checklist",
                                  "prompt": "Todos",
                                  "items": []}}}]
    msg = meeting.add_message(sender="agent1", content="done",
                              blocks=blocks)
    assert msg.blocks == blocks
    assert meeting.messages[-1].blocks == blocks
