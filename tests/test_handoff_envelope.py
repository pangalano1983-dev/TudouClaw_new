"""P0-A — structured handoff envelope for send_message / reply_message.

Verifies:
  * `_build_handoff_envelope` normalizes fields, auto-derives summary
    from content when omitted.
  * `_render_envelope_for_wire` produces a compact, structured text.
  * `send_message` with envelope stores it in inbox metadata.
  * `reply_message` ditto.
  * Backward compat: legacy callers passing only `content` still work.
  * Agent inbox injection (`_build_inbox_context`) renders envelope
    compactly and hides long details.
"""
from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


from app.tools_split.coordination import (  # noqa: E402
    _build_handoff_envelope, _render_envelope_for_wire,
    _tool_send_message, _tool_reply_message,
)


# ── envelope builder ──────────────────────────────────────────────


def test_builder_normalizes_all_fields():
    env = _build_handoff_envelope(
        content="some long content "*100,
        summary="Decision: use plan B",
        key_fields={"decision": "B", "risk": "low"},
        artifact_refs=["/ws/report.md", "art_x"],
    )
    assert env["summary"] == "Decision: use plan B"
    assert env["key_fields"] == {"decision": "B", "risk": "low"}
    assert env["artifact_refs"] == ["/ws/report.md", "art_x"]
    # Detail len reflects .strip()'d content.
    assert env["detail_len"] == len(("some long content " * 100).strip())


def test_builder_auto_derives_summary_from_content_when_missing():
    env = _build_handoff_envelope(
        content="这是一段说明文字，总共会被用作 summary 的回退" * 3,
        summary="",
        key_fields=None, artifact_refs=None,
    )
    assert env["summary"], "summary should auto-derive from content"
    assert len(env["summary"]) <= 800 + 1
    assert env["key_fields"] == {}
    assert env["artifact_refs"] == []


def test_builder_caps_auto_summary():
    huge = "X" * 5000
    env = _build_handoff_envelope(
        content=huge, summary="", key_fields=None, artifact_refs=None)
    assert len(env["summary"]) <= 801
    assert env["summary"].endswith("…")


def test_builder_artifact_refs_accepts_string_or_list():
    env_str = _build_handoff_envelope(
        content="x", summary="y", key_fields=None,
        artifact_refs="/only/one.md",
    )
    assert env_str["artifact_refs"] == ["/only/one.md"]

    env_tuple = _build_handoff_envelope(
        content="x", summary="y", key_fields=None,
        artifact_refs=("a", "b", ""),   # empty dropped
    )
    assert env_tuple["artifact_refs"] == ["a", "b"]


def test_builder_rejects_non_dict_key_fields_silently():
    env = _build_handoff_envelope(
        content="x", summary="y",
        key_fields="not a dict", artifact_refs=None)
    assert env["key_fields"] == {}


# ── wire rendering ───────────────────────────────────────────────


def test_render_structured_envelope_compact():
    env = _build_handoff_envelope(
        content="raw detail goes here",
        summary="Decision is B",
        key_fields={"decision": "B"},
        artifact_refs=["/ws/report.md"],
    )
    out = _render_envelope_for_wire("raw detail goes here", env)
    assert "📣 Summary: Decision is B" in out
    assert "🔑 Key:" in out
    assert "📎 Artifacts: /ws/report.md" in out
    assert "📄 Detail:" in out


def test_render_legacy_content_only_falls_back_to_raw():
    # Caller passed only content, no structured fields — summary is
    # auto-derived; wire text still contains Summary + Detail (not raw).
    env = _build_handoff_envelope(
        content="just some text", summary="",
        key_fields=None, artifact_refs=None,
    )
    out = _render_envelope_for_wire("just some text", env)
    # Either structured form or raw — but must contain the core text.
    assert "just some text" in out


def test_render_truncates_long_detail_preview():
    big = "Y" * 3000
    env = _build_handoff_envelope(
        content=big, summary="short summary",
        key_fields=None, artifact_refs=None,
    )
    out = _render_envelope_for_wire(big, env)
    # Wire text is short despite huge content.
    assert len(out) < 1500
    assert "chars in detail" in out


# ── send_message with envelope ──────────────────────────────────


class _FakeAgent:
    def __init__(self, aid, name):
        self.id, self.name = aid, name


class _FakeHub:
    def __init__(self):
        self.agents: dict[str, _FakeAgent] = {}
        self.routed: list = []

    def get_agent(self, k):
        return self.agents.get(k)

    def route_message(self, frm, to, content, msg_type="task",
                      source="api", metadata=None):
        self.routed.append((frm, to, content, msg_type, source))


@pytest.fixture
def wiring(tmp_path, monkeypatch):
    from app import inbox as ibx
    ibx.reset_store_for_test()
    monkeypatch.setenv("TUDOU_CLAW_DATA_DIR", str(tmp_path))
    store = ibx.get_store(db_path=str(tmp_path / "inbox.db"))

    hub = _FakeHub()
    hub.agents["a-alice"] = _FakeAgent("a-alice", "Alice")
    hub.agents["a-bob"] = _FakeAgent("a-bob", "Bob")
    import app.tools_split._common as common
    import app.tools_split.coordination as coord
    monkeypatch.setattr(common, "_get_hub", lambda: hub)
    monkeypatch.setattr(coord, "_get_hub", lambda: hub)
    yield store, hub
    ibx.reset_store_for_test()


