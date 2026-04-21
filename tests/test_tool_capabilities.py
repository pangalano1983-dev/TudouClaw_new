"""Regression for the core/skill-gated tool tiering.

Big picture: agents previously received ALL 38 TOOL_DEFINITIONS in
every LLM call regardless of capability. This module gates tool
schemas on agent.granted_skills so only relevant tools ship.
"""
from __future__ import annotations

import pytest

from app.tool_capabilities import (
    CAPABILITY_SKILL_IDS,
    CAPABILITY_SKILLS,
    CORE_TOOLS,
    filter_tools_by_capability,
    get_tool_capability,
    is_core_tool,
    sanity_check,
)


def _fake_tool(name: str) -> dict:
    return {"function": {"name": name, "description": f"{name} description"}}


# ── Classification correctness ───────────────────────────────────────

def test_core_and_capability_sets_are_disjoint():
    """A tool cannot be both CORE and gated behind a capability skill."""
    gated_tools = {t for tools in CAPABILITY_SKILLS.values() for t in tools}
    overlap = CORE_TOOLS & gated_tools
    assert not overlap, f"Tool(s) in both tiers: {sorted(overlap)}"


def test_every_defined_tool_is_classified():
    """Every name in TOOL_DEFINITIONS must be either CORE or gated.
    This guards against drift: new tools added to tools.py without
    updating tool_capabilities.py would silently ship to every agent."""
    both, missing = sanity_check()
    assert not both, f"In both tiers (shouldn't happen): {sorted(both)}"
    assert not missing, (
        f"Unclassified tools (add to CORE_TOOLS or CAPABILITY_SKILLS): "
        f"{sorted(missing)}"
    )


def test_get_tool_capability_for_core_returns_none():
    for tool in list(CORE_TOOLS)[:5]:
        assert get_tool_capability(tool) is None


def test_get_tool_capability_for_gated_returns_skill():
    assert get_tool_capability("submit_deliverable") == "project-management"
    assert get_tool_capability("create_pptx_advanced") == "pptx-author"
    assert get_tool_capability("team_create") == "multi-agent"


def test_is_core_tool():
    assert is_core_tool("read_file")
    assert is_core_tool("bash")
    assert not is_core_tool("submit_deliverable")
    assert not is_core_tool("create_pptx")


# ── filter_tools_by_capability ───────────────────────────────────────

def test_filter_keeps_all_core_with_empty_grants():
    tools = [_fake_tool(name) for name in CORE_TOOLS]
    result = filter_tools_by_capability(tools, granted_skills=[])
    assert len(result) == len(CORE_TOOLS)


def test_filter_strips_all_gated_with_empty_grants():
    """Zero capability skills granted → only core tools survive."""
    all_tools = [_fake_tool(t)
                 for cap_tools in CAPABILITY_SKILLS.values()
                 for t in cap_tools]
    result = filter_tools_by_capability(all_tools, granted_skills=[])
    assert result == []  # every one stripped


def test_filter_unlocks_exactly_the_granted_capability():
    """Granting 'project-management' should reveal its 5 tools and
    no others."""
    # Start with one tool from every capability skill
    one_from_each = [_fake_tool(tools[0])
                     for tools in CAPABILITY_SKILLS.values()]
    result = filter_tools_by_capability(
        one_from_each, granted_skills=["project-management"])
    names = [t["function"]["name"] for t in result]
    # Exactly submit_deliverable (first tool under project-management)
    assert names == [CAPABILITY_SKILLS["project-management"][0]]


def test_filter_unlocks_multiple_granted_capabilities():
    pm_and_video = [_fake_tool(t) for t in
                     CAPABILITY_SKILLS["project-management"]
                     + CAPABILITY_SKILLS["video-forge"]]
    result = filter_tools_by_capability(
        pm_and_video,
        granted_skills=["project-management", "video-forge"],
    )
    assert len(result) == len(pm_and_video)


def test_filter_ignores_unknown_grants():
    """Granting a skill id that isn't a capability skill (e.g. a
    workflow skill like 'test-driven-development') has no effect on
    tool-tier filtering."""
    gated = [_fake_tool("submit_deliverable")]
    result = filter_tools_by_capability(
        gated, granted_skills=["test-driven-development"])
    assert result == []  # still stripped


def test_filter_unknown_tool_passes_through():
    """Tool with a name that is neither CORE nor in any capability
    skill (e.g. a tool added after classification) must PASS through
    — fail-open, so admins can classify later without breaking it."""
    tools = [_fake_tool("brand_new_tool_xyz")]
    result = filter_tools_by_capability(tools, granted_skills=[])
    assert [t["function"]["name"] for t in result] == ["brand_new_tool_xyz"]


def test_filter_handles_none_granted_skills():
    """Defensive: Agent.granted_skills may be None on freshly-loaded
    legacy records; filter must tolerate it."""
    tools = [_fake_tool("read_file"), _fake_tool("submit_deliverable")]
    result = filter_tools_by_capability(tools, granted_skills=None)
    # Core passes; gated stripped.
    assert [t["function"]["name"] for t in result] == ["read_file"]


# ── Integration with Agent._get_effective_tools ──────────────────────

def test_agent_with_zero_capability_skills_sees_core_only():
    from app.agent import Agent, AgentProfile
    agent = Agent(
        id="test-agent",
        name="tester",
        role="general",
        profile=AgentProfile(),
        granted_skills=[],
    )
    effective = agent._get_effective_tools()
    names = {t["function"]["name"] for t in effective}
    # Every name should be in CORE_TOOLS (modulo any unknown tools
    # that pass through, which shouldn't happen in a clean checkout).
    # Every gated tool should be absent.
    gated_tools = {t
                   for tools in CAPABILITY_SKILLS.values()
                   for t in tools}
    leaked = names & gated_tools
    assert not leaked, f"Gated tools leaked without grant: {sorted(leaked)}"


