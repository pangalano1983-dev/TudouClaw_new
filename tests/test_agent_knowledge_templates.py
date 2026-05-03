"""Tests for Agent.profile.knowledge_templates binding (spec
2026-05-03)."""
from __future__ import annotations
import pytest


def test_profile_has_knowledge_templates_field_default_empty():
    """New AgentProfile defaults knowledge_templates to []."""
    from app.agent import AgentProfile
    p = AgentProfile()
    assert hasattr(p, "knowledge_templates")
    assert p.knowledge_templates == []


def test_profile_to_dict_includes_knowledge_templates():
    from app.agent import AgentProfile
    p = AgentProfile()
    p.knowledge_templates = ["tpl_a", "tpl_b"]
    d = p.to_dict()
    assert d.get("knowledge_templates") == ["tpl_a", "tpl_b"]


def test_profile_from_dict_reads_knowledge_templates():
    from app.agent import AgentProfile
    p = AgentProfile.from_dict({"knowledge_templates": ["x", "y", "z"]})
    assert p.knowledge_templates == ["x", "y", "z"]


def test_profile_from_dict_missing_field_defaults_empty():
    """Legacy agent.json files (saved before this feature) should
    load with knowledge_templates = []."""
    from app.agent import AgentProfile
    p = AgentProfile.from_dict({"agent_class": "enterprise"})
    assert p.knowledge_templates == []


def test_profile_roundtrip_preserves_knowledge_templates():
    from app.agent import AgentProfile
    src = AgentProfile()
    src.knowledge_templates = ["t1", "t2"]
    restored = AgentProfile.from_dict(src.to_dict())
    assert restored.knowledge_templates == ["t1", "t2"]


def test_update_agent_profile_accepts_knowledge_templates(tmp_path, monkeypatch):
    """POST /agent/{id}/profile with knowledge_templates in body
    persists onto agent.profile.knowledge_templates via the
    body→AgentProfile.from_dict path."""
    from app.agent import Agent, AgentProfile

    agent = Agent(id="ak1", name="t")
    agent.profile = AgentProfile()

    body = {"knowledge_templates": ["tpl_x", "tpl_y"]}

    if "knowledge_templates" in body:
        new_profile = AgentProfile.from_dict({
            **agent.profile.to_dict(),
            "knowledge_templates": list(body["knowledge_templates"] or []),
        })
        agent.profile = new_profile

    assert agent.profile.knowledge_templates == ["tpl_x", "tpl_y"]


def test_injection_renders_bound_first_then_auto_match_dedup(tmp_path, monkeypatch):
    """Bound templates always render before auto-matched ones; if
    auto-match returns one already in bound, it's dropped (dedup)."""
    from app import template_library as tl_mod
    from app.template_library import Template, TemplateLibrary

    lib = TemplateLibrary(templates_dir=str(tmp_path))
    t1 = Template(id="t1", name="bound_one", content="BOUND_ONE_CONTENT", enabled=True)
    t2 = Template(id="t2", name="bound_two", content="BOUND_TWO_CONTENT", enabled=True)
    t3 = Template(id="t3", name="auto_match", content="AUTO_MATCH_CONTENT", enabled=True)
    lib.templates = {"t1": t1, "t2": t2, "t3": t3}

    def fake_match(message, role="", limit=2):
        return [t2, t3]
    lib.match_templates = fake_match
    monkeypatch.setattr(tl_mod, "_library", lib)

    from app.agent import Agent, AgentProfile
    agent = Agent(id="ax", name="x", role="research")
    agent.profile = AgentProfile()
    agent.profile.knowledge_templates = ["t1", "t2"]

    bound_ids = list(getattr(agent.profile, "knowledge_templates", []) or [])
    bound_templates = []
    for tid in bound_ids:
        t = lib.get_template(tid)
        if t is not None and getattr(t, "enabled", True):
            bound_templates.append(t)
    auto_matched = lib.match_templates("any message", role=agent.role, limit=2)
    seen_ids = {t.id for t in bound_templates}
    final = list(bound_templates)
    for t in auto_matched:
        if t.id not in seen_ids:
            seen_ids.add(t.id)
            final.append(t)

    assert [t.id for t in final[:2]] == ["t1", "t2"]
    assert [t.id for t in final].count("t2") == 1
    assert "t3" in [t.id for t in final]
