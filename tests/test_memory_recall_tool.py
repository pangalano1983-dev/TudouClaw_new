"""新 A.3 — memory_recall LLM tool.

Lightweight test of the coordination-module wrapper that exposes the
MemoryManager.recall() to LLM tool calls.
"""
from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


from app.core.memory import MemoryManager, SemanticFact  # noqa: E402
from app.tools_split.knowledge import _tool_memory_recall  # noqa: E402


@pytest.fixture
def mm_patched(tmp_path, monkeypatch):
    """Build a fresh MemoryManager and patch core.memory.get_memory_manager."""
    mgr = MemoryManager(db_path=str(tmp_path / "mem.db"))
    mgr._chromadb_available = False     # force deterministic FTS+bigram path
    from app.core import memory as _mem
    monkeypatch.setattr(_mem, "get_memory_manager", lambda: mgr)
    yield mgr
    try:
        mgr._conn.close()
    except Exception:
        pass


def _seed(mm, agent_id: str, content: str, category: str = "outcome"):
    mm.upsert_fact(SemanticFact(
        agent_id=agent_id, category=category,
        content=content, source="seed", confidence=0.9,
    ))


# ── guard rails ────────────────────────────────────────────────────


def test_missing_caller_errors(mm_patched):
    out = _tool_memory_recall(query="anything")
    assert out.startswith("Error")
    assert "calling" in out.lower() or "caller" in out.lower()


def test_empty_query_errors(mm_patched):
    out = _tool_memory_recall(query="", _caller_agent_id="a-alice")
    assert out.startswith("Error")
    assert "query" in out.lower()


def test_no_memory_manager_returns_error(monkeypatch):
    from app.core import memory as _mem
    monkeypatch.setattr(_mem, "get_memory_manager", lambda: None)
    out = _tool_memory_recall(query="pytest", _caller_agent_id="a-alice")
    assert out.startswith("Error")


# ── empty memory ──────────────────────────────────────────────────


def test_recall_with_empty_memory(mm_patched):
    out = _tool_memory_recall(query="pytest",
                              _caller_agent_id="a-alice")
    assert "No prior memory" in out
    # Suggests what to do instead.
    assert "web_search" in out or "knowledge_lookup" in out
    assert "save_experience" in out


# ── recall with seeded memory ─────────────────────────────────────


def test_recall_returns_seeded_fact(mm_patched):
    _seed(mm_patched, "a-alice",
          "The project uses pytest with fixtures in conftest.py")
    out = _tool_memory_recall(query="pytest configuration",
                              _caller_agent_id="a-alice")
    assert "Memory recall" in out
    assert "pytest" in out
    assert "conftest" in out
    # Structured columns present.
    assert "conf=" in out
    assert "age=" in out
    assert "outcome" in out


def test_recall_respects_top_k(mm_patched):
    for i in range(8):
        _seed(mm_patched, "a-alice",
              f"fact number {i} about deployment pipeline item {i}")
    out = _tool_memory_recall(query="deployment", top_k=3,
                              _caller_agent_id="a-alice")
    # Count "[N]" markers in the output.
    import re
    hits = re.findall(r"^\s+\[\d+\]", out, flags=re.MULTILINE)
    assert len(hits) <= 3


def test_recall_respects_category_filter(mm_patched):
    _seed(mm_patched, "a-alice",
          "testing pipeline: write tests first",
          category="rule")
    _seed(mm_patched, "a-alice",
          "testing pipeline: deploy finished at 10:00",
          category="outcome")
    # Filter to rule → the outcome hit must be excluded.
    out = _tool_memory_recall(query="testing pipeline",
                              category="rule",
                              _caller_agent_id="a-alice")
    assert "write tests first" in out
    assert "deploy finished" not in out


def test_recall_isolates_agents(mm_patched):
    _seed(mm_patched, "a-alice", "alice's unique fact")
    _seed(mm_patched, "a-bob", "bob's unique fact")
    out_a = _tool_memory_recall(query="unique",
                                _caller_agent_id="a-alice")
    out_b = _tool_memory_recall(query="unique",
                                _caller_agent_id="a-bob")
    assert "alice" in out_a
    assert "alice" not in out_b
    assert "bob" in out_b
    assert "bob" not in out_a


def test_recall_invalid_top_k_is_clamped(mm_patched):
    _seed(mm_patched, "a-alice", "some fact")
    out_low = _tool_memory_recall(query="fact", top_k=-5,
                                  _caller_agent_id="a-alice")
    assert "Memory recall" in out_low    # doesn't crash
    out_high = _tool_memory_recall(query="fact", top_k=9999,
                                   _caller_agent_id="a-alice")
    assert "Memory recall" in out_high   # clamped


def test_recall_truncates_long_content(mm_patched):
    _seed(mm_patched, "a-alice", "long content " + "X" * 5000)
    out = _tool_memory_recall(query="long content",
                              _caller_agent_id="a-alice")
    assert "…" in out     # trimmed marker
    # Overall output should NOT be huge.
    assert len(out) < 2000


def test_recall_reminds_about_refresh_on_hit(mm_patched):
    _seed(mm_patched, "a-alice", "some fact")
    out = _tool_memory_recall(query="some fact",
                              _caller_agent_id="a-alice")
    # The closing hint mentions save_experience + refresh.
    assert "save_experience" in out


# ── schema wiring ─────────────────────────────────────────────────


def test_tool_registered_in_dispatcher():
    from app.tools import _TOOL_FUNCS
    assert "memory_recall" in _TOOL_FUNCS


def test_tool_has_schema_entry():
    from app.tools import TOOL_DEFINITIONS
    names = {
        t["function"]["name"] for t in TOOL_DEFINITIONS
        if isinstance(t, dict) and t.get("type") == "function"
    }
    assert "memory_recall" in names


def test_tool_in_minimal_default_set():
    from app.agent import Agent
    assert "memory_recall" in Agent._MINIMAL_DEFAULT_TOOLS
