"""RAG v1-B — Hybrid retrieval (BM25 + Vector + RRF).

Covers:
  * _tokenize: latin + CJK per-char
  * _bm25_search: scores keyword matches, handles Chinese
  * _rrf_fuse: reciprocal rank fusion
  * hybrid_search: graceful degradation paths
"""
from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


class _FakeCollection:
    def __init__(self):
        self._ids: list[str] = []
        self._docs: list[str] = []
        self._metas: list[dict] = []

    def upsert(self, ids, documents, metadatas):
        for i, id_ in enumerate(ids):
            if id_ in self._ids:
                idx = self._ids.index(id_)
                self._docs[idx] = documents[i]
                self._metas[idx] = metadatas[i]
            else:
                self._ids.append(id_)
                self._docs.append(documents[i])
                self._metas.append(metadatas[i])

    def count(self):
        return len(self._ids)

    def get(self, ids=None, include=None):
        include = include or []
        if ids is None:
            sel_idx = list(range(len(self._ids)))
        else:
            sel_idx = [self._ids.index(i) for i in ids if i in self._ids]
        out = {"ids": [self._ids[i] for i in sel_idx]}
        if "metadatas" in include:
            out["metadatas"] = [self._metas[i] for i in sel_idx]
        if "documents" in include:
            out["documents"] = [self._docs[i] for i in sel_idx]
        return out

    def query(self, query_texts, n_results):
        # Simple lexical "vector" stub: score by shared lowercase chars
        # with query string — deterministic and reasonable.
        q = (query_texts[0] or "").lower()
        qset = set(q)
        scored = []
        for i, d in enumerate(self._docs):
            dset = set(d.lower())
            overlap = len(qset & dset)
            dist = 1.0 / (overlap + 1)
            scored.append((self._ids[i], d, self._metas[i], dist))
        scored.sort(key=lambda x: x[3])
        scored = scored[:n_results]
        return {
            "ids": [[s[0] for s in scored]],
            "documents": [[s[1] for s in scored]],
            "metadatas": [[s[2] for s in scored]],
            "distances": [[s[3] for s in scored]],
        }


@pytest.fixture
def registry():
    import app.rag_provider as rp
    reg = rp.RAGProviderRegistry.__new__(rp.RAGProviderRegistry)
    reg._providers = {}
    reg._loaded = True
    coll = _FakeCollection()

    class _FakeMM:
        def _get_chroma_collection(self, name):
            return coll

    reg._get_memory_manager = lambda: _FakeMM()
    yield reg, coll


# ── _tokenize ────────────────────────────────────────────


def test_tokenize_latin_basic():
    from app.rag_provider import RAGProviderRegistry as R
    assert R._tokenize("Hello, World! 2026") == ["hello", "world", "2026"]


def test_tokenize_cjk_per_char():
    from app.rag_provider import RAGProviderRegistry as R
    # Each Chinese char is a token, Latin words grouped normally.
    toks = R._tokenize("云计算 in 2026")
    assert "云" in toks and "计" in toks and "算" in toks
    assert "2026" in toks


def test_tokenize_empty():
    from app.rag_provider import RAGProviderRegistry as R
    assert R._tokenize("") == []
    assert R._tokenize(None) == []


def test_tokenize_punctuation_only():
    from app.rag_provider import RAGProviderRegistry as R
    assert R._tokenize("..., ?!:") == []


# ── _rrf_fuse ───────────────────────────────────────────


def test_rrf_basic_two_lists():
    from app.rag_provider import RAGProviderRegistry as R
    a = [("x", 1.0), ("y", 0.9), ("z", 0.8)]
    b = [("y", 0.5), ("w", 0.4), ("x", 0.3)]
    fused = R._rrf_fuse([a, b], K=60)
    # Top fused ids should be those ranked high in BOTH lists.
    top_ids = [d for d, _ in fused[:3]]
    # 'y' is #2 in a and #1 in b; 'x' is #1 in a and #3 in b.
    # Both should be top-2 in fusion.
    assert "y" in top_ids[:2]
    assert "x" in top_ids[:2]


def test_rrf_preserves_unique_ids():
    from app.rag_provider import RAGProviderRegistry as R
    fused = R._rrf_fuse([[("a", 1), ("b", 0.5)], [("c", 1)]])
    ids = [d for d, _ in fused]
    assert set(ids) == {"a", "b", "c"}


def test_rrf_empty_lists_yield_empty():
    from app.rag_provider import RAGProviderRegistry as R
    assert R._rrf_fuse([]) == []
    assert R._rrf_fuse([[], []]) == []


# ── _bm25_search ────────────────────────────────────────


def test_bm25_empty_collection(registry):
    reg, _ = registry
    assert reg._bm25_search("c", "anything", top_k=10) == []


def test_bm25_scores_keyword_matches(registry):
    reg, coll = registry
    coll.upsert(
        ids=["a", "b", "c"],
        documents=[
            "terraform apply is dangerous in production",
            "the deploy pipeline uses github actions",
            "markdown is the preferred doc format",
        ],
        metadatas=[{}, {}, {}],
    )
    hits = reg._bm25_search("c", "terraform production", top_k=3)
    assert hits, "BM25 should find keyword matches"
    assert hits[0][0] == "a"   # strongest match


def test_bm25_handles_chinese_query(registry):
    reg, coll = registry
    coll.upsert(
        ids=["a", "b"],
        documents=[
            "云计算是一种通过网络提供资源的服务",
            "面条的做法很多种",
        ],
        metadatas=[{}, {}],
    )
    hits = reg._bm25_search("c", "云计算", top_k=2)
    assert hits
    assert hits[0][0] == "a"


def test_bm25_empty_query_returns_empty(registry):
    reg, coll = registry
    coll.upsert(ids=["a"], documents=["body"], metadatas=[{}])
    assert reg._bm25_search("c", "", top_k=5) == []


# ── hybrid_search ──────────────────────────────────────


def test_hybrid_returns_top_k(registry):
    reg, coll = registry
    for i in range(8):
        coll.upsert(
            ids=[f"d{i}"],
            documents=[f"document {i} about testing and pytest"],
            metadatas=[{"title": f"doc{i}"}],
        )
    out = reg.hybrid_search("", "c", "pytest testing", top_k=3)
    assert len(out) == 3
    # Each result has rrf_score attached.
    for r in out:
        assert "rrf_score" in (r.metadata or {})


def test_hybrid_falls_back_to_vector_when_bm25_empty(registry):
    reg, coll = registry
    # BM25 token = "random" won't match any doc (we use unrelated text).
    coll.upsert(
        ids=["d1"], documents=["some body text here"], metadatas=[{"title": "x"}]
    )
    # Query with no BM25-matchable token yet still similar via vector stub.
    out = reg.hybrid_search("", "c", "!?#", top_k=5)
    # Should not crash; result list may be empty or fall back to vector.
    assert isinstance(out, list)


def test_hybrid_prefers_keyword_hit(registry):
    reg, coll = registry
    coll.upsert(
        ids=["a", "b", "c"],
        documents=[
            "discussion of terraform apply risks in production",
            "a general note about markdown",
            "pytest fixtures and parametrized tests",
        ],
        metadatas=[{"title": "a"}, {"title": "b"}, {"title": "c"}],
    )
    out = reg.hybrid_search("", "c", "terraform apply", top_k=3)
    # The terraform doc should win despite vector stub's weak signal.
    assert out[0].id == "a"


def test_hybrid_empty_collection_empty_result(registry):
    reg, _ = registry
    out = reg.hybrid_search("", "empty", "some query", top_k=5)
    assert out == []
