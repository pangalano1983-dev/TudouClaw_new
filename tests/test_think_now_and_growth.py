"""Think button + Growth stats — merged replacement for the old
Active Thinking module.

Before:
  * active_thinking.py (621 lines) had a 7-step self-reflection loop
    triggered by a never-running scheduler hook, writing its output to
    an ActiveThinking.md file nobody read.
  * Think button opened a panel to enable / configure that loop.
  * Three modules (thinking, experience library, agent_growth) each
    owned a separate concept of "self improvement", none of which
    actually fed back into agent behavior.

After:
  * active_thinking.py deleted; field + scheduler hook + 4 API
    endpoints + panel UI removed.
  * Think button → POST /think-now: one-shot LLM call that summarizes
    the recent N turns, extracts any reusable ``{scene, knowledge,
    rule_do, rule_dont}`` blocks, persists them via the existing
    experience library, and emits an assistant-kind event so the
    summary renders as a chat bubble.
  * Growth panel consumes a new GET /growth-stats endpoint that
    aggregates COUNTERS over existing modules (experience / L3 memory /
    skills / domain KBs / shared-knowledge contributions / last
    self-summary). Zero new computation.

These tests lock the contract.
"""
from __future__ import annotations

import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ── active_thinking module is gone ────────────────────────────────


def test_active_thinking_module_deleted():
    """The entire active_thinking module must be gone, not just
    neutered. Anyone still importing it should get ImportError."""
    with pytest.raises(ImportError):
        import app.active_thinking  # noqa: F401


def test_no_active_thinking_field_on_agent():
    """Agent dataclass must no longer carry the active_thinking
    placeholder — otherwise hub auto-save round-trips a None."""
    from app.agent import Agent
    # dataclass.fields — no entry with name "active_thinking"
    from dataclasses import fields
    names = {f.name for f in fields(Agent)}
    assert "active_thinking" not in names


def test_no_thinking_endpoints_in_router():
    """The 4 thinking endpoints (enable/disable/history/GET) must be
    gone; only the new /think-now POST should exist."""
    from app.api.routers import agents as ar
    with open(ar.__file__) as f:
        src = f.read()
    # New endpoint present
    assert 'think-now' in src
    # Old endpoint prefixes gone
    assert '"/agent/{agent_id}/thinking/enable"' not in src
    assert '"/agent/{agent_id}/thinking/disable"' not in src
    assert '"/agent/{agent_id}/thinking/history"' not in src


def test_scheduler_hooks_deleted():
    """_check_active_thinking + _run_agent_thinking were orphan
    functions (no caller). They must be removed so future code doesn't
    wire them back by accident."""
    from app import scheduler as sch
    with open(sch.__file__) as f:
        src = f.read()
    assert "_check_active_thinking" not in src
    assert "_run_agent_thinking" not in src


# ── legacy payload compatibility ──────────────────────────────────


def test_agent_from_persist_dict_silently_drops_legacy_active_thinking():
    """Old agents.json files may still contain an "active_thinking"
    key. Agent.from_persist_dict must accept them without crashing
    and without creating a phantom attribute."""
    from app.agent import Agent
    d = {
        "id": "t1", "name": "test", "role": "general",
        "active_thinking": {"enabled": True, "config": {"foo": "bar"}},
    }
    agent = Agent.from_persist_dict(d)
    assert agent.id == "t1"
    # The legacy key is accepted and dropped on the floor — no field
    # on the Agent dataclass, so no attribute at all.
    from dataclasses import fields
    assert "active_thinking" not in {f.name for f in fields(Agent)}


# ── think_now behavior ────────────────────────────────────────────


def _make_agent_stub(messages, role="general"):
    """Build a harness bound to the real Agent.think_now."""
    from app.agent import Agent
    h = SimpleNamespace()
    h.id = "a1"
    h.name = "test"
    h.role = role
    h.messages = list(messages)
    h.events = []
    h.self_improvement = None
    h.provider = "local"
    h.model = "x"
    h.think_now = Agent.think_now.__get__(h)
    # _log just appends to events
    h._log = lambda kind, data: h.events.append(
        SimpleNamespace(kind=kind, data=data, ts=1700000000))
    h._resolve_effective_provider_model = lambda: ("local", "x")
    return h


def test_think_now_empty_conversation_returns_error():
    agent = _make_agent_stub([])
    result = agent.think_now()
    assert result["ok"] is False
    assert result["error"] == "no_conversation_yet"


