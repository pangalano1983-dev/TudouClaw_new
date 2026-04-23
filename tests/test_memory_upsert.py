"""新 A.1 / A.2 — MemoryManager.upsert_fact + recall.

Similarity-gated write behavior:

  * New fact, no prior similar    → action=inserted
  * New fact, exact duplicate      → action=unchanged (id preserved)
  * New fact, paraphrase above     → action=updated   (old id kept, content replaced)
    threshold
  * New fact, below threshold      → action=inserted  (coexists)

`recall` is thin wrapper that returns plain dicts.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


from app.core.memory import MemoryManager, SemanticFact  # noqa: E402


@pytest.fixture
def mm(tmp_path):
    db = str(tmp_path / "mem.db")
    mgr = MemoryManager(db_path=db)
    # Force FTS5 + bigram fallback path (no ChromaDB) so tests are
    # deterministic and don't require the optional embeddings deps.
    mgr._chromadb_available = False
    yield mgr
    try:
        mgr._conn.close()
    except Exception:
        pass


def _fact(content: str, category: str = "outcome",
          source: str = "test", agent_id: str = "a-alice",
          confidence: float = 0.9) -> SemanticFact:
    return SemanticFact(
        agent_id=agent_id, category=category, content=content,
        source=source, confidence=confidence,
    )


# ── bigram similarity helper ───────────────────────────────────────


def test_bigram_similarity_identical_strings():
    assert MemoryManager._bigram_similarity("hello world", "hello world") == 1.0


def test_bigram_similarity_paraphrase_is_high():
    # Same semantic content with minor rewording.
    s1 = "terraform apply is blocked in production environment"
    s2 = "terraform apply blocked in prod environment"
    sim = MemoryManager._bigram_similarity(s1, s2)
    assert sim > 0.7, f"expected >0.7, got {sim}"


def test_bigram_similarity_different_topics_is_low():
    sim = MemoryManager._bigram_similarity(
        "terraform apply in production is dangerous",
        "the user prefers markdown over rst",
    )
    assert sim < 0.3, f"expected <0.3, got {sim}"


def test_bigram_similarity_empty_inputs():
    assert MemoryManager._bigram_similarity("", "anything") == 0.0
    assert MemoryManager._bigram_similarity("something", "") == 0.0
    assert MemoryManager._bigram_similarity("", "") == 0.0


# ── upsert: insert path ────────────────────────────────────────────


def test_upsert_insert_when_no_prior(mm):
    r = mm.upsert_fact(_fact("The project uses pytest for testing."))
    assert r["action"] == "inserted"
    assert r["id"]
    assert r["matched_id"] == ""
    facts = mm.get_recent_facts("a-alice")
    assert len(facts) == 1
    assert facts[0].content.startswith("The project")


def test_upsert_rejects_empty_content(mm):
    with pytest.raises(ValueError):
        mm.upsert_fact(_fact("", agent_id="a"))


def test_upsert_rejects_empty_agent_id(mm):
    with pytest.raises(ValueError):
        mm.upsert_fact(_fact("anything", agent_id=""))


# ── upsert: unchanged path ─────────────────────────────────────────


def test_upsert_exact_duplicate_is_unchanged(mm):
    content = "The deploy pipeline uses GitHub Actions."
    r1 = mm.upsert_fact(_fact(content))
    t0 = time.time()
    time.sleep(0.01)
    r2 = mm.upsert_fact(_fact(content))
    assert r2["action"] == "unchanged"
    assert r2["id"] == r1["id"]
    # updated_at on the stored fact should NOT have been bumped.
    stored = mm.get_recent_facts("a-alice")[0]
    assert stored.updated_at < t0 + 0.005, (
        "exact-duplicate upsert should not churn updated_at"
    )


# ── upsert: update / refresh path ─────────────────────────────────


def test_upsert_paraphrase_refreshes_in_place(mm):
    # Seed with original.
    first = mm.upsert_fact(_fact(
        "terraform apply is blocked in production environment",
        source="first-write",
    ))
    assert first["action"] == "inserted"
    orig_id = first["id"]

    # Upsert a paraphrase that should exceed the similarity threshold.
    r = mm.upsert_fact(_fact(
        "terraform apply blocked in prod environment",
        source="second-write",
        confidence=0.95,
    ), threshold=0.65)
    assert r["action"] == "updated"
    assert r["matched_id"] == orig_id
    assert r["similarity"] >= 0.65
    # Previous content returned for audit.
    assert "production environment" in r["previous"]

    # Old id is kept; content replaced; created_at preserved; updated_at bumped.
    facts = mm.get_recent_facts("a-alice")
    assert len(facts) == 1
    assert facts[0].id == orig_id
    assert "prod environment" in facts[0].content
    assert "production environment" not in facts[0].content
    # The source field carries audit of the refresh.
    assert "refreshed" in facts[0].source.lower()
    assert facts[0].confidence == 0.95


def test_upsert_correction_overwrites_wrong_old(mm):
    """Historical memory was wrong; new conclusion supersedes."""
    mm.upsert_fact(_fact(
        "The default port for the API server is 8080.",
    ))
    # User learned the truth later.
    r = mm.upsert_fact(_fact(
        "The default port for the API server is 9090, not 8080.",
        source="user-correction",
    ), threshold=0.55)
    assert r["action"] == "updated"
    facts = mm.get_recent_facts("a-alice")
    assert len(facts) == 1
    assert "9090" in facts[0].content
    assert "refreshed" in facts[0].source


# ── upsert: coexist path ──────────────────────────────────────────


def test_upsert_different_topics_coexist(mm):
    mm.upsert_fact(_fact("The deploy pipeline uses GitHub Actions."))
    r = mm.upsert_fact(_fact("The user prefers Markdown for documentation."))
    assert r["action"] == "inserted"
    assert len(mm.get_recent_facts("a-alice")) == 2


def test_upsert_respects_category_gate(mm):
    """A 'rule' with same content as an 'outcome' should still refresh
    only within its category by default."""
    # Seed an outcome fact.
    mm.upsert_fact(_fact(
        "terraform apply blocks on production env",
        category="outcome",
    ))
    # A rule with near-identical wording but different category
    # should NOT refresh the outcome (they're different categories).
    r = mm.upsert_fact(_fact(
        "terraform apply blocks on production env",
        category="rule",
    ), threshold=0.5)
    assert r["action"] == "inserted"
    # Both exist.
    outcomes = mm.get_recent_facts("a-alice", category="outcome")
    rules = mm.get_recent_facts("a-alice", category="rule")
    assert len(outcomes) == 1
    assert len(rules) == 1


def test_upsert_agent_isolation(mm):
    mm.upsert_fact(_fact("alice's secret", agent_id="a-alice"))
    r = mm.upsert_fact(_fact("alice's secret", agent_id="a-bob"))
    # Same content, different agent → no cross-agent refresh.
    assert r["action"] == "inserted"
    assert len(mm.get_recent_facts("a-alice")) == 1
    assert len(mm.get_recent_facts("a-bob")) == 1


# ── find_similar_fact direct ───────────────────────────────────────


def test_find_similar_returns_none_when_no_match(mm):
    f, s = mm.find_similar_fact("a-alice", "totally new concept here")
    assert f is None
    assert s == 0.0


def test_find_similar_returns_best_match(mm):
    mm.upsert_fact(_fact("pytest is the testing framework in use"))
    mm.upsert_fact(_fact("docs live in the docs/ folder"))
    f, s = mm.find_similar_fact(
        "a-alice", "we use pytest for testing", threshold=0.3,
    )
    assert f is not None
    assert "pytest" in f.content


# ── recall ─────────────────────────────────────────────────────────


def test_recall_returns_dicts(mm):
    mm.upsert_fact(_fact("pytest is the test runner"))
    mm.upsert_fact(_fact("CI is GitHub Actions"))
    out = mm.recall("a-alice", "testing framework")
    assert isinstance(out, list)
    assert all(isinstance(x, dict) for x in out)
    # Each dict carries the standard keys.
    for d in out:
        assert {"id", "category", "content", "confidence",
                "source", "updated_at", "age_days"} <= set(d.keys())


def test_recall_empty_for_no_matches(mm):
    out = mm.recall("a-ghost", "anything")
    assert out == []


def test_recall_respects_category_filter(mm):
    mm.upsert_fact(_fact("use pytest", category="rule"))
    mm.upsert_fact(_fact("deploy succeeded", category="outcome"))
    out = mm.recall("a-alice", "pytest", category="rule")
    assert len(out) >= 1
    assert all(d["category"] == "rule" for d in out)


def test_recall_includes_age_days(mm):
    # Insert a fact with a timestamp far in the past.
    f = _fact("an old fact")
    f.created_at = time.time() - 86400 * 10    # 10 days ago
    f.updated_at = f.created_at
    mm.save_fact(f, preserve_timestamps=True)
    out = mm.recall("a-alice", "old fact")
    assert out
    assert out[0]["age_days"] >= 9
