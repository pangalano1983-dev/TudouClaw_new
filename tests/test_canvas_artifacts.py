"""Tests for the canvas workflow artifact closed-loop.

Covers:
* shared dir creation + isolation per run
* pre/post-snapshot diff correctly identifies new files
* unchanged files are NOT re-registered (sha256 dedup)
* new artifacts get vars_key auto-generated
* mark_artifact promotion + tag merge
* audit log records every register / mark / read / delete
* noise-extension files registered but flagged
"""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import pytest

from app.canvas_artifacts import (
    ArtifactStore, ArtifactMetadata, _sanitize_for_var,
)


@pytest.fixture
def store():
    """Fresh store + per-test temp dir, cleaned on teardown."""
    with tempfile.TemporaryDirectory(prefix="tudou_artifacts_test_") as tmp:
        yield ArtifactStore(tmp)


# ── Pure helpers ───────────────────────────────────────────────────────


def test_sanitize_for_var_basics():
    assert _sanitize_for_var("topology.png") == "topology_png"
    assert _sanitize_for_var("deck.pptx") == "deck_pptx"
    assert _sanitize_for_var("./foo bar.md") == "foo_bar_md"
    assert _sanitize_for_var("中文.txt") == "_____txt" or _sanitize_for_var("中文.txt").endswith("_txt")


# ── Shared dir + snapshot ──────────────────────────────────────────────


def test_shared_dir_created_per_run(store):
    d1 = store.shared_dir("run-aaa")
    d2 = store.shared_dir("run-bbb")
    assert d1.exists() and d1.is_dir()
    assert d2.exists() and d2.is_dir()
    assert d1 != d2   # isolated per run


def test_snapshot_empty_dir(store):
    snap = store.snapshot_dir("run-fresh")
    assert snap == {}


def test_snapshot_picks_up_files(store):
    d = store.shared_dir("run-x")
    (d / "foo.png").write_bytes(b"PNG fake")
    (d / "bar.txt").write_text("hello")
    snap = store.snapshot_dir("run-x")
    assert set(snap.keys()) == {"foo.png", "bar.txt"}
    assert all(isinstance(v, int) and v > 0 for v in snap.values())


def test_snapshot_recurses_subdirs(store):
    d = store.shared_dir("run-y")
    sub = d / "subdir"
    sub.mkdir()
    (sub / "nested.md").write_text("# nested")
    snap = store.snapshot_dir("run-y")
    assert "subdir/nested.md" in snap


# ── Diff + register ────────────────────────────────────────────────────


def test_diff_new_file_registered(store):
    pre = store.snapshot_dir("run-1")    # empty
    d = store.shared_dir("run-1")
    (d / "topology.png").write_bytes(b"PNG bytes here")

    new = store.diff_and_register(
        "run-1", pre_snapshot=pre,
        producer_node_id="n_drawio", producer_agent_id="agent-A",
    )
    assert len(new) == 1
    art = new[0]
    assert art.name == "topology.png"
    assert art.rel_path == "topology.png"
    assert art.size_bytes == len(b"PNG bytes here")
    assert art.sha256   # non-empty hash
    assert art.producer_node_id == "n_drawio"
    assert art.producer_agent_id == "agent-A"
    assert art.vars_key == "n_drawio.file_topology_png"
    assert art.marked is False   # auto-detected


def test_diff_unchanged_file_not_reregistered(store):
    d = store.shared_dir("run-2")
    (d / "stable.txt").write_text("v1")
    pre = store.snapshot_dir("run-2")
    # Register first time
    new1 = store.diff_and_register(
        "run-2", pre_snapshot={},   # pretend this is the pre-snapshot for the FIRST node
        producer_node_id="n_a", producer_agent_id="agent-A",
    )
    assert len(new1) == 1
    # Second pass: the file is unchanged (snapshot includes its mtime)
    pre = store.snapshot_dir("run-2")
    new2 = store.diff_and_register(
        "run-2", pre_snapshot=pre,
        producer_node_id="n_b", producer_agent_id="agent-B",
    )
    assert len(new2) == 0   # unchanged → no new artifact


def test_diff_modified_file_reregistered(store):
    d = store.shared_dir("run-3")
    (d / "evolving.md").write_text("v1")
    pre = store.snapshot_dir("run-3")
    # Modify content + mtime
    time.sleep(0.01)
    (d / "evolving.md").write_text("v2 longer content")
    new = store.diff_and_register(
        "run-3", pre_snapshot=pre,
        producer_node_id="n_x", producer_agent_id="agent-X",
    )
    assert len(new) == 1
    assert new[0].name == "evolving.md"