def test_think_now_summarizes_and_emits_assistant_bubble(monkeypatch):
    agent = _make_agent_stub([
        {"role": "user", "content": "写一个快速排序"},
        {"role": "assistant", "content": "用递归分治实现了 quicksort"},
        {"role": "user", "content": "跑一下测试"},
        {"role": "assistant", "content": "测试全过，但 pivot 选择可以优化"},
    ])
    fake_llm_output = (
        "我刚才在做什么：帮助用户实现并测试了快速排序。\n"
        "关键问题：pivot 选择可以优化。\n"
        "有用的规则/教训：避免用固定 pivot，改用 median-of-three。\n"
        "下一步：应用 median-of-three 优化。\n"
    )
    with patch("app.llm.chat_no_stream",
               return_value={"content": fake_llm_output}):
        result = agent.think_now(turns_window=15)
    assert result["ok"] is True
    assert "快速排序" in result["summary"] or "pivot" in result["summary"]
    assert result["turns_analyzed"] == 4
    # Assistant bubble event emitted.
    msgs = [ev for ev in agent.events
            if ev.kind == "message"
            and ev.data.get("source") == "think_now"]
    assert len(msgs) == 1
    assert "【自我总结】" in msgs[0].data["content"]


def test_think_now_persists_experience_blocks(monkeypatch):
    agent = _make_agent_stub([
        {"role": "user", "content": "写 API 调用"},
        {"role": "assistant", "content": "加了 try/except"},
    ])
    llm_out = (
        "我刚才在做什么：实现 API 调用并加了异常处理。\n"
        "有用的规则/教训：所有外部调用必须 try/except。\n\n"
        '```experience\n'
        '{"scene": "外部 API 调用",'
        ' "knowledge": "网络不可靠，必须容错",'
        ' "rule_do": "所有外部调用包 try/except",'
        ' "rule_dont": "假设请求一定成功",'
        ' "priority": 3}\n'
        '```\n'
    )
    fake_lib = MagicMock()
    fake_lib.add_experience = MagicMock()
    from app.experience_library import SelfImprovementEngine
    real_init = SelfImprovementEngine.__init__

    def fake_init(self, agent=None, role=""):
        real_init(self, agent=agent, role=role)
        self.library = fake_lib

    with patch("app.llm.chat_no_stream",
               return_value={"content": llm_out}), \
         patch.object(SelfImprovementEngine, "__init__", fake_init):
        result = agent.think_now()
    assert result["ok"] is True
    assert result["experiences_saved"] == 1
    fake_lib.add_experience.assert_called_once()
    # Second positional arg is the Experience — verify the critical fields.
    args, _kw = fake_lib.add_experience.call_args
    role_arg, exp_arg = args
    assert role_arg == "general"
    assert "外部 API" in exp_arg.scene
    # rule_do maps into action_rules[], rule_dont into taboo_rules[]
    assert exp_arg.action_rules and "try/except" in exp_arg.action_rules[0]
    assert exp_arg.taboo_rules and "假设" in exp_arg.taboo_rules[0]
    # Priority normalized to string — numeric 3 → "high"
    assert exp_arg.priority == "high"


def test_think_now_strips_experience_blocks_from_display_summary():
    """The ```experience``` JSON blocks are machinery, not content the
    user should read. They must not appear in the assistant bubble."""
    agent = _make_agent_stub([
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ])
    llm_out = (
        "总结内容。\n\n"
        '```experience\n{"scene":"s","knowledge":"k","rule_do":"do",'
        '"rule_dont":"","priority":"medium"}\n```\n'
    )
    with patch("app.llm.chat_no_stream",
               return_value={"content": llm_out}):
        result = agent.think_now()
    assert "```experience" not in result["summary"]
    assert "scene" not in result["summary"]
    # The assistant event body also stripped
    msg_ev = next(ev for ev in agent.events
                  if ev.data.get("source") == "think_now")
    assert "```experience" not in msg_ev.data["content"]


def test_think_now_llm_failure_returns_error(monkeypatch):
    agent = _make_agent_stub([
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hey"},
    ])
    with patch("app.llm.chat_no_stream", side_effect=RuntimeError("LLM exploded")):
        result = agent.think_now()
    assert result["ok"] is False
    assert "llm_failed" in result["error"]
    # No assistant bubble inserted when LLM failed
    assert not any(ev.data.get("source") == "think_now" for ev in agent.events)


# ── growth-stats endpoint shape ──────────────────────────────────


