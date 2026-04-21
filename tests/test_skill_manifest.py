"""Regression for the skill routing manifest loader.

Covers the Clowder-style "single-source-of-truth" manifest shape:
not_for / next / sop_step / requires_mcp.
"""
from __future__ import annotations

from pathlib import Path

from app.skills.manifest_loader import (
    SkillRoutingExtras,
    load_manifest,
    render_bootstrap_table,
)


def _write(tmp: Path, body: str) -> Path:
    p = tmp / "MANIFEST.yaml"
    p.write_text(body, encoding="utf-8")
    return p


def test_load_real_manifest_has_every_field(tmp_path):
    """The live app/skills/MANIFEST.yaml must parse cleanly with at
    least a few chain entries — otherwise the routing is broken."""
    manifest = load_manifest()
    assert manifest.schema_version >= 1
    # tdd is in the engineering chain; verify key wiring survived.
    tdd = manifest.extras_for("test-driven-development")
    assert "verification-before-completion" in tdd.next
    assert tdd.sop_step == 3


def test_load_missing_file_returns_empty(tmp_path):
    manifest = load_manifest(tmp_path / "nope.yaml")
    assert manifest.schema_version >= 1
    assert manifest.skills == {}


def test_load_malformed_file_returns_empty(tmp_path):
    p = _write(tmp_path, "not: [valid: yaml: at: all:")
    manifest = load_manifest(p)
    # Must not raise; gives an empty result so the system stays bootable.
    assert manifest.skills == {}


def test_load_skill_with_all_fields(tmp_path):
    p = _write(tmp_path, """
schemaVersion: 1
skills:
  demo:
    not_for:
      - "case A"
      - "case B"
    next:
      - "demo-2"
    sop_step: 5
    requires_mcp:
      - "email"
      - "slack"
""")
    manifest = load_manifest(p)
    demo = manifest.extras_for("demo")
    assert demo.not_for == ["case A", "case B"]
    assert demo.next == ["demo-2"]
    assert demo.sop_step == 5
    assert demo.requires_mcp == ["email", "slack"]


def test_unlisted_skill_returns_empty_extras(tmp_path):
    p = _write(tmp_path, "schemaVersion: 1\nskills: {}\n")
    manifest = load_manifest(p)
    unlisted = manifest.extras_for("anything")
    assert isinstance(unlisted, SkillRoutingExtras)
    assert unlisted.not_for == []
    assert unlisted.next == []
    assert unlisted.sop_step is None


def test_malformed_entry_is_skipped_not_fatal(tmp_path):
    p = _write(tmp_path, """
schemaVersion: 1
skills:
  bad_entry: "not a dict"
  good_entry:
    next: ["x"]
""")
    manifest = load_manifest(p)
    # Bad entry silently dropped; good entry loads.
    assert manifest.extras_for("bad_entry").next == []
    assert manifest.extras_for("good_entry").next == ["x"]


def test_sop_step_coercion_rejects_strings(tmp_path):
    p = _write(tmp_path, """
schemaVersion: 1
skills:
  demo:
    sop_step: "not a number"
""")
    manifest = load_manifest(p)
    # String sop_step falls back to None rather than blowing up.
    assert manifest.extras_for("demo").sop_step is None


# ── Bootstrap table ──────────────────────────────────────────────────

def test_render_bootstrap_table_has_every_skill(tmp_path):
    p = _write(tmp_path, """
schemaVersion: 1
skills:
  alpha:
    not_for: ["case X"]
    next: ["beta"]
  beta:
    not_for: []
    next: []
""")
    manifest = load_manifest(p)
    table = render_bootstrap_table(
        manifest,
        skill_names=["alpha", "beta"],
        descriptions={
            "alpha": "Do the alpha thing when needed",
            "beta": "Follow-up action",
        },
    )
    assert "`alpha`" in table
    assert "`beta`" in table
    assert "Do the alpha thing" in table
    assert "case X" in table
    assert "beta" in table  # in the next-column for alpha
    # Header row present
    assert "| Skill | Use when | Not for | Next |" in table


def test_render_bootstrap_handles_missing_description(tmp_path):
    manifest = load_manifest()
    # Skill with no description falls back to a nudge, doesn't crash.
    table = render_bootstrap_table(manifest, ["nonexistent-skill"])
    assert "(see SKILL.md)" in table


def test_render_bootstrap_table_empty_list(tmp_path):
    manifest = load_manifest()
    assert render_bootstrap_table(manifest, []) == ""


def test_render_bootstrap_pipes_are_escaped(tmp_path):
    manifest = load_manifest()
    table = render_bootstrap_table(
        manifest,
        ["fake"],
        descriptions={"fake": "a | b | c description"},
    )
    # Description pipes escaped so table doesn't split cells incorrectly.
    assert "a \\| b \\| c" in table
