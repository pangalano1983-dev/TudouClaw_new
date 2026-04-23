"""P0-A — ProjectMessage envelope (project chat)."""
from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


from app.project import Project, ProjectMessage  # noqa: E402


# ── dataclass shape ────────────────────────────────────────────


def test_new_fields_sane_defaults():
    m = ProjectMessage(sender="a1", content="hi")
    assert m.summary == ""
    assert m.key_fields == {}
    assert m.artifact_refs == []


def test_envelope_roundtrips():
    m = ProjectMessage(
        sender="a-alice", content="detail",
        summary="Decision: deploy next week",
        key_fields={"release": "v2", "date": "2026-05-01"},
        artifact_refs=["/ws/release_plan.md"],
    )
    d = m.to_dict()
    assert d["summary"] == "Decision: deploy next week"
    assert d["key_fields"]["release"] == "v2"
    assert d["artifact_refs"] == ["/ws/release_plan.md"]
    m2 = ProjectMessage.from_dict(d)
    assert m2.summary == m.summary
    assert m2.key_fields == m.key_fields
    assert m2.artifact_refs == m.artifact_refs


def test_legacy_dict_loads_without_envelope():
    legacy = {
        "id": "m1", "sender": "a-alice", "sender_name": "Alice",
        "content": "hi", "timestamp": 1.0,
    }
    m = ProjectMessage.from_dict(legacy)
    assert m.summary == ""
    assert m.key_fields == {}
    assert m.artifact_refs == []


# ── compact_text ────────────────────────────────────────────────


def test_compact_text_structured():
    m = ProjectMessage(
        sender="a-alice", content="full body " * 20,
        summary="Sprint complete",
        key_fields={"velocity": 42},
        artifact_refs=["/ws/retro.md"],
    )
    out = m.compact_text()
    assert "📣 Sprint complete" in out
    assert "42" in out
    assert "/ws/retro.md" in out
    assert "📄" in out


def test_compact_text_legacy_content_only():
    m = ProjectMessage(sender="a-alice", content="just chatty text")
    assert m.compact_text() == "just chatty text"


# ── post_message ────────────────────────────────────────────────


@pytest.fixture
def project():
    return Project(id="p-test", name="test")


def test_post_message_with_envelope(project):
    m = project.post_message(
        sender="a-alice", sender_name="Alice",
        summary="Ran the pipeline",
        key_fields={"stage": "passed"},
        artifact_refs=["/ws/run.log"],
    )
    assert m.summary == "Ran the pipeline"
    assert m.key_fields == {"stage": "passed"}
    assert m.artifact_refs == ["/ws/run.log"]


def test_post_message_auto_summary_for_long_content(project):
    long = "finding " * 200    # ~1600 chars
    m = project.post_message(
        sender="a-alice", sender_name="Alice",
        content=long,
    )
    assert m.summary
    assert len(m.summary) <= 801


def test_post_message_short_content_no_auto_summary(project):
    m = project.post_message(
        sender="a-alice", sender_name="Alice", content="ack")
    assert m.summary == ""
    assert m.content == "ack"
