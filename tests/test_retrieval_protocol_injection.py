"""Retrieval Protocol auto-injection into system prompt.

Root bug: _tool_knowledge_lookup / Pack v2 / spill fixes are useless if
the LLM never decides to call knowledge_lookup. Qwen 3.5-35B defaults to
bash/grep for "search the KB" questions unless told otherwise.

Fix: _build_retrieval_protocol() returns an imperative 5-rule block for
agents that have a bound KB. Returns empty for others. This lives in
code (agent.py), not profile JSON, so the hub's periodic save cannot
wipe it.
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _profile(**kw):
    # AgentProfile minimal surrogate — only the attributes the helper reads.
    defaults = dict(rag_mode="shared", rag_collection_ids=[],
                    agent_class="enterprise")
    defaults.update(kw)
    return SimpleNamespace(**defaults)


# ── when to inject ───────────────────────────────────────────────────


def test_injects_for_private_with_bound_kb():
    from app.agent import _build_retrieval_protocol
    p = _profile(rag_mode="private", rag_collection_ids=["dkb_1"])
    out = _build_retrieval_protocol(p)
    assert out
    assert "knowledge_lookup" in out


def test_injects_for_both_with_bound_kb():
    from app.agent import _build_retrieval_protocol
    p = _profile(rag_mode="both", rag_collection_ids=["dkb_1"])
    assert _build_retrieval_protocol(p)


def test_injects_for_advisor_class_even_without_kb_yet():
    """Advisor-class agent: inject protocol so they use knowledge_lookup
    the moment a KB is bound, without waiting for a re-save."""
    from app.agent import _build_retrieval_protocol
    p = _profile(rag_mode="private", rag_collection_ids=[],
                 agent_class="advisor")
    assert _build_retrieval_protocol(p)


# ── when NOT to inject ───────────────────────────────────────────────


def test_skips_for_rag_mode_none():
    from app.agent import _build_retrieval_protocol
    p = _profile(rag_mode="none", rag_collection_ids=["dkb_1"],
                 agent_class="advisor")
    assert _build_retrieval_protocol(p) == ""


def test_skips_for_empty_rag_mode():
    from app.agent import _build_retrieval_protocol
    p = _profile(rag_mode="", rag_collection_ids=["dkb_1"],
                 agent_class="advisor")
    assert _build_retrieval_protocol(p) == ""


def test_skips_for_enterprise_without_bound_kb():
    """Plain enterprise agent with shared mode but no private KB —
    no domain knowledge to cite, protocol would be noise."""
    from app.agent import _build_retrieval_protocol
    p = _profile(rag_mode="shared", rag_collection_ids=[],
                 agent_class="enterprise")
    assert _build_retrieval_protocol(p) == ""


def test_skips_for_none_profile():
    from app.agent import _build_retrieval_protocol
    assert _build_retrieval_protocol(None) == ""


# ── content contract ───────────────────────────────────────────────


def test_protocol_enforces_core_rules():
    from app.agent import _build_retrieval_protocol
    p = _profile(rag_mode="private", rag_collection_ids=["dkb_1"])
    out = _build_retrieval_protocol(p)
    # 5 imperative rules must survive any future edit
    assert "knowledge_lookup" in out
    assert "bash" in out  # explicit ban
    assert "read_file" in out
    assert "source_file" in out or "heading_path" in out  # citation format
    assert "未找到" in out or "未命中" in out  # no-fabricate fallback


# ── wired into prompt build paths ─────────────────────────────────


def test_helper_is_referenced_by_both_prompt_builders():
    """Both agent.py's legacy/V2 builders AND agent_llm.py must call
    the helper — otherwise some agents will miss the injection."""
    import app.agent as _a
    import app.agent_llm as _al
    # agent.py: verify the symbol is importable from the module
    assert hasattr(_a, "_build_retrieval_protocol")
    # Both modules' source should reference the helper
    with open(_a.__file__) as f:
        a_src = f.read()
    with open(_al.__file__) as f:
        al_src = f.read()
    assert "_build_retrieval_protocol" in a_src
    assert "_build_retrieval_protocol" in al_src
    # Called at least 2x in agent.py (two prompt-build paths)
    assert a_src.count("_build_retrieval_protocol(") >= 3  # defn + 2 calls
