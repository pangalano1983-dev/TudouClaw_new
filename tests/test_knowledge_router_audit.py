"""Regression audit — 5 knowledge-router endpoints that were silent-no-ops.

Bugs (all 5 had the same pattern):
  POST /knowledge                 — called non-existent get_knowledge_manager
  POST /knowledge/{id}            — ditto
  POST /knowledge/{id}/delete     — ditto
  POST /rag/search                — checked hasattr(hub, 'search_rag') → always False
  POST /rag/ingest                — checked hasattr(hub, 'ingest_rag_documents') → always False

All returned fake success (empty stubs or ok=True). Now routed through
the real module APIs.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Isolate the knowledge store file and RAG registry."""
    monkeypatch.setenv("TUDOU_CLAW_DATA_DIR", str(tmp_path))
    # knowledge.py module-level state: it caches entries in memory.
    # Force a reload so it picks up tmp dir.
    import importlib
    import app.knowledge as _kb
    importlib.reload(_kb)

    # Stub RAG registry.
    import app.rag_provider as rp

    observed = {"search_calls": [], "ingest_calls": []}

    class _StubRAG:
        def search(self, provider_id, collection, query, top_k=5):
            observed["search_calls"].append({
                "provider_id": provider_id,
                "collection": collection,
                "query": query, "top_k": top_k,
            })
            # Return deterministic fake results.
            from app.rag_provider import RAGResult
            return [
                RAGResult(id=f"r{i}", title=f"hit {i}",
                          content=f"body {i}", distance=0.1 * i)
                for i in range(min(top_k, 2))
            ]

        def ingest(self, provider_id, collection, documents):
            observed["ingest_calls"].append({
                "provider_id": provider_id,
                "collection": collection,
                "documents": list(documents or []),
            })
            return len(documents or [])

    monkeypatch.setattr(rp, "get_rag_registry", lambda: _StubRAG())

    # Minimal FastAPI app.
    from app.api.deps.auth import get_current_user, CurrentUser
    from app.api.deps.hub import get_hub as _get_hub

    async def _fake_user():
        return CurrentUser(user_id="u", role="superAdmin")

    from app.api.routers import knowledge as kn_router
    app = FastAPI()
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[_get_hub] = lambda: object()
    app.include_router(kn_router.router)
    with TestClient(app) as tc:
        tc.kb_module = _kb
        tc.observed = observed
        yield tc


# ── /knowledge POST (add_entry) ──────────────────────────


def test_add_knowledge_entry_persists(client):
    r = client.post("/api/portal/knowledge", json={
        "title": "Python style guide",
        "content": "Use 4 spaces.",
        "tags": ["python", "style"],
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] is True
    entry = d["entry"]
    assert entry["title"] == "Python style guide"
    assert entry["content"] == "Use 4 spaces."
    assert entry["tags"] == ["python", "style"]
    # It's actually in the store.
    stored = client.kb_module.list_entries()
    assert any(e["id"] == entry["id"] for e in stored)


def test_add_knowledge_missing_title_400(client):
    r = client.post("/api/portal/knowledge",
                    json={"content": "body"})
    assert r.status_code == 400


def test_add_knowledge_missing_content_400(client):
    r = client.post("/api/portal/knowledge",
                    json={"title": "t"})
    assert r.status_code == 400


def test_add_knowledge_tags_non_list_defaults(client):
    r = client.post("/api/portal/knowledge", json={
        "title": "X", "content": "Y", "tags": "not a list",
    })
    assert r.status_code == 200
    assert r.json()["entry"]["tags"] == []


# ── /knowledge/{id} POST (update_entry) ──────────────────


def test_update_knowledge_entry(client):
    r1 = client.post("/api/portal/knowledge", json={
        "title": "Original", "content": "orig",
    })
    eid = r1.json()["entry"]["id"]
    r2 = client.post(f"/api/portal/knowledge/{eid}", json={
        "title": "Updated", "tags": ["new"],
    })
    assert r2.status_code == 200
    d = r2.json()
    assert d["ok"] is True
    assert d["entry"]["title"] == "Updated"
    assert d["entry"]["tags"] == ["new"]


def test_update_nonexistent_returns_404(client):
    r = client.post("/api/portal/knowledge/does-not-exist", json={
        "title": "X",
    })
    assert r.status_code == 404


# ── /knowledge/{id}/delete ───────────────────────────────


def test_delete_knowledge_entry(client):
    r1 = client.post("/api/portal/knowledge", json={
        "title": "To delete", "content": "body",
    })
    eid = r1.json()["entry"]["id"]
    r2 = client.post(f"/api/portal/knowledge/{eid}/delete")
    assert r2.status_code == 200
    assert r2.json()["ok"] is True
    # Actually removed from store.
    assert not any(e["id"] == eid for e in client.kb_module.list_entries())


def test_delete_nonexistent_returns_404(client):
    r = client.post("/api/portal/knowledge/nope/delete")
    assert r.status_code == 404


# ── /rag/search ──────────────────────────────────────────


def test_rag_search_routes_to_registry(client):
    r = client.post("/api/portal/rag/search", json={
        "query": "cloud computing trends",
        "provider": "local",
        "collection": "my_collection",
        "limit": 3,
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] is True
    # Stub RAG returned 2 results (capped at min(top_k, 2)).
    assert d["count"] == 2
    # Registry received the call.
    assert len(client.observed["search_calls"]) == 1
    call = client.observed["search_calls"][0]
    assert call["query"] == "cloud computing trends"
    assert call["collection"] == "my_collection"
    assert call["top_k"] == 3


def test_rag_search_missing_query_400(client):
    r = client.post("/api/portal/rag/search", json={
        "collection": "c",
    })
    assert r.status_code == 400


def test_rag_search_missing_collection_400(client):
    r = client.post("/api/portal/rag/search", json={
        "query": "x",
    })
    assert r.status_code == 400


# ── /rag/ingest ──────────────────────────────────────────


def test_rag_ingest_routes_to_registry(client):
    docs = [
        {"id": "d1", "title": "doc1", "content": "body 1"},
        {"id": "d2", "title": "doc2", "content": "body 2"},
    ]
    r = client.post("/api/portal/rag/ingest", json={
        "provider": "local", "collection": "c1", "documents": docs,
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] is True
    assert d["ingested"] == 2
    assert d["requested"] == 2
    # Registry got the docs.
    assert len(client.observed["ingest_calls"]) == 1
    assert client.observed["ingest_calls"][0]["collection"] == "c1"
    assert len(client.observed["ingest_calls"][0]["documents"]) == 2


def test_rag_ingest_empty_documents_400(client):
    r = client.post("/api/portal/rag/ingest", json={
        "collection": "c", "documents": [],
    })
    assert r.status_code == 400


def test_rag_ingest_missing_collection_400(client):
    r = client.post("/api/portal/rag/ingest", json={
        "documents": [{"id": "x", "content": "y"}],
    })
    assert r.status_code == 400


def test_rag_ingest_docs_not_a_list_400(client):
    r = client.post("/api/portal/rag/ingest", json={
        "collection": "c", "documents": "not a list",
    })
    assert r.status_code == 400


# ── cross-endpoint flow: add then search (vector sync is best-effort) ──


def test_knowledge_wiki_add_then_readback_via_list(client):
    for t in ["A", "B", "C"]:
        client.post("/api/portal/knowledge", json={
            "title": t, "content": f"body of {t}",
        })
    titles = [e["title"] for e in client.kb_module.list_entries()]
    assert "A" in titles
    assert "B" in titles
    assert "C" in titles
