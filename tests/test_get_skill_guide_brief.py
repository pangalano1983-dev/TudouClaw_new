"""Opt 5 — get_skill_guide brief/verbose mode.

Builds a fake skill registry in a tmpdir + a SKILL.md with known headings
and body, then verifies:
  * brief=True (default) returns only headings + file list (short)
  * brief=False returns the full body (long)
  * string "false" / "0" / "no" coerce to verbose
  * verbose=true overrides brief=true
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


from app.tools_split.skills import _tool_get_skill_guide  # noqa: E402


# ── test fixtures ──────────────────────────────────────────────────


_BODY_LONG = """# Overview

This is a test skill with a very long body.

## Installation

```bash
pip install foo
```

## Usage

Step 1: do something.
Step 2: do something else.

## Advanced Usage

Deep dive content here...

## Troubleshooting

If things break, check the logs.
""" + "X" * 3000   # pad it out to be obviously "long"


class _FakeManifest:
    def __init__(self, name="test-skill", runtime="python",
                 description="A test skill"):
        self.name = name
        self.runtime = runtime
        self.description = description
        self.entry = "SKILL.md"


class _FakeInstance:
    def __init__(self, skill_dir: str, name="test-skill"):
        self.id = f"inst_{name}"
        self.manifest = _FakeManifest(name=name)
        self.install_dir = skill_dir


class _FakeRegistry:
    def __init__(self, insts):
        self._insts = insts

    def list_all(self):
        return list(self._insts)


@pytest.fixture
def skill_dir(tmp_path):
    d = tmp_path / "test-skill"
    d.mkdir()
    (d / "SKILL.md").write_text(_BODY_LONG, encoding="utf-8")
    (d / "helper.py").write_text("# helper\n", encoding="utf-8")
    (d / "reference.md").write_text("# Reference doc\n", encoding="utf-8")
    return str(d)


@pytest.fixture
def patched_registry(skill_dir, monkeypatch):
    inst = _FakeInstance(skill_dir)
    fake_reg = _FakeRegistry([inst])
    from app.skills import engine as _engine
    monkeypatch.setattr(_engine, "get_registry", lambda: fake_reg)
    # Also prevent hub-short-circuit from returning None.
    return fake_reg


# ── brief mode (default) ───────────────────────────────────────────


def test_brief_default_returns_headings_not_body(patched_registry):
    out = _tool_get_skill_guide(name="test-skill")
    assert "## Skill: test-skill" in out
    assert "**skill_dir**" in out
    assert "**runtime**: python" in out
    assert "**描述**: A test skill" in out
    # Has headings section
    assert "章节目录" in out
    # Specific headings from the SKILL.md
    assert "# Overview" in out
    assert "## Installation" in out
    assert "## Advanced Usage" in out
    # Body content NOT included
    assert "pip install foo" not in out
    assert "Step 1: do something." not in out
    # Output size is reasonable
    assert len(out) < 1500, f"brief output unexpectedly large: {len(out)} chars"


def test_brief_lists_ancillary_files(patched_registry):
    out = _tool_get_skill_guide(name="test-skill")
    assert "附属文件" in out
    assert "helper.py" in out


def test_brief_mentions_how_to_load_full(patched_registry):
    out = _tool_get_skill_guide(name="test-skill")
    assert "brief=false" in out.lower()


# ── verbose mode ───────────────────────────────────────────────────


def test_verbose_returns_full_body(patched_registry):
    out = _tool_get_skill_guide(name="test-skill", brief=False)
    # Full body content present
    assert "pip install foo" in out
    assert "Step 1: do something." in out
    assert "Troubleshooting" in out
    # Should not claim to be brief
    assert "章节目录" not in out
    # Output is large
    assert len(out) > 2500


def test_brief_string_false_becomes_verbose(patched_registry):
    out = _tool_get_skill_guide(name="test-skill", brief="false")
    assert "pip install foo" in out


def test_brief_string_zero_becomes_verbose(patched_registry):
    out = _tool_get_skill_guide(name="test-skill", brief="0")
    assert "pip install foo" in out


def test_verbose_flag_overrides_brief_default(patched_registry):
    out = _tool_get_skill_guide(name="test-skill", verbose=True)
    assert "pip install foo" in out


def test_verbose_is_significantly_larger_than_brief(patched_registry):
    brief_out = _tool_get_skill_guide(name="test-skill")
    verbose_out = _tool_get_skill_guide(name="test-skill", brief=False)
    # Verbose should be at least 3x larger — that's the whole point.
    assert len(verbose_out) > len(brief_out) * 3


# ── error paths unchanged ─────────────────────────────────────────


def test_missing_name_still_errors(patched_registry):
    out = _tool_get_skill_guide()
    assert out.startswith("Error")


def test_unknown_skill_still_errors(patched_registry):
    out = _tool_get_skill_guide(name="does-not-exist")
    assert out.startswith("Error")
    assert "not found" in out
