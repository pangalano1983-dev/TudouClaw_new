"""Regression — /api/portal/agent/{id}/prompt-packs import_from_catalog.

Bug: the catalog entry's real prompt text lives in its `entries` list
(title + content per entry, may have many). Old code created a
PromptPack with content="" → agent 绑定 之后没有任何提示注入，
用户看到 "✓ 已导入" 其实什么也没联动起来。

Fix: assemble entries into a Markdown body, merge tags, then store.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ── helpers under direct test ───────────────────────────────


def test_assemble_empty_entries_returns_empty():
    from app.api.routers.agents import _assemble_catalog_skill_content
    assert _assemble_catalog_skill_content({"id": "x"}) == ""
    assert _assemble_catalog_skill_content({"id": "x", "entries": []}) == ""
    assert _assemble_catalog_skill_content({"id": "x", "entries": "not a list"}) == ""


def test_assemble_joins_entries_with_headings():
    from app.api.routers.agents import _assemble_catalog_skill_content
    entry = {
        "id": "skill_a", "name": "Skill A",
        "description": "A skill.", "category": "academic",
        "entries": [
            {"title": "Identity", "content": "You are an anthropologist.",
             "priority": 9},
            {"title": "Mission", "content": "Analyze cultures.",
             "priority": 5},
        ],
    }
    body = _assemble_catalog_skill_content(entry)
    assert "You are an anthropologist." in body
    assert "Analyze cultures." in body
    assert "## Identity" in body
    assert "## Mission" in body
    # Frontmatter block included.
    assert "name: Skill A" in body


def test_assemble_sorts_by_priority_high_first():
    from app.api.routers.agents import _assemble_catalog_skill_content
    entry = {
        "id": "x",
        "entries": [
            {"title": "Low", "content": "low body", "priority": 1},
            {"title": "High", "content": "high body", "priority": 9},
            {"title": "Mid", "content": "mid body", "priority": 5},
        ],
    }
    body = _assemble_catalog_skill_content(entry)
    # High should appear BEFORE Low.
    assert body.index("high body") < body.index("low body")
    assert body.index("high body") < body.index("mid body")


def test_assemble_handles_content_starting_with_heading():
    """Don't stack two ## levels."""
    from app.api.routers.agents import _assemble_catalog_skill_content
    entry = {
        "id": "x",
        "entries": [
            {"title": "Identity",
             "content": "# Heading in Body\n\nThe body already has a heading."},
        ],
    }
    body = _assemble_catalog_skill_content(entry)
    # Body preserved as-is; no synthesized "## Identity" (since body starts with #)
    assert "# Heading in Body" in body
    assert body.count("## Identity") == 0


def test_assemble_skips_entries_with_empty_content():
    from app.api.routers.agents import _assemble_catalog_skill_content
    entry = {
        "id": "x",
        "entries": [
            {"title": "Empty", "content": "", "priority": 9},
            {"title": "Real", "content": "Real body here.", "priority": 5},
        ],
    }
    body = _assemble_catalog_skill_content(entry)
    assert "Real body here." in body
    assert "Empty" not in body


def test_merge_tags_dedups_across_entries():
    from app.api.routers.agents import _merge_catalog_skill_tags
    entry = {
        "id": "x", "tags": ["a", "b"],
        "entries": [
            {"tags": ["b", "c"]},
            {"tags": ["c", "d"]},
        ],
    }
    tags = _merge_catalog_skill_tags(entry)
    assert tags == ["a", "b", "c", "d"]


def test_merge_tags_strips_whitespace():
    from app.api.routers.agents import _merge_catalog_skill_tags
    entry = {"id": "x", "tags": [" a ", "", None, " b  "]}
    tags = _merge_catalog_skill_tags(entry)
    assert tags == ["a", "b"]


# ── import_from_catalog end-to-end ──────────────────────────


