"""新 A.7 / A.8 / A.9 — memory_refs tracing + REST delete flow."""
from __future__ import annotations

import os
import sys
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


from app.core.memory import MemoryManager, SemanticFact  # noqa: E402


@pytest.fixture
def mm_and_hub(tmp_path, monkeypatch):
    mgr = MemoryManager(db_path=str(tmp_path / "mem.db"))
    mgr._chromadb_available = False
    from app.core import memory as _mem
    monkeypatch.setattr(_mem, "get_memory_manager", lambda: mgr)

    # Fake agent + hub for the tool caller lookup.
    class _FakeAgent:
        id = "a-alice"
        role = "coder"
        _turn_memory_refs = None

    class _FakeHub:
        agents = {"a-alice": _FakeAgent()}
        def get_agent(self, aid):
            return self.agents.get(aid)

    hub = _FakeHub()
    import app.tools_split._common as common
    import app.tools_split.knowledge as _knmod
    monkeypatch.setattr(common, "_get_hub", lambda: hub)
    monkeypatch.setattr(_knmod, "_get_hub", lambda: hub)
    from app import hub as _hub_pkg
    monkeypatch.setattr(_hub_pkg, "get_hub", lambda: hub)
    yield mgr, hub


def _seed(mm, agent_id, content, category="outcome"):
    mm.upsert_fact(SemanticFact(
        agent_id=agent_id, category=category,
        content=content, source="seed", confidence=0.9,
    ))
    facts = mm.get_recent_facts(agent_id)
    return facts[0].id


# ── A.7: memory_recall populates _turn_memory_refs ───────────────


def test_memory_recall_populates_agent_bucket(mm_and_hub):
    mm, hub = mm_and_hub
    _seed(mm, "a-alice", "pytest is the test runner in this project")

    from app.tools_split.knowledge import _tool_memory_recall
    _tool_memory_recall(query="test runner",
                        _caller_agent_id="a-alice")

    agent = hub.agents["a-alice"]
    refs = getattr(agent, "_turn_memory_refs", None)
    assert refs is not None
    assert len(refs) == 1
    assert refs[0]["id"]
    assert "pytest" in refs[0]["content_preview"]
    assert refs[0]["category"] == "outcome"
    assert "confidence" in refs[0]
    assert "age_days" in refs[0]


def test_memory_recall_dedups_within_turn(mm_and_hub):
    mm, hub = mm_and_hub
    _seed(mm, "a-alice", "pytest is the test runner")
    from app.tools_split.knowledge import _tool_memory_recall
    _tool_memory_recall(query="test runner",
                        _caller_agent_id="a-alice")
    # Second call same query — bucket should NOT double up.
    _tool_memory_recall(query="pytest",
                        _caller_agent_id="a-alice")
    agent = hub.agents["a-alice"]
    refs = agent._turn_memory_refs
    assert len(refs) == 1    # deduped by id


def test_memory_recall_empty_does_not_touch_bucket(mm_and_hub):
    mm, hub = mm_and_hub
    from app.tools_split.knowledge import _tool_memory_recall
    _tool_memory_recall(query="nothing exists",
                        _caller_agent_id="a-alice")
    agent = hub.agents["a-alice"]
    refs = getattr(agent, "_turn_memory_refs", None)
    assert not refs


# ── A.9: REST delete flow ─────────────────────────────────────────


@pytest.fixture
def client(mm_and_hub, monkeypatch):
    from app.api.deps.auth import get_current_user, CurrentUser
    from app.api.routers import memory_refs as mem_router

    async def _fake_user():
        return CurrentUser(user_id="u1", role="superAdmin")

    app = FastAPI()
    app.dependency_overrides[get_current_user] = _fake_user
    app.include_router(mem_router.router)
    with TestClient(app) as tc:
        yield tc


def test_rest_get_fact(mm_and_hub, client):
    mm, _ = mm_and_hub
    fid = _seed(mm, "a-alice", "some important fact")
    r = client.get(f"/api/portal/memory/{fid}")
    assert r.status_code == 200
    d = r.json()
    assert d["id"] == fid
    assert d["agent_id"] == "a-alice"
    assert "important fact" in d["content"]


def test_rest_get_missing_404(client):
    r = client.get("/api/portal/memory/nonexistent")
    assert r.status_code == 404


def test_rest_delete_removes_the_memory(mm_and_hub, client):
    mm, _ = mm_and_hub
    fid = _seed(mm, "a-alice", "wrong fact that must go")
    r = client.delete(f"/api/portal/memory/{fid}")
    assert r.status_code == 200
    d = r.json()
    assert d["deleted_id"] == fid
    assert d["agent_id"] == "a-alice"
    assert "wrong fact" in d["preview"]
    # Actually gone from the store.
    facts = mm.get_recent_facts("a-alice")
    assert all(f.id != fid for f in facts)


def test_rest_delete_missing_404(client):
    r = client.delete("/api/portal/memory/nonexistent")
    assert r.status_code == 404


def test_rest_bulk_delete(mm_and_hub, client):
    mm, _ = mm_and_hub
    ids = [_seed(mm, "a-alice", f"fact {i}") for i in range(4)]
    r = client.post("/api/portal/memory/bulk_delete",
                    json={"ids": ids[:3] + ["does-not-exist"]})
    assert r.status_code == 200
    d = r.json()
    assert d["deleted"] == 3
    assert d["skipped"] == 1
    remaining = mm.get_recent_facts("a-alice")
    assert len(remaining) == 1
    assert remaining[0].id == ids[3]


def test_rest_bulk_delete_empty_400(client):
    r = client.post("/api/portal/memory/bulk_delete", json={"ids": []})
    assert r.status_code == 400


def test_rest_stats_for_agent(mm_and_hub, client):
    mm, _ = mm_and_hub
    _seed(mm, "a-alice", "rule 1", category="rule")
    _seed(mm, "a-alice", "rule 2", category="rule")
    _seed(mm, "a-alice", "outcome 1", category="outcome")
    r = client.get("/api/portal/memory/stats?agent_id=a-alice")
    assert r.status_code == 200
    d = r.json()
    assert d["agent_id"] == "a-alice"
    assert d["total"] == 3
    assert d["by_category"].get("rule") == 2
    assert d["by_category"].get("outcome") == 1


# ── deleted → memory_recall misses → next save re-inserts ───────


def test_delete_then_save_reinserts_fresh(mm_and_hub, client):
    """Golden path: user flags bad memory → we delete → next save_experience
    call on a similar topic creates a new (hopefully correct) memory
    instead of refreshing the (deleted) old one."""
    mm, hub = mm_and_hub
    fid = _seed(mm, "a-alice",
                "API default port is 8080")
    # User marks incorrect.
    r = client.delete(f"/api/portal/memory/{fid}")
    assert r.status_code == 200

    # Agent later saves the corrected version.
    from app.core.memory import SemanticFact as _SF
    res = mm.upsert_fact(_SF(
        agent_id="a-alice", category="outcome",
        content="API default port is 9090",
        source="correction-after-flag",
    ))
    assert res["action"] == "inserted"   # NEW insert, not refresh
    facts = mm.get_recent_facts("a-alice")
    assert len(facts) == 1
    assert "9090" in facts[0].content