def test_diff_idempotent_within_one_pass(store):
    d = store.shared_dir("run-4")
    (d / "a.png").write_bytes(b"a")
    (d / "b.png").write_bytes(b"b")
    pre = {}
    new1 = store.diff_and_register(
        "run-4", pre_snapshot=pre,
        producer_node_id="n_one", producer_agent_id="agent-O",
    )
    assert len(new1) == 2
    # Re-running with same pre but unchanged disk → 0 new artifacts
    pre = store.snapshot_dir("run-4")
    new2 = store.diff_and_register(
        "run-4", pre_snapshot=pre,
        producer_node_id="n_two", producer_agent_id="agent-T",
    )
    assert len(new2) == 0


def test_noise_extension_marked_as_noise(store):
    d = store.shared_dir("run-5")
    (d / "compile.log").write_text("...lots of log lines...")
    new = store.diff_and_register(
        "run-5", pre_snapshot={},
        producer_node_id="n_x", producer_agent_id="agent-X",
    )
    assert len(new) == 1
    assert new[0].marked is False
    # noise files get an auto-detected note in description
    assert "auto-detected" in (new[0].description or "")


# ── List / get / mark / delete ─────────────────────────────────────────


def test_list_round_trip(store):
    d = store.shared_dir("run-6")
    (d / "deck.pptx").write_bytes(b"pptx bytes")
    store.diff_and_register(
        "run-6", pre_snapshot={},
        producer_node_id="n_p", producer_agent_id="agent-P",
    )
    items = store.list_artifacts("run-6")
    assert len(items) == 1
    assert items[0].name == "deck.pptx"


def test_mark_artifact_promotes(store):
    d = store.shared_dir("run-7")
    (d / "report.md").write_text("# report")
    new = store.diff_and_register(
        "run-7", pre_snapshot={},
        producer_node_id="n_r", producer_agent_id="agent-R",
    )
    art_id = new[0].id
    assert new[0].marked is False
    updated = store.mark_artifact(
        "run-7", name_or_id=art_id,
        actor_agent_id="admin", actor_node_id="api:mark",
        description="final Q2 report",
        tags=["Q2", "report"],
    )
    assert updated is not None
    assert updated.marked is True
    assert updated.description == "final Q2 report"
    assert updated.tags == ["Q2", "report"]
    # Persisted across reload
    items = store.list_artifacts("run-7")
    assert items[0].marked is True
    assert items[0].tags == ["Q2", "report"]


def test_mark_by_name_works_too(store):
    d = store.shared_dir("run-8")
    (d / "topo.png").write_bytes(b"PNG")
    store.diff_and_register("run-8", pre_snapshot={},
                            producer_node_id="n_d", producer_agent_id="agent-D")
    updated = store.mark_artifact(
        "run-8", name_or_id="topo.png",
        actor_agent_id="admin", actor_node_id="api:mark",
        description="final diagram",
    )
    assert updated is not None
    assert updated.marked is True


def test_mark_dedups_tags(store):
    d = store.shared_dir("run-9")
    (d / "x.txt").write_text("x")
    store.diff_and_register("run-9", pre_snapshot={},
                            producer_node_id="n_a", producer_agent_id="agent-A")
    art_id = store.list_artifacts("run-9")[0].id
    store.mark_artifact("run-9", name_or_id=art_id,
                        actor_agent_id="u", actor_node_id="api",
                        tags=["A", "B"])
    store.mark_artifact("run-9", name_or_id=art_id,
                        actor_agent_id="u", actor_node_id="api",
                        tags=["B", "C"])
    assert store.list_artifacts("run-9")[0].tags == ["A", "B", "C"]


def test_delete_removes_file_and_index(store):
    d = store.shared_dir("run-10")
    (d / "to-delete.md").write_text("bye")
    store.diff_and_register("run-10", pre_snapshot={},
                            producer_node_id="n_x", producer_agent_id="agent-X")
    art_id = store.list_artifacts("run-10")[0].id
    ok = store.delete_artifact("run-10", art_id,
                                actor_agent_id="admin", actor_node_id="api")
    assert ok is True
    assert store.list_artifacts("run-10") == []
    assert not (d / "to-delete.md").exists()