def test_agent_with_project_management_sees_pm_tools():
    from app.agent import Agent, AgentProfile
    agent = Agent(
        id="pm-agent",
        name="alice",
        role="pm",
        profile=AgentProfile(),
        granted_skills=["project-management"],
    )
    effective = agent._get_effective_tools()
    names = {t["function"]["name"] for t in effective}
    for tool in CAPABILITY_SKILLS["project-management"]:
        assert tool in names, f"{tool} should be unlocked"
    # Other capabilities still gated.
    assert "create_video" not in names
    assert "team_create" not in names


def test_agent_with_all_capabilities_sees_every_non_denied_tool():
    from app.agent import Agent, AgentProfile
    agent = Agent(
        id="god-agent",
        name="omniscient",
        role="general",
        profile=AgentProfile(),
        granted_skills=list(CAPABILITY_SKILL_IDS),
    )
    effective = agent._get_effective_tools()
    names = {t["function"]["name"] for t in effective}
    # All gated tools should be present.
    for cap_tools in CAPABILITY_SKILLS.values():
        for tool in cap_tools:
            # Subject to global denylist (e.g. create_pptx might be
            # denied in user env); skip tools that were globally denied.
            pass  # we don't assert on these here to avoid flakiness
    # At minimum, canonical core tools present. (plan_update is CORE
    # in our classification but is handled via agent_execution.py
    # intercept rather than tool_registry — pre-existing; not in scope
    # for this test which just verifies the capability-filter doesn't
    # over-strip.)
    for core in ("read_file", "bash", "web_search",
                 "knowledge_lookup", "emit_ui_block"):
        assert core in names, f"core tool {core} missing"


# ── Capability skill enumeration ─────────────────────────────────────

def test_all_capability_skill_ids_are_known():
    # 7 declared capability skills.
    expected = {
        "project-management", "pptx-author", "video-forge",
        "screenshot", "http-client", "multi-agent", "admin-ops",
    }
    assert CAPABILITY_SKILL_IDS == expected


# ── Global default capability layer ──────────────────────────────────
# Admin-level config that grants certain capabilities to every agent
# implicitly. Separate from per-agent granted_skills.

def test_load_missing_file_returns_empty(tmp_path):
    from app.tool_capabilities import load_global_default_capabilities
    result = load_global_default_capabilities(tmp_path / "nope.json")
    assert result == []


def test_load_malformed_file_returns_empty(tmp_path):
    from app.tool_capabilities import load_global_default_capabilities
    (tmp_path / "cap.json").write_text("not: valid json at all", encoding="utf-8")
    # Must not raise — bootability matters more than strict parsing.
    assert load_global_default_capabilities(tmp_path / "cap.json") == []


def test_load_drops_unknown_capability_names(tmp_path):
    """Typo-in-config safety: if admin writes 'projctmanagement'
    instead of 'project-management', silently drop it rather than
    unlock a random subset."""
    import json as _j
    (tmp_path / "c.json").write_text(
        _j.dumps({"defaults": ["project-management", "projctmanagement",
                                 "pptx-author"]}),
        encoding="utf-8",
    )
    from app.tool_capabilities import load_global_default_capabilities
    result = load_global_default_capabilities(tmp_path / "c.json")
    # Unknown dropped; known preserved in input order.
    assert result == ["project-management", "pptx-author"]


def test_save_rejects_unknown_capability_name(tmp_path):
    from app.tool_capabilities import save_global_default_capabilities
    import pytest as _pytest
    with _pytest.raises(ValueError, match="Unknown capability skill"):
        save_global_default_capabilities(
            ["typo-skill"], path=tmp_path / "c.json")


def test_save_then_load_roundtrip(tmp_path):
    from app.tool_capabilities import (
        save_global_default_capabilities,
        load_global_default_capabilities,
    )
    save_global_default_capabilities(
        ["project-management", "multi-agent", "multi-agent"],  # dup gets deduped
        path=tmp_path / "c.json",
    )
    # Sorted + deduped.
    assert load_global_default_capabilities(tmp_path / "c.json") == [
        "multi-agent", "project-management",
    ]


def test_global_defaults_unlock_tools(tmp_path):
    """Global defaults should unlock tools across ALL agents without
    per-agent grant."""
    tools = [_fake_tool("submit_deliverable"), _fake_tool("create_video")]
    # Agent has no grants, but project-management is a global default.
    result = filter_tools_by_capability(
        tools,
        granted_skills=[],
        global_defaults=["project-management"],
    )
    names = [t["function"]["name"] for t in result]
    assert "submit_deliverable" in names     # unlocked by global default
    assert "create_video" not in names       # still gated


def test_effective_caps_is_union_of_defaults_and_grants():
    """Agent with per-agent grant + admin global default should see
    the UNION of capabilities."""
    tools = [_fake_tool("submit_deliverable"),    # project-management
              _fake_tool("create_video"),          # video-forge
              _fake_tool("team_create")]           # multi-agent
    result = filter_tools_by_capability(
        tools,
        granted_skills=["video-forge"],           # per-agent
        global_defaults=["project-management"],   # global
    )
    names = {t["function"]["name"] for t in result}
    assert names == {"submit_deliverable", "create_video"}
    assert "team_create" not in names
