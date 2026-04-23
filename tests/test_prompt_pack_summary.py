"""Opt 2 — PromptPack.summary field + summary-first injection.

Verifies:
  * PromptPack roundtrips the new `summary` field via to_dict/from_dict
  * _derive_summary extracts headings + first paragraph
  * build_context_injection() default (summary mode) is ~10x smaller
    than full-body mode for the same skills
  * Pre-written summary is preferred over auto-derived
  * full_body=True restores legacy behavior
"""
from __future__ import annotations

import os
import sys
import tempfile

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


from app.skills.prompt_enhancer import (  # noqa: E402
    PromptPack, PromptPackStore, PromptPackRegistry,
)


_BIG_BODY = """---
name: test-skill
description: A test skill
---
# Overview

This skill helps you do X.

## Installation

```bash
pip install foo
```

## Usage

Step 1: open terminal.
Step 2: run the command.

## Advanced Usage

Deep dive content here...

""" + "X" * 3000


def _make_pack(skill_id="s1", name="test-skill",
               description="A test skill",
               summary: str = "",
               content: str = _BIG_BODY) -> PromptPack:
    return PromptPack(
        skill_id=skill_id,
        name=name,
        description=description,
        content=content,
        summary=summary,
        category="tool_guide",
    )


@pytest.fixture
def registry(tmp_path):
    store = PromptPackStore(persist_path=str(tmp_path / "packs.json"))
    reg = PromptPackRegistry(store=store)
    return reg


def _put(store: PromptPackStore, p: PromptPack) -> None:
    """Tests insert records directly into the internal dict since the
    production put-path is `scan()`ed from disk."""
    store._skills[p.skill_id] = p


# ── roundtrip ───────────────────────────────────────────────────────


def test_summary_field_roundtrips():
    p = _make_pack(summary="pre-written short summary")
    d = p.to_dict()
    assert d["summary"] == "pre-written short summary"
    p2 = PromptPack.from_dict(d)
    assert p2.summary == "pre-written short summary"


def test_summary_defaults_to_empty():
    p = _make_pack()
    assert p.summary == ""
    p2 = PromptPack.from_dict(p.to_dict())
    assert p2.summary == ""


# ── _derive_summary ────────────────────────────────────────────────


def test_derive_summary_extracts_headings_and_para():
    out = PromptPackRegistry._derive_summary(_BIG_BODY)
    assert "Sections:" in out
    assert "Overview" in out
    assert "Installation" in out
    assert "Usage" in out
    assert "Advanced Usage" in out
    # First paragraph after the initial heading.
    assert "This skill helps you do X." in out
    assert len(out) <= 500


def test_derive_summary_empty_content_returns_empty():
    assert PromptPackRegistry._derive_summary("") == ""
    assert PromptPackRegistry._derive_summary(None) == ""


def test_derive_summary_handles_no_headings():
    body = "Just plain text with no markdown structure."
    out = PromptPackRegistry._derive_summary(body)
    # Empty because we look for content AFTER a heading, but headings
    # are the anchor — plain text falls through to "no sections".
    assert "Sections:" not in out


def test_derive_summary_caps_at_max_chars():
    long_para = "# Head\n\n" + ("word " * 500)
    out = PromptPackRegistry._derive_summary(long_para, max_chars=200)
    assert len(out) <= 201   # +1 for ellipsis


# ── build_context_injection — summary mode (default) ─────────────


def test_summary_mode_is_much_smaller_than_full(registry):
    # Register a pack with big content, no pre-written summary.
    p = _make_pack()
    _put(registry.store, p)
    summary_out = registry.build_context_injection([p.skill_id])
    full_out = registry.build_context_injection([p.skill_id],
                                                  full_body=True,
                                                  max_chars=20000)
    # Summary mode substantially smaller.
    assert len(summary_out) < 1500
    assert len(full_out) > 2500
    assert len(full_out) > len(summary_out) * 2


def test_summary_mode_includes_sections_and_description(registry):
    p = _make_pack()
    _put(registry.store, p)
    out = registry.build_context_injection([p.skill_id])
    assert "Skills" in out
    assert p.name in out
    assert p.description in out
    # Sections list from the derived summary.
    assert "Sections:" in out
    assert "Installation" in out
    # Full-body content must NOT appear.
    assert "pip install foo" not in out
    assert "Step 1: open terminal." not in out


def test_pre_written_summary_is_preferred(registry):
    p = _make_pack(summary="TEST-SUMMARY-PREFERRED")
    _put(registry.store, p)
    out = registry.build_context_injection([p.skill_id])
    assert "TEST-SUMMARY-PREFERRED" in out
    # Auto-derived "Sections:" should NOT appear when pre-written summary exists.
    assert "Sections:" not in out


def test_full_body_mode_restores_legacy(registry):
    p = _make_pack()
    _put(registry.store, p)
    out = registry.build_context_injection([p.skill_id],
                                             full_body=True,
                                             max_chars=20000)
    assert "pip install foo" in out
    assert "Step 1: open terminal." in out


def test_summary_mode_indicator_in_heading(registry):
    p = _make_pack()
    _put(registry.store, p)
    out = registry.build_context_injection([p.skill_id])
    assert "summary mode" in out.lower()


def test_full_body_mode_no_summary_indicator(registry):
    p = _make_pack()
    _put(registry.store, p)
    out = registry.build_context_injection([p.skill_id], full_body=True)
    assert "summary mode" not in out.lower()


def test_selection_counter_still_increments(registry):
    p = _make_pack()
    _put(registry.store, p)
    assert p.total_selections == 0
    registry.build_context_injection([p.skill_id])
    updated = registry.store.get(p.skill_id)
    assert updated.total_selections == 1


def test_empty_skill_ids_returns_empty(registry):
    assert registry.build_context_injection([]) == ""


def test_unknown_skill_ids_skipped(registry):
    p = _make_pack()
    _put(registry.store, p)
    out = registry.build_context_injection([p.skill_id, "nonexistent"])
    assert p.name in out
    # Didn't crash; unknown id silently ignored.


def test_max_chars_respected(registry):
    p = _make_pack(summary="Q" * 10000)
    _put(registry.store, p)
    out = registry.build_context_injection([p.skill_id], max_chars=500)
    assert len(out) <= 600     # tight cap, +small header overhead


# ── multi-skill injection size ────────────────────────────────────


def test_three_skills_summary_mode_stays_compact(registry):
    for i in range(3):
        p = _make_pack(skill_id=f"s{i}", name=f"skill-{i}")
        _put(registry.store, p)
    out = registry.build_context_injection([f"s{i}" for i in range(3)])
    # Default max_chars=5000 plenty for 3 summaries.
    assert len(out) < 5000
    # All 3 skills mentioned.
    for i in range(3):
        assert f"skill-{i}" in out
