"""P0-A — Meeting chat envelope fields on MeetingMessage.

Verifies:
  * New fields roundtrip via to_dict / from_dict
  * Legacy messages (old JSON without envelope fields) still load
  * add_message accepts envelope kwargs
  * Auto-derives summary from long content when agent didn't supply one
  * compact_text renders envelope / falls back to content
"""
from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


from app.meeting import Meeting, MeetingMessage  # noqa: E402


# ── dataclass shape ────────────────────────────────────────────


def test_new_fields_have_sane_defaults():
    m = MeetingMessage(sender="a1", content="hi")
    assert m.summary == ""
    assert m.key_fields == {}
    assert m.artifact_refs == []


def test_envelope_roundtrips_through_to_dict_from_dict():
    m = MeetingMessage(
        sender="a-alice", content="full detail body",
        summary="decision is B", key_fields={"winner": "B"},
        artifact_refs=["/ws/report.md"],
    )
    d = m.to_dict()
    assert d["summary"] == "decision is B"
    assert d["key_fields"] == {"winner": "B"}
    assert d["artifact_refs"] == ["/ws/report.md"]
    m2 = MeetingMessage.from_dict(d)
    assert m2.summary == m.summary
    assert m2.key_fields == m.key_fields
    assert m2.artifact_refs == m.artifact_refs


def test_legacy_dict_without_envelope_still_loads():
    # Older persisted transcript rows don't have these fields.
    legacy = {
        "id": "m1", "sender": "a-alice", "sender_name": "Alice",
        "role": "agent", "content": "hello", "attachments": [],
        "created_at": 1.0,
    }
    m = MeetingMessage.from_dict(legacy)
    assert m.summary == ""
    assert m.key_fields == {}
    assert m.artifact_refs == []
    assert m.content == "hello"


# ── compact_text rendering ────────────────────────────────────


def test_compact_text_renders_structured_envelope():
    m = MeetingMessage(
        sender="a-alice", content="full detail body " * 20,
        summary="Decision: plan B wins",
        key_fields={"winner": "B", "score": 0.87},
        artifact_refs=["/ws/analysis.md"],
    )
    out = m.compact_text()
    assert "📣 Decision: plan B wins" in out
    assert "🔑" in out
    assert "/ws/analysis.md" in out
    assert "📄" in out    # detail preview


def test_compact_text_summary_only_no_content():
    m = MeetingMessage(
        sender="a-alice",
        summary="All tests pass",
        key_fields={"pass": 52, "fail": 0},
    )
    out = m.compact_text()
    assert "All tests pass" in out
    assert "52" in out
    # No detail block since content is empty.
    assert "📄" not in out


def test_compact_text_detail_preview_truncated():
    huge = "X" * 3000
    m = MeetingMessage(
        sender="a-alice", content=huge,
        summary="short",
    )
    out = m.compact_text(detail_preview_chars=400)
    assert len(out) < 600   # compact even with 3k content
    assert "X" * 400 in out
    assert "…" in out


def test_compact_text_no_envelope_falls_back_to_raw():
    m = MeetingMessage(sender="a-alice", content="just raw content")
    assert m.compact_text() == "just raw content"


def test_compact_text_empty_message_returns_empty():
    assert MeetingMessage(sender="a").compact_text() == ""


# ── Meeting.add_message ───────────────────────────────────────


@pytest.fixture
def meeting():
    return Meeting(id="m-test", title="test meeting")


def test_add_message_with_envelope(meeting):
    m = meeting.add_message(
        sender="a-alice",
        summary="Decision: B",
        key_fields={"winner": "B"},
        artifact_refs=["/ws/x.md"],
    )
    assert m.summary == "Decision: B"
    assert m.key_fields == {"winner": "B"}
    assert m.artifact_refs == ["/ws/x.md"]


def test_add_message_legacy_content_only_still_works(meeting):
    m = meeting.add_message(sender="a-alice", content="hello everyone")
    # Short content → no auto-summary.
    assert m.content == "hello everyone"
    assert m.summary == ""


def test_add_message_auto_derives_summary_for_long_content(meeting):
    long_body = "important finding " * 60   # ~1060 chars
    m = meeting.add_message(sender="a-alice", content=long_body)
    # Long content → summary auto-filled from head.
    assert m.summary
    assert len(m.summary) <= 801
    assert m.content == long_body   # raw kept


def test_add_message_short_content_no_summary(meeting):
    m = meeting.add_message(sender="a-alice", content="ack")
    assert m.summary == ""


def test_add_message_summary_beats_auto_derive(meeting):
    """If caller explicitly passes summary, don't overwrite with auto-derived."""
    m = meeting.add_message(
        sender="a-alice",
        content="a" * 2000,
        summary="My explicit summary",
    )
    assert m.summary == "My explicit summary"


# ── transcript compacting end-to-end ──────────────────────────


def test_transcript_renders_compact_when_envelope_present(meeting):
    meeting.add_message(
        sender="a-alice",
        summary="Completed data ingest",
        key_fields={"rows": 50000},
        artifact_refs=["/ws/data.parquet"],
    )
    meeting.add_message(
        sender="a-bob", content="Thanks, will write the report next.",
    )
    # Rendered form of first message is compact; second is raw.
    lines = [m.compact_text() for m in meeting.messages]
    assert "📣" in lines[0]
    assert "rows" in lines[0]
    assert "Thanks" in lines[1] and "📣" not in lines[1]
