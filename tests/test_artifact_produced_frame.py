"""artifact_produced frame — emitted on every new artifact landing in store.

Verifies:
- `ArtifactStore.put()` publishes a frame to ProgressBus
- Frame carries id/kind/label/size/mime/produced_at
- File-like artifacts get a `download_url` pointing at the portal route
- Non-file artifacts (RECORD, TEXT_BLOB) omit download_url
- Channel routing: agent:<id> when produced_by.agent_id set, else global
- Failures in bus don't corrupt artifact store (best-effort policy)
- Deterministic ids (_stable_id) still emit exactly once per put
"""
from __future__ import annotations

import time
import pytest

from app.agent_state.artifact import (
    Artifact, ArtifactKind, ArtifactStore, ProducedBy,
)
from app.progress_bus import get_bus


def _mk_artifact(**overrides) -> Artifact:
    """Helper: Artifact requires produced_at + produced_by; tests shouldn't
    care about every field — keep the builder terse."""
    defaults = dict(
        id="art_x", kind=ArtifactKind.TEXT_BLOB,
        value="x", label="x",
        produced_at=time.time(),
        produced_by=ProducedBy(),
        mime=None, size=None, ttl_s=None, metadata={},
    )
    defaults.update(overrides)
    return Artifact(**defaults)


def test_put_emits_artifact_produced_frame():
    store = ArtifactStore()
    bus = get_bus()
    sub = bus.subscribe("agent:test-artifact-1")
    try:
        art = _mk_artifact(
            id="art_test1", kind=ArtifactKind.FILE,
            value="/tmp/report.pptx", label="report.pptx",
            size=42000,
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            produced_by=ProducedBy(agent_id="test-artifact-1",
                                    task_id="t1", tool_id="write_file"),
        )
        store.put(art)
        f = sub.next(timeout=1.0)
        assert f is not None
        assert f.kind == "artifact_produced"
        assert f.data["artifact_id"] == "art_test1"
        assert f.data["kind"] == "file"
        assert f.data["label"] == "report.pptx"
        assert f.data["size"] == 42000
        assert "presentation" in f.data["mime"]
        # download_url points at the agent-artifact route
        assert f.data["download_url"] == "/api/agent_state/artifact/test-artifact-1/art_test1"
        assert f.data["produced_by"]["task_id"] == "t1"
        assert f.data["produced_by"]["tool_id"] == "write_file"
    finally:
        bus.unsubscribe(sub)


def test_file_without_label_derives_basename():
    store = ArtifactStore()
    bus = get_bus()
    sub = bus.subscribe("agent:test-basename")
    try:
        art = _mk_artifact(
            id="art_bn1", kind=ArtifactKind.DOCUMENT,
            value="/nested/path/to/deep/analysis.md",
            label="",
            produced_by=ProducedBy(agent_id="test-basename"),
        )
        store.put(art)
        f = sub.next(timeout=1.0)
        assert f.data["label"] == "analysis.md"
    finally:
        bus.unsubscribe(sub)


def test_non_file_artifact_no_download_url():
    store = ArtifactStore()
    bus = get_bus()
    sub = bus.subscribe("agent:test-nonfile")
    try:
        art = _mk_artifact(
            id="art_record1", kind=ArtifactKind.RECORD,
            value='{"some": "json"}',
            label="some record",
            produced_by=ProducedBy(agent_id="test-nonfile"),
        )
        store.put(art)
        f = sub.next(timeout=1.0)
        assert f.data["download_url"] == ""
        assert f.data["kind"] == "record"
    finally:
        bus.unsubscribe(sub)


def test_artifact_without_agent_id_goes_to_global():
    store = ArtifactStore()
    bus = get_bus()
    sub = bus.subscribe("global")
    try:
        art = _mk_artifact(
            id="art_global1", kind=ArtifactKind.TEXT_BLOB,
            value="a bit of text", label="snippet",
            produced_by=ProducedBy(),  # no agent_id
        )
        store.put(art)
        # Scan recent frames on global (other tests may publish here too)
        found = False
        for _ in range(30):
            f = sub.next(timeout=0.3)
            if f is None:
                break
            if f.kind == "artifact_produced" and f.data.get("artifact_id") == "art_global1":
                found = True
                assert f.data["download_url"] == ""
                break
        assert found, "frame for art_global1 should appear on global channel"
    finally:
        bus.unsubscribe(sub)


def test_artifact_value_not_leaked_to_frame():
    """Large artifact values (whole .md bodies) should NOT be in the frame
    payload — frontend only needs metadata + download URL."""
    store = ArtifactStore()
    bus = get_bus()
    sub = bus.subscribe("agent:test-noleak")
    try:
        huge_value = "x" * 50000
        art = _mk_artifact(
            id="art_noleak1", kind=ArtifactKind.TEXT_BLOB,
            value=huge_value, label="big text",
            produced_by=ProducedBy(agent_id="test-noleak"),
        )
        store.put(art)
        f = sub.next(timeout=1.0)
        assert f is not None
        import json as _json
        serialized = _json.dumps(f.data)
        assert huge_value not in serialized
    finally:
        bus.unsubscribe(sub)


def test_bus_failure_does_not_corrupt_store(monkeypatch):
    """If ProgressBus raises, the artifact MUST still be stored — bus
    emission is a side effect, not a prerequisite for persistence."""
    from app.agent_state import artifact as _amod
    def _boom(art):
        raise RuntimeError("bus is broken")
    monkeypatch.setattr(_amod, "_emit_artifact_produced", _boom)

    store = ArtifactStore()
    art = _mk_artifact(
        id="art_resilient1", kind=ArtifactKind.TEXT_BLOB,
        value="ok", label="text",
    )
    try:
        aid = store.put(art)
    except Exception as e:
        pytest.fail(f"put() should never raise from bus emission failure: {e}")
    assert store.get(aid) is not None


def test_frame_emitted_exactly_once_per_put():
    store = ArtifactStore()
    bus = get_bus()
    sub = bus.subscribe("agent:test-once")
    try:
        art = _mk_artifact(
            id="art_once1", kind=ArtifactKind.FILE,
            value="/tmp/x.txt", label="x.txt",
            produced_by=ProducedBy(agent_id="test-once"),
        )
        store.put(art)
        f1 = sub.next(timeout=1.0)
        assert f1 is not None
        f2 = sub.next(timeout=0.3)
        assert f2 is None, "put should emit exactly one frame per artifact"
    finally:
        bus.unsubscribe(sub)
