"""scan_deliverable_dir must ignore workspace meta + tool_outputs.

Bug: spill files under workspace/tool_outputs/ and the agent's own
meta docs (Project.md / Scheduled.md / MCP.md / Tasks.md / Skills.md
/ ActiveThinking.md) were being ingested as artifacts, then rendered
as download cards on the chat bubble. They're infrastructure, not
deliverables.

Fix: scan_deliverable_dir skips {tool_outputs, skills, cache, __pycache__}
subdirs and the 6 workspace meta files at the root level.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


@pytest.fixture
def ws(tmp_path):
    """Build a realistic agent workspace layout."""
    root = tmp_path / "workspace"
    root.mkdir()
    # Workspace meta files (should be EXCLUDED)
    for name in ("Project.md", "Skills.md", "MCP.md", "Tasks.md",
                 "Scheduled.md", "ActiveThinking.md"):
        (root / name).write_text(f"# {name}\n")
    # tool_outputs/ subdir with spills (should be EXCLUDED)
    tool_out = root / "tool_outputs"
    tool_out.mkdir()
    (tool_out / "20260422_181703_read_file_abc.md").write_text("# Spilled\n")
    (tool_out / "20260422_181707_bash_def.md").write_text("# Spilled\n")
    # skills/ bundles (should be EXCLUDED)
    (root / "skills").mkdir()
    (root / "skills" / "my-skill").mkdir()
    (root / "skills" / "my-skill" / "SKILL.md").write_text("# Skill\n")
    # Real deliverables (should be KEPT)
    (root / "report.docx").write_text("fake docx")
    (root / "analysis.md").write_text("# Real user-facing doc\n")
    subout = root / "output"
    subout.mkdir()
    (subout / "summary.pdf").write_text("fake pdf")
    return root


def _scan(ws_path):
    from app.agent_state.extractors import scan_deliverable_dir
    from app.agent_state.artifact import ArtifactStore
    store = ArtifactStore()
    added = scan_deliverable_dir(store, str(ws_path))
    return store, added


def test_tool_outputs_dir_is_excluded(ws):
    store, _ = _scan(ws)
    # Check against path COMPONENTS, not substrings — pytest tmp paths
    # may incidentally include the string "tool_outputs".
    leaked = [a.value for a in store.all()
              if "tool_outputs" in os.path.relpath(a.value, ws).split(os.sep)]
    assert not leaked, f"tool_outputs files leaked: {leaked}"


def test_workspace_meta_files_excluded(ws):
    store, _ = _scan(ws)
    paths = [os.path.basename(a.value) for a in store.all()]
    for meta in ("Project.md", "Skills.md", "MCP.md", "Tasks.md",
                 "Scheduled.md", "ActiveThinking.md"):
        assert meta not in paths, f"{meta} should be excluded"


def test_skills_subdir_excluded(ws):
    store, _ = _scan(ws)
    paths = [a.value for a in store.all()]
    assert not any("/skills/" in p for p in paths), \
        f"skills/ dir leaked: {paths}"


def test_real_deliverables_still_ingested(ws):
    store, _ = _scan(ws)
    names = [os.path.basename(a.value) for a in store.all()]
    # These should all be kept.
    assert "report.docx" in names
    assert "analysis.md" in names
    assert "summary.pdf" in names


def test_same_name_in_subdir_not_excluded(tmp_path):
    """A legitimate deliverable named Project.md inside a subdir
    (e.g. output/Project.md) is NOT the agent's meta file — keep it.
    Only the workspace-root meta files are excluded."""
    root = tmp_path / "ws"
    root.mkdir()
    # Meta at root — excluded
    (root / "Project.md").write_text("meta")
    # Same filename in subdir — this IS a deliverable
    sub = root / "output"
    sub.mkdir()
    (sub / "Project.md").write_text("user-made")
    store, _ = _scan(root)
    paths = [a.value for a in store.all()]
    # Root one excluded, subdir one kept.
    assert any(p.endswith("output/Project.md") for p in paths)
    assert not any(p.endswith("workspace/Project.md") or
                   p == str(root / "Project.md") for p in paths)
