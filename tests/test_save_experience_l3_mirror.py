"""新 A.4 — save_experience mirrors to the calling agent's L3 memory.

Verifies:
  * A call to save_experience with a caller context writes BOTH:
      - an Experience to the role experience library (legacy behavior)
      - a SemanticFact to the caller's L3 memory via upsert
  * exp_type → category mapping (retrospective → rule, active_learning → reasoning)
  * priority → confidence mapping
  * Similarity refresh: a second save with paraphrased content updates
    the L3 fact instead of adding a dupe
"""
from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


from app.core.memory import MemoryManager  # noqa: E402


@pytest.fixture
def wiring(tmp_path, monkeypatch):
    """Patch MemoryManager + ExperienceLibrary + Hub."""
    # 1. MemoryManager singleton patched to a fresh tmp db.
    mgr = MemoryManager(db_path=str(tmp_path / "mem.db"))
    mgr._chromadb_available = False
    from app.core import memory as _mem
    monkeypatch.setattr(_mem, "get_memory_manager", lambda: mgr)

    # 2. Hub: fake agent with a role.
    class _FakeAgent:
        id = "a-alice"
        role = "coder"
    class _FakeHub:
        agents = {"a-alice": _FakeAgent()}
        def get_agent(self, aid):
            return self.agents.get(aid)
    fake_hub = _FakeHub()
    import app.tools_split._common as _common
    import app.tools_split.knowledge as _knmod
    monkeypatch.setattr(_common, "_get_hub", lambda: fake_hub)
    monkeypatch.setattr(_knmod, "_get_hub", lambda: fake_hub)

    # 3. Experience library is real but uses an isolated dir so test
    # doesn't leak.
    import app.experience_library as _el
    # Re-init singleton pointing at tmp dir.
    _orig = getattr(_el, "_lib_singleton", None)
    monkeypatch.setenv("TUDOU_CLAW_DATA_DIR", str(tmp_path))
    if _orig is not None:
        monkeypatch.setattr(_el, "_lib_singleton", None)

    yield mgr
    try:
        mgr._conn.close()
    except Exception:
        pass


def _call_save(content: str, exp_type: str = "retrospective",
               priority: str = "medium",
               scene: str = "writing unit tests for async code") -> str:
    from app.tools_split.knowledge import _tool_save_experience
    return _tool_save_experience(
        scene=scene,
        core_knowledge=content,
        priority=priority,
        exp_type=exp_type,
        _caller_agent_id="a-alice",
    )


# ── basic mirror ──────────────────────────────────────────────────


def test_mirror_creates_l3_fact(wiring):
    mm = wiring
    out = _call_save("use pytest-asyncio and fixture scope='session'")
    assert out.startswith("✓ Experience saved")
    assert "L3 inserted" in out
    facts = mm.get_recent_facts("a-alice")
    assert len(facts) == 1
    assert "pytest-asyncio" in facts[0].content
    # Scene wrapped in brackets in the compact L3 form.
    assert "[writing unit tests for async code]" in facts[0].content


def test_retrospective_maps_to_rule_category(wiring):
    mm = wiring
    _call_save("always await the coroutine before returning",
               exp_type="retrospective")
    facts = mm.get_recent_facts("a-alice")
    assert facts[0].category == "rule"


def test_active_learning_maps_to_reasoning_category(wiring):
    mm = wiring
    _call_save("after benchmarking, uvloop won by 1.4x over asyncio default",
               exp_type="active_learning")
    facts = mm.get_recent_facts("a-alice")
    assert facts[0].category == "reasoning"


def test_priority_high_maps_to_high_confidence(wiring):
    mm = wiring
    _call_save("critical finding about memory leaks", priority="high")
    facts = mm.get_recent_facts("a-alice")
    assert abs(facts[0].confidence - 0.95) < 0.01


def test_priority_low_maps_to_low_confidence(wiring):
    mm = wiring
    _call_save("minor observation", priority="low")
    facts = mm.get_recent_facts("a-alice")
    assert abs(facts[0].confidence - 0.6) < 0.01


# ── similarity refresh on repeat ──────────────────────────────────


def test_mirror_refreshes_l3_on_similar_save(wiring):
    mm = wiring
    _call_save("always use pytest-asyncio for async tests")
    out = _call_save(
        "always use pytest-asyncio for async tests in this project"
    )
    # Second call saw high similarity → L3 refreshed, not re-added.
    assert "L3 refreshed" in out
    facts = mm.get_recent_facts("a-alice")
    assert len(facts) == 1     # only one L3 fact
    # Newer content wins.
    assert "in this project" in facts[0].content


def test_mirror_inserts_on_different_topic(wiring):
    mm = wiring
    _call_save("use pytest-asyncio", scene="async unit tests")
    out = _call_save(
        "use loguru with sinks",
        scene="project logging setup",
    )
    assert "L3 inserted" in out
    assert len(mm.get_recent_facts("a-alice")) == 2


# ── backwards compat: missing caller just skips mirror ────────────


def test_missing_caller_still_saves_to_experience_lib(wiring):
    """No _caller_agent_id → experience saved normally, no L3 mirror."""
    mm = wiring
    from app.tools_split.knowledge import _tool_save_experience
    out = _tool_save_experience(
        scene="test",
        core_knowledge="some core knowledge",
        role="coder",   # explicit role so exp_lib still routes
    )
    assert out.startswith("✓ Experience saved")
    # No mirror attempted, no L3 fact created.
    assert "L3" not in out or "skipped" in out
    assert len(mm.get_recent_facts("a-alice")) == 0


# ── action_rules / taboo_rules folded into L3 content ─────────────


def test_action_and_taboo_rules_flow_into_l3(wiring):
    mm = wiring
    from app.tools_split.knowledge import _tool_save_experience
    _tool_save_experience(
        scene="deploying to production",
        core_knowledge="always run smoke tests first",
        action_rules=["run ./scripts/smoke.sh",
                      "check /health endpoint"],
        taboo_rules=["never skip the canary stage"],
        _caller_agent_id="a-alice",
    )
    facts = mm.get_recent_facts("a-alice")
    assert len(facts) == 1
    body = facts[0].content
    assert "run ./scripts/smoke.sh" in body
    assert "never skip the canary stage" in body
    assert "DO:" in body
    assert "DON'T:" in body