def test_growth_stats_endpoint_returns_all_asset_counters():
    """The /growth-stats response must expose every counter the UI
    renders, with sane defaults on any data-layer exception."""
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from app.api.routers.agents import router
    from app.api.deps.auth import get_current_user, CurrentUser
    from app.api.deps.hub import get_hub as _get_hub

    # Minimal hub + agent stub
    fake_agent = SimpleNamespace(
        id="a1", name="test", role="general",
        provider="p", model="m",
        granted_skills=["sk1", "sk2"],
        bound_prompt_packs=["pp1"],
        events=[],
        profile=SimpleNamespace(
            rag_mode="private",
            rag_collection_ids=["kb1"],
        ),
    )
    fake_hub = SimpleNamespace(
        get_agent=lambda aid: fake_agent if aid == "a1" else None,
        agents={"a1": fake_agent},
        supervisor=None,
    )
    async def fake_user():
        return CurrentUser(user_id="u", role="superAdmin")
    app = FastAPI()
    app.dependency_overrides[get_current_user] = fake_user
    app.dependency_overrides[_get_hub] = lambda: fake_hub
    app.include_router(router)

    # Patch all data sources
    fake_lib = SimpleNamespace(
        get_experience_count=lambda r: 7,
        get_all_role_counts=lambda: {"general": 7, "coder": 3},
    )
    fake_mm = SimpleNamespace(count_facts=lambda aid: 42)
    fake_kb = SimpleNamespace(name="Cloud KB", doc_count=7187)
    fake_dkb_store = SimpleNamespace(get=lambda kid: fake_kb)

    with patch("app.experience_library._get_global_library",
               return_value=fake_lib), \
         patch("app.core.memory.get_memory_manager",
               return_value=fake_mm), \
         patch("app.rag_provider.get_domain_kb_store",
               return_value=fake_dkb_store), \
         patch("app.knowledge.list_entries",
               return_value=[
                   {"tags": ["shared-by-agent", "general"]},
                   {"tags": ["shared-by-agent", "coder"]},
                   {"tags": ["shared-by-agent", "general"]},
                   {"tags": ["random-tag"]},
               ]), \
         TestClient(app) as c:
        r = c.get("/api/portal/agent/a1/growth-stats")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["agent_id"] == "a1"
    assert d["role"] == "general"
    assert d["experience_count"] == 7
    assert d["experience_roles"] == {"general": 7, "coder": 3}
    assert d["memory_facts"] == 42
    assert d["granted_skills"] == 2
    assert d["bound_prompt_packs"] == 1
    assert len(d["domain_kbs"]) == 1
    assert d["domain_kbs"][0]["doc_count"] == 7187
    assert d["domain_kb_chunks_total"] == 7187
    # Only 2 of the mock KB entries are shared-by-agent+general
    assert d["shared_knowledge_contributions"] == 2
    # last_self_summary — none in events, so 0
    assert d["last_self_summary_at"] == 0.0


def test_growth_stats_tolerates_missing_modules():
    """Each data source is independently guarded. An unconfigured
    memory manager or empty KB store must not 500 the endpoint."""
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from app.api.routers.agents import router
    from app.api.deps.auth import get_current_user, CurrentUser
    from app.api.deps.hub import get_hub as _get_hub

    fake_agent = SimpleNamespace(
        id="a1", name="test", role="general",
        provider="p", model="m",
        granted_skills=[], bound_prompt_packs=[],
        events=[],
        profile=SimpleNamespace(rag_mode="none", rag_collection_ids=[]),
    )
    fake_hub = SimpleNamespace(
        get_agent=lambda aid: fake_agent if aid == "a1" else None,
        agents={"a1": fake_agent},
        supervisor=None,
    )
    async def fake_user():
        return CurrentUser(user_id="u", role="superAdmin")
    app = FastAPI()
    app.dependency_overrides[get_current_user] = fake_user
    app.dependency_overrides[_get_hub] = lambda: fake_hub
    app.include_router(router)

    with patch("app.experience_library._get_global_library",
               side_effect=RuntimeError("no lib")), \
         patch("app.core.memory.get_memory_manager",
               side_effect=RuntimeError("no mm")), \
         patch("app.rag_provider.get_domain_kb_store",
               side_effect=RuntimeError("no dkb")), \
         patch("app.knowledge.list_entries",
               side_effect=RuntimeError("no kb")), \
         TestClient(app) as c:
        r = c.get("/api/portal/agent/a1/growth-stats")
    assert r.status_code == 200
    d = r.json()
    assert d["experience_count"] == 0
    assert d["memory_facts"] == 0
    assert d["domain_kbs"] == []
    assert d["shared_knowledge_contributions"] == 0
