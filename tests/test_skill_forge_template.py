"""Regression for the SKILL.md template — enforces 7 required sections.

Clowder-style template standard (Sprint 1.2 of the skill-quality uplift):
every auto-generated SKILL.md must have the 7 canonical sections so the
skill is navigable and the agent can find Common Mistakes / distinguishing
guidance without scanning prose.
"""
from __future__ import annotations

from app.experience_library import Experience
from app.skills._skill_forge import SkillForge


_REQUIRED_SECTIONS = (
    "## Core Knowledge",
    "## Workflow",
    "## Quick Reference",
    "## Common Mistakes",
    "## Distinguishing from Other Skills",
    "## Next Steps",
)

_REQUIRED_DESCRIPTION_MARKERS = (
    "Use when:",
    "Not for:",
    "Output:",
    "GOTCHA:",
)


def _make_exp(scene: str = "generate a PPTX report", role: str = "coder") -> Experience:
    # Minimal Experience that won't blow up the template builder.
    return Experience(
        exp_type="retrospective",
        source="test",
        scene=scene,
        core_knowledge="Use create_pptx for simple decks, advanced for charts.",
        action_rules=["always declare a theme"],
        taboo_rules=["do not invent layout.type"],
        priority="medium",
        tags=["pptx"],
        role=role,
    )


def test_template_contains_all_required_sections(tmp_path):
    # No LLM fn — forces the deterministic template path.
    forge = SkillForge(
        experience_data_dir=str(tmp_path / "exp"),
        output_dir=str(tmp_path / "out"),
        llm_call_fn=None,
    )
    md = forge._generate_skill_md_template(
        skill_name="pptx-maker",
        experiences=[_make_exp(), _make_exp("design a KPI slide")],
        scenes=["generate a PPTX report", "design a KPI slide"],
        knowledge=["use create_pptx_advanced with cards layout"],
    )
    for section in _REQUIRED_SECTIONS:
        assert section in md, f"template missing section: {section}"


def test_template_description_uses_five_element_format(tmp_path):
    forge = SkillForge(
        experience_data_dir=str(tmp_path / "exp"),
        output_dir=str(tmp_path / "out"),
        llm_call_fn=None,
    )
    md = forge._generate_skill_md_template(
        skill_name="demo",
        experiences=[_make_exp()],
        scenes=["demo scene"],
        knowledge=["demo knowledge"],
    )
    # Frontmatter description must carry every marker.
    for marker in _REQUIRED_DESCRIPTION_MARKERS:
        assert marker in md, f"description missing marker: {marker}"


def test_template_common_mistakes_table_present(tmp_path):
    """Common Mistakes is the single highest-value section — must never
    collapse to just a heading without a table scaffold."""
    forge = SkillForge(
        experience_data_dir=str(tmp_path / "exp"),
        output_dir=str(tmp_path / "out"),
        llm_call_fn=None,
    )
    md = forge._generate_skill_md_template(
        skill_name="demo",
        experiences=[_make_exp()],
        scenes=["demo scene"],
        knowledge=["demo knowledge"],
    )
    cm_start = md.find("## Common Mistakes")
    assert cm_start >= 0
    # Scaffold columns must be present between this heading and the next.
    next_section = md.find("\n## ", cm_start + 1)
    section_body = md[cm_start:next_section if next_section > 0 else len(md)]
    assert "Error" in section_body and "Consequence" in section_body and "Fix" in section_body