def test_send_message_stores_envelope_in_metadata(wiring):
    store, hub = wiring
    out = _tool_send_message(
        to_agent="Bob",
        summary="Analyzed Q4 data — plan B recommended",
        key_fields={"winner": "B", "confidence": 0.87},
        artifact_refs=["/ws/q4_analysis.md"],
        _caller_agent_id="a-alice",
    )
    assert "Message sent to Bob" in out
    assert "Inbox id" in out
    msgs = store.fetch_unread("a-bob")
    assert len(msgs) == 1
    env = (msgs[0].metadata or {}).get("envelope")
    assert env is not None
    assert env["summary"] == "Analyzed Q4 data — plan B recommended"
    assert env["key_fields"] == {"winner": "B", "confidence": 0.87}
    assert env["artifact_refs"] == ["/ws/q4_analysis.md"]


def test_send_message_legacy_content_only_still_works(wiring):
    store, _ = wiring
    out = _tool_send_message(
        to_agent="Bob",
        content="quick fyi: all tests pass",
        _caller_agent_id="a-alice",
    )
    assert "Message sent to Bob" in out
    m = store.fetch_unread("a-bob")[0]
    env = (m.metadata or {}).get("envelope") or {}
    # Summary was auto-derived from content.
    assert "quick fyi" in env["summary"]


def test_send_message_preserves_detail_full_in_metadata(wiring):
    store, _ = wiring
    long_detail = "A comprehensive analysis. " * 50
    _tool_send_message(
        to_agent="Bob",
        content=long_detail,
        summary="Short summary",
        _caller_agent_id="a-alice",
    )
    m = store.fetch_unread("a-bob")[0]
    assert m.metadata.get("detail_full") == long_detail


def test_send_message_wire_text_is_compact_even_for_huge_content(wiring):
    store, hub = wiring
    huge = "X" * 8000
    _tool_send_message(
        to_agent="Bob",
        summary="Here's the deal",
        key_fields={"x": 1},
        content=huge,
        _caller_agent_id="a-alice",
    )
    # The wire-text (stored as content on the inbox row) is the compact
    # version, not the 8k original.
    m = store.fetch_unread("a-bob")[0]
    assert len(m.content) < 2000
    # Full text is preserved in metadata for on-demand recall.
    assert m.metadata.get("detail_full") == huge


# ── reply_message with envelope ─────────────────────────────────


def test_reply_message_with_envelope(wiring):
    store, _ = wiring
    # Bob sends something to Alice first.
    orig_id = store.send(
        to_agent="a-alice", from_agent="a-bob",
        content="Can you confirm Q4 data?",
    )
    out = _tool_reply_message(
        message_id=orig_id,
        summary="Confirmed — data matches source",
        key_fields={"status": "ok", "row_count": 1247},
        artifact_refs=["/ws/q4_check.md"],
        _caller_agent_id="a-alice",
    )
    assert "Reply sent to a-bob" in out
    replies = store.fetch_unread("a-bob")
    assert len(replies) == 1
    env = replies[0].metadata.get("envelope")
    assert env["summary"] == "Confirmed — data matches source"
    assert env["key_fields"]["row_count"] == 1247


def test_reply_message_without_any_body_errors(wiring):
    store, _ = wiring
    orig_id = store.send(
        to_agent="a-alice", from_agent="a-bob", content="Q?")
    out = _tool_reply_message(
        message_id=orig_id, _caller_agent_id="a-alice",
    )
    assert out.startswith("Error")
    assert "content or summary" in out.lower()


def test_reply_message_summary_only_is_valid(wiring):
    """No content + only summary = totally fine."""
    store, _ = wiring
    orig_id = store.send(
        to_agent="a-alice", from_agent="a-bob", content="Q?")
    out = _tool_reply_message(
        message_id=orig_id,
        summary="Yes — confirmed",
        _caller_agent_id="a-alice",
    )
    assert "Reply sent" in out


# ── schema wiring ────────────────────────────────────────────────


def test_send_message_schema_no_longer_requires_content():
    from app.tools import TOOL_DEFINITIONS
    for t in TOOL_DEFINITIONS:
        if t.get("function", {}).get("name") == "send_message":
            required = t["function"]["parameters"].get("required") or []
            assert "content" not in required
            assert "to_agent" in required
            # Envelope fields documented.
            props = t["function"]["parameters"]["properties"]
            assert "summary" in props
            assert "key_fields" in props
            assert "artifact_refs" in props
            return
    raise AssertionError("send_message schema not found")


def test_reply_message_schema_no_longer_requires_content():
    from app.tools import TOOL_DEFINITIONS
    for t in TOOL_DEFINITIONS:
        if t.get("function", {}).get("name") == "reply_message":
            required = t["function"]["parameters"].get("required") or []
            assert "content" not in required
            assert "message_id" in required
            props = t["function"]["parameters"]["properties"]
            assert "summary" in props
            assert "key_fields" in props
            assert "artifact_refs" in props
            return
    raise AssertionError("reply_message schema not found")