@pytest.fixture
def client_with_fake_catalog(tmp_path, monkeypatch):
    """Point the catalog file at a tmp file with a known entry so we
    can assert the imported PromptPack ends up with real content."""
    # Write a minimal catalog.
    catalog_dir = tmp_path / "data"
    catalog_dir.mkdir()
    catalog_path = catalog_dir / "community_skills.json"
    catalog = {
        "version": 1,
        "categories": ["academic"],
        "skills": [
            {
                "id": "test_skill_1",
                "name": "测试技能",
                "description": "A test skill entry.",
                "icon": "🧪",
                "category": "academic",
                "source": "test",
                "entries": [
                    {
                        "id": "test_skill_1_id",
                        "title": "核心身份",
                        "content": "你是一个文化研究者。",
                        "priority": 9,
                        "tags": ["academic", "test"],
                    },
                    {
                        "id": "test_skill_1_mission",
                        "title": "核心使命",
                        "content": "你的任务是深度分析文化。",
                        "priority": 7,
                        "tags": ["test"],
                    },
                ],
            },
        ],
    }
    with open(catalog_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False)

    # Patch catalog path resolution. The FastAPI code builds the path as
    # `parent.parent.parent / "data" / "community_skills.json"` relative
    # to `app/api/routers/agents.py`. We need the check
    # `catalog_path = _Path(__file__).resolve().parent.parent.parent
    #  / "data" / "community_skills.json"` to land on our tmp file.
    # Easiest: monkeypatch `open` is fragile; use monkeypatch on
    # `_Path` to return our path.
    import app.api.routers.agents as ag_mod
    _orig_open = open

    def _patched_open(p, *args, **kwargs):
        p_str = str(p)
        if p_str.endswith("community_skills.json"):
            return _orig_open(str(catalog_path), *args, **kwargs)
        return _orig_open(p, *args, **kwargs)

    monkeypatch.setattr("builtins.open", _patched_open)

    # Minimal hub + agent.
    class _FakeAgent:
        def __init__(self):
            self.id = "a-alice"
            self.name = "Alice"
            self.role = "general"
            self.bound_prompt_packs: list[str] = []
            self.working_dir = ""

    class _FakeHub:
        def __init__(self):
            self.agents = {"a-alice": _FakeAgent()}

        def get_agent(self, aid):
            return self.agents.get(aid)

        def _save_agents(self):
            pass

    hub = _FakeHub()

    from app.api.deps.auth import get_current_user, CurrentUser
    from app.api.deps.hub import get_hub as _get_hub

    async def _fake_user():
        return CurrentUser(user_id="u", role="superAdmin")

    # Fresh PromptPack registry — reset singleton.
    import app.core.prompt_enhancer as pe
    monkeypatch.setattr(pe, "_registry_singleton", None, raising=False)
    # Force a tmp persist path.
    monkeypatch.setenv("TUDOU_CLAW_DATA_DIR", str(tmp_path))

    app = FastAPI()
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[_get_hub] = lambda: hub
    app.include_router(ag_mod.router)

    with TestClient(app) as tc:
        tc.hub = hub
        yield tc


def test_import_from_catalog_populates_content(client_with_fake_catalog):
    tc = client_with_fake_catalog
    r = tc.post(
        "/api/portal/agent/a-alice/prompt-packs",
        json={"action": "import_from_catalog",
              "skill_ids": ["test_skill_1"]},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["imported"] == 1
    assert "test_skill_1" in d["bound_prompt_packs"]

    # Fetch the actual PromptPack from the registry and check content.
    from app.core.prompt_enhancer import get_prompt_pack_registry
    reg = get_prompt_pack_registry()
    pack = reg.store.get("test_skill_1")
    assert pack is not None, "PromptPack should have been stored"
    # THE CRITICAL ASSERTION — this was the bug.
    assert pack.content, "content must be populated, not empty"
    assert "你是一个文化研究者" in pack.content
    assert "你的任务是深度分析文化" in pack.content
    # Name, description, category from top-level.
    assert pack.name == "测试技能"
    assert pack.category == "academic"
    # Merged tags (top-level + entries).
    assert "academic" in pack.tags
    assert "test" in pack.tags


def test_import_from_catalog_unknown_skill_skipped(client_with_fake_catalog):
    tc = client_with_fake_catalog
    r = tc.post(
        "/api/portal/agent/a-alice/prompt-packs",
        json={"action": "import_from_catalog",
              "skill_ids": ["does_not_exist"]},
    )
    assert r.status_code == 200
    d = r.json()
    assert d["imported"] == 0


def test_import_from_catalog_preserves_existing_binds(client_with_fake_catalog):
    tc = client_with_fake_catalog
    tc.hub.agents["a-alice"].bound_prompt_packs.append("existing_skill")
    tc.post(
        "/api/portal/agent/a-alice/prompt-packs",
        json={"action": "import_from_catalog",
              "skill_ids": ["test_skill_1"]},
    )
    bound = tc.hub.agents["a-alice"].bound_prompt_packs
    assert "existing_skill" in bound
    assert "test_skill_1" in bound


def test_import_from_catalog_idempotent_binding(client_with_fake_catalog):
    """Same skill imported twice doesn't duplicate the binding."""
    tc = client_with_fake_catalog
    for _ in range(2):
        tc.post(
            "/api/portal/agent/a-alice/prompt-packs",
            json={"action": "import_from_catalog",
                  "skill_ids": ["test_skill_1"]},
        )
    bound = tc.hub.agents["a-alice"].bound_prompt_packs
    assert bound.count("test_skill_1") == 1
