"""Knowledge module must honor TUDOU_CLAW_DATA_DIR env.

Regression guard: historically ``app/knowledge.py`` hard-coded
``Path.home() / ".tudou_claw"`` and every pytest run polluted the
user's real shared_knowledge.json with fixture entries ("Python
style guide", "X", "Updated", "A", "B", "C"). That produced 36
garbage rows that had to be cleaned manually.

This test locks in env-override semantics so CI can never pollute
production again.
"""
from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _fresh_import(env_dir: Path):
    """Re-import app.knowledge with the env pointing at env_dir."""
    os.environ["TUDOU_CLAW_DATA_DIR"] = str(env_dir)
    # Drop cached module + in-memory entry cache so the new path is picked up
    for mod in list(sys.modules):
        if mod == "app.knowledge" or mod.startswith("app.knowledge."):
            del sys.modules[mod]
    return importlib.import_module("app.knowledge")


def test_env_override_redirects_shared_knowledge_file(tmp_path, monkeypatch):
    kb = _fresh_import(tmp_path)
    # add_entry should write into tmp_path, not into ~/.tudou_claw
    entry = kb.add_entry("probe title", "probe content", tags=["test"])
    assert entry and entry.get("id")
    # File exists under tmp_path
    written = tmp_path / "shared_knowledge.json"
    assert written.exists()
    loaded = json.loads(written.read_text(encoding="utf-8"))
    assert any(e.get("title") == "probe title" for e in loaded)
    # And the user's real home was NOT touched
    home_file = Path.home() / ".tudou_claw" / "shared_knowledge.json"
    if home_file.exists():
        home_loaded = json.loads(home_file.read_text(encoding="utf-8"))
        assert not any(e.get("title") == "probe title" for e in home_loaded), (
            "knowledge.py leaked test fixture into production ~/.tudou_claw!"
        )


def test_env_override_works_for_both_env_names(tmp_path):
    """TUDOU_CLAW_DATA_DIR is primary; TUDOU_CLAW_HOME is legacy fallback."""
    alt = tmp_path / "alt_home"
    alt.mkdir()
    os.environ.pop("TUDOU_CLAW_DATA_DIR", None)
    os.environ["TUDOU_CLAW_HOME"] = str(alt)
    for mod in list(sys.modules):
        if mod == "app.knowledge" or mod.startswith("app.knowledge."):
            del sys.modules[mod]
    kb = importlib.import_module("app.knowledge")
    kb.add_entry("via-home", "content", [])
    assert (alt / "shared_knowledge.json").exists()
    os.environ.pop("TUDOU_CLAW_HOME", None)


def test_env_override_reset_between_runs(tmp_path):
    """Two sequential fixture dirs must not bleed into each other."""
    a = tmp_path / "runA"
    b = tmp_path / "runB"
    a.mkdir(); b.mkdir()

    kb = _fresh_import(a)
    kb.add_entry("only-in-A", "", [])
    # Switch env + flush cache
    kb2 = _fresh_import(b)
    kb2.add_entry("only-in-B", "", [])

    a_titles = [e["title"] for e in json.loads(
        (a / "shared_knowledge.json").read_text(encoding="utf-8"))]
    b_titles = [e["title"] for e in json.loads(
        (b / "shared_knowledge.json").read_text(encoding="utf-8"))]
    assert "only-in-A" in a_titles
    assert "only-in-B" not in a_titles
    assert "only-in-B" in b_titles
    assert "only-in-A" not in b_titles