def test_open_for_read_audit_trail(store):
    d = store.shared_dir("run-11")
    (d / "file.bin").write_bytes(b"binary content")
    store.diff_and_register("run-11", pre_snapshot={},
                            producer_node_id="n_p", producer_agent_id="agent-P")
    art_id = store.list_artifacts("run-11")[0].id
    res = store.open_for_read("run-11", art_id,
                                actor_agent_id="agent-Q", actor_node_id="n_consumer")
    assert res is not None
    art, full = res
    assert full.is_file()
    # Read should have appended an audit row
    rows, _ = store.read_audit("run-11")
    read_rows = [r for r in rows if r.get("action") == "read"]
    assert len(read_rows) == 1
    assert read_rows[0]["actor_agent_id"] == "agent-Q"
    assert read_rows[0]["actor_node_id"] == "n_consumer"
    assert read_rows[0]["artifact_id"] == art_id


# ── Audit log ──────────────────────────────────────────────────────────


def test_audit_records_register_event(store):
    d = store.shared_dir("run-12")
    (d / "out.png").write_bytes(b"png")
    store.diff_and_register("run-12", pre_snapshot={},
                            producer_node_id="n_d", producer_agent_id="agent-D")
    rows, _ = store.read_audit("run-12")
    register_rows = [r for r in rows if r.get("action") == "register"]
    assert len(register_rows) == 1
    assert register_rows[0]["actor_agent_id"] == "agent-D"
    assert register_rows[0]["name"] == "out.png"
    assert "sha256" in register_rows[0]


def test_audit_records_mark_event(store):
    d = store.shared_dir("run-13")
    (d / "f.txt").write_text("f")
    store.diff_and_register("run-13", pre_snapshot={},
                            producer_node_id="n_a", producer_agent_id="agent-A")
    art_id = store.list_artifacts("run-13")[0].id
    store.mark_artifact("run-13", name_or_id=art_id,
                        actor_agent_id="admin-user",
                        actor_node_id="api:mark",
                        description="approved",
                        tags=["v1"])
    rows, _ = store.read_audit("run-13")
    mark_rows = [r for r in rows if r.get("action") == "mark"]
    assert len(mark_rows) == 1
    assert mark_rows[0]["actor_agent_id"] == "admin-user"
    assert mark_rows[0]["description"] == "approved"
    assert mark_rows[0]["tags"] == ["v1"]


def test_audit_append_only_across_calls(store):
    d = store.shared_dir("run-14")
    # First batch
    (d / "a.txt").write_text("a")
    store.diff_and_register("run-14", pre_snapshot={},
                            producer_node_id="n_a", producer_agent_id="agent-A")
    rows1, off1 = store.read_audit("run-14")
    # Second batch
    pre = store.snapshot_dir("run-14")
    (d / "b.txt").write_text("b")
    store.diff_and_register("run-14", pre_snapshot=pre,
                            producer_node_id="n_b", producer_agent_id="agent-B")
    rows2, off2 = store.read_audit("run-14")
    assert off2 > off1
    assert len(rows2) > len(rows1)
    # Incremental read picks up just the delta
    delta, _ = store.read_audit("run-14", since_offset=off1)
    assert len(delta) == len(rows2) - len(rows1)
    assert all(r.get("ts", 0) >= rows1[-1].get("ts", 0) for r in delta)


# ── Closed-loop integration shape ──────────────────────────────────────


def test_closed_loop_var_key_format_matches_executor_contract(store):
    """The vars_key in the registered artifact must be the dotted form
    the executor expects to inject into run.vars. The executor strips
    the {node_id}. prefix when storing in the dict (see _execute_node)
    so this test asserts the full form is sane."""
    d = store.shared_dir("run-loop")
    (d / "diagram.png").write_bytes(b"png")
    new = store.diff_and_register(
        "run-loop", pre_snapshot={},
        producer_node_id="n_drawio", producer_agent_id="a16c",
    )
    art = new[0]
    # Format: "{node_id}.file_{sanitized_name}"
    assert art.vars_key == "n_drawio.file_diagram_png"
    # Suffix-only (what gets stored under vars after the executor strips
    # the node_id prefix) should be "file_diagram_png"
    suffix = art.vars_key.split(".", 1)[-1]
    assert suffix == "file_diagram_png"
