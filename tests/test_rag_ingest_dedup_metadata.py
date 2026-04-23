"""RAG v1-C — _ingest_local persists new metadata + dedups by content_hash.

Verifies:
  * content_hash / heading_path / source_file / chunk_index /
    imported_at are written into ChromaDB metadata
  * Re-ingesting the same content_hash is a no-op (skipped)
  * Non-hashed docs (legacy) still ingest fine
  * Search results surface the metadata
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


class _FakeCollection:
    """In-memory ChromaDB-ish collection for testing."""

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

    def get(self, include=None):
        include = include or []
        out = {"ids": list(self._ids)}
        if "metadatas" in include:
            out["metadatas"] = list(self._metas)
        if "documents" in include:
            out["documents"] = list(self._docs)
        return out

    def query(self, query_texts, n_results):
        # Naive: return first n_results in insertion order with fake distance.
        n = min(n_results, len(self._ids))
        return {
            "ids": [self._ids[:n]],
            "documents": [self._docs[:n]],
            "metadatas": [self._metas[:n]],
            "distances": [[0.1 * i for i in range(n)]],
        }


@pytest.fixture
def registry_with_fake_chroma(tmp_path, monkeypatch):
    """Build a RagRegistry where MemoryManager's chroma_collection is
    replaced by our _FakeCollection."""
    fake_coll = _FakeCollection()

    class _FakeMM:
        def __init__(self):
            pass

        def _get_chroma_collection(self, name):
            return fake_coll

    import app.rag_provider as rp
    reg = rp.RAGProviderRegistry.__new__(rp.RAGProviderRegistry)
    # Bypass the usual heavy init.
    reg._providers = {}
    reg._loaded = True
    reg._get_memory_manager = lambda: _FakeMM()

    yield reg, fake_coll


# ── metadata persistence ─────────────────────────────────────


def test_all_new_metadata_fields_persisted(registry_with_fake_chroma):
    reg, coll = registry_with_fake_chroma
    docs = [{
        "id": "c1",
        "title": "Chapter 1",
        "content": "The body of chapter 1.",
        "tags": ["legal"],
        "source": "upload",
        "content_hash": "abc123",
        "heading_path": "Part A / Chapter 1",
        "source_file": "docs/foo.md",
        "chunk_index": 1,
        "imported_at": 1700000000.0,
    }]
    n = reg._ingest_local("col", docs)
    assert n == 1
    assert len(coll._metas) == 1
    m = coll._metas[0]
    assert m["content_hash"] == "abc123"
    assert m["heading_path"] == "Part A / Chapter 1"
    assert m["source_file"] == "docs/foo.md"
    assert m["chunk_index"] == 1
    assert m["imported_at"] == 1700000000.0
    # Legacy fields still present.
    assert m["title"] == "Chapter 1"
    assert "legal" in m["tags"]
    assert m["source"] == "upload"


def test_legacy_docs_without_new_fields_still_ingest(registry_with_fake_chroma):
    reg, coll = registry_with_fake_chroma
    docs = [{"id": "a", "title": "old", "content": "stuff"}]
    n = reg._ingest_local("col", docs)
    assert n == 1
    # New fields omitted — metadata still has title + source + created_at.
    m = coll._metas[0]
    assert "title" in m
    assert "created_at" in m
    # But no empty v1-C fields.
    assert "content_hash" not in m
    assert "heading_path" not in m


def test_empty_content_skipped(registry_with_fake_chroma):
    reg, coll = registry_with_fake_chroma
    docs = [
        {"id": "x", "title": "x", "content": ""},
        {"id": "y", "title": "y", "content": "real"},
    ]
    n = reg._ingest_local("col", docs)
    assert n == 1
    assert coll._ids == ["y"]


# ── content_hash dedup ──────────────────────────────────────


def test_dedup_by_content_hash_across_requests(registry_with_fake_chroma):
    reg, coll = registry_with_fake_chroma

    # First request.
    docs1 = [
        {"id": "c_v1_a", "title": "A", "content": "text A",
         "content_hash": "hash_A"},
        {"id": "c_v1_b", "title": "B", "content": "text B",
         "content_hash": "hash_B"},
    ]
    n1 = reg._ingest_local("col", docs1)
    assert n1 == 2
    assert coll.count() == 2

    # Second request re-imports same content (different IDs, same hash).
    docs2 = [
        {"id": "c_v2_a", "title": "A (re)", "content": "text A",
         "content_hash": "hash_A"},     # duplicate
        {"id": "c_v2_c", "title": "C", "content": "text C",
         "content_hash": "hash_C"},     # new
    ]
    n2 = reg._ingest_local("col", docs2)
    # hash_A skipped; hash_C ingested.
    assert n2 == 1
    assert coll.count() == 3
    # hash_A is still the v1 id (not re-upserted with the v2 id).
    hashes = [m.get("content_hash") for m in coll._metas]
    assert hashes.count("hash_A") == 1


def test_no_hash_allows_duplicate_by_id_upsert_semantics(registry_with_fake_chroma):
    """If a doc has NO content_hash, dedup can't fire; upsert-by-id
    still protects against same-ID duplicates."""
    reg, coll = registry_with_fake_chroma

    # Same ID → upserted (overwritten).
    reg._ingest_local("col", [{"id": "same", "content": "v1"}])
    reg._ingest_local("col", [{"id": "same", "content": "v2"}])
    assert coll.count() == 1
    assert "v2" in coll._docs[0]


def test_same_hash_within_single_request_skipped(registry_with_fake_chroma):
    """Within a request, once we've seen a hash we skip further dupes."""
    reg, coll = registry_with_fake_chroma
    docs = [
        {"id": "a", "content": "body", "content_hash": "h1"},
        {"id": "b", "content": "body", "content_hash": "h1"},   # dup
        {"id": "c", "content": "body", "content_hash": "h2"},
    ]
    n = reg._ingest_local("col", docs)
    assert n == 2
    assert coll.count() == 2


# ── search surfaces metadata ───────────────────────────────


def test_search_returns_v1c_metadata(registry_with_fake_chroma):
    reg, coll = registry_with_fake_chroma
    reg._ingest_local("col", [{
        "id": "d1", "title": "t", "content": "body of d1",
        "content_hash": "h1", "heading_path": "Chapter / Section",
        "source_file": "docs/foo.md", "chunk_index": 3,
    }])
    results = reg._search_local("col", "body", top_k=5)
    assert len(results) == 1
    meta = results[0].metadata
    assert meta["heading_path"] == "Chapter / Section"
    assert meta["source_file"] == "docs/foo.md"
    assert meta["chunk_index"] == 3
    assert meta["content_hash"] == "h1"
