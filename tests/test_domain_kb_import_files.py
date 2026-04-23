"""Browser-upload folder import — /domain-kb/import-files.

Accepts client-enumerated files (base64) so user can browse local
folder from the browser instead of typing a server path.
"""
from __future__ import annotations

import base64
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
def fresh_store(tmp_path, monkeypatch):
    monkeypatch.setenv("TUDOU_CLAW_DATA_DIR", str(tmp_path))
    import app.rag_provider as rp
    monkeypatch.setattr(rp, "_DOMAIN_KB_FILE", tmp_path / "dkb.json")
    monkeypatch.setattr(rp, "_domain_kb_store_singleton", None,
                        raising=False)
    store = rp.get_domain_kb_store()
    kb = store.create(name="upload-test", provider_id="")
    yield store, kb


@pytest.fixture
def client(fresh_store, monkeypatch):
    store, kb = fresh_store

    import app.rag_provider as rp
    observed = {"calls": []}

    class _StubRAG:
        def ingest(self, provider_id, collection, chunks):
            observed["calls"].append({
                "provider_id": provider_id,
                "collection": collection,
                "chunks": chunks,
            })
            return len(chunks)

        def create_collection(self, provider_id, name):
            return True

    monkeypatch.setattr(rp, "get_rag_registry", lambda: _StubRAG())

    from app.api.deps.auth import get_current_user, CurrentUser

    async def _fake_user():
        return CurrentUser(user_id="u", role="superAdmin")

    from app.api.deps.hub import get_hub as _get_hub
    from app.api.routers import knowledge as kn_router

    app = FastAPI()
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[_get_hub] = lambda: object()
    app.include_router(kn_router.router)
    with TestClient(app) as tc:
        tc.store = store
        tc.kb = kb
        tc.observed = observed
        yield tc


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


# ── happy path ─────────────────────────────────────────────


def test_upload_single_md_file(client):
    r = client.post("/api/portal/domain-kb/import-files", json={
        "kb_id": client.kb.id,
        "files": [
            {"name": "doc.md", "data_base64": _b64("# Heading\n\nbody " * 50)}
        ],
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["files_scanned"] == 1
    assert d["files_imported"] == 1
    assert d["chunks_total"] >= 1
    # Ingest called once with chunks.
    assert len(client.observed["calls"]) == 1


def test_upload_multiple_files(client):
    files = []
    for i in range(5):
        files.append({
            "name": f"sub/doc_{i}.md",
            "data_base64": _b64(f"file {i} body " * 30),
        })
    r = client.post("/api/portal/domain-kb/import-files", json={
        "kb_id": client.kb.id, "files": files,
    })
    d = r.json()
    assert d["files_imported"] == 5
    # each chunk carries the uploaded name as source_file
    sent = client.observed["calls"][0]["chunks"]
    names = {c["source_file"] for c in sent}
    for i in range(5):
        assert f"sub/doc_{i}.md" in names


def test_folder_structure_preserved_via_name(client):
    """Client sends `name` as the relative path from the folder root;
    the backend uses it verbatim as the chunk's source_file."""
    r = client.post("/api/portal/domain-kb/import-files", json={
        "kb_id": client.kb.id,
        "files": [
            {"name": "chapter1/section1.md",
             "data_base64": _b64("body " * 30)},
        ],
    })
    assert r.status_code == 200
    sent = client.observed["calls"][0]["chunks"]
    assert sent[0]["source_file"] == "chapter1/section1.md"


def test_tags_applied(client):
    r = client.post("/api/portal/domain-kb/import-files", json={
        "kb_id": client.kb.id,
        "files": [{"name": "a.md", "data_base64": _b64("content " * 30)}],
        "tags": ["legal", "2026"],
    })
    sent = client.observed["calls"][0]["chunks"]
    assert "legal" in sent[0]["tags"]
    assert "2026" in sent[0]["tags"]


# ── skip reasons ───────────────────────────────────────────


def test_oversized_file_skipped(client):
    big = "X" * (3 * 1024 * 1024)
    r = client.post("/api/portal/domain-kb/import-files", json={
        "kb_id": client.kb.id,
        "files": [{"name": "big.txt", "data_base64": _b64(big)}],
        "max_file_size_mb": 1,
    })
    d = r.json()
    assert d["files_imported"] == 0
    assert any("too_large" in s["reason"] for s in d["skipped"])


def test_empty_data_skipped(client):
    r = client.post("/api/portal/domain-kb/import-files", json={
        "kb_id": client.kb.id,
        "files": [
            {"name": "empty.md", "data_base64": ""},
            {"name": "ok.md", "data_base64": _b64("real content " * 20)},
        ],
    })
    d = r.json()
    assert d["files_imported"] == 1
    assert any(s["reason"] == "empty_data" for s in d["skipped"])


def test_missing_name_skipped(client):
    r = client.post("/api/portal/domain-kb/import-files", json={
        "kb_id": client.kb.id,
        "files": [
            {"data_base64": _b64("content")},
            {"name": "ok.md", "data_base64": _b64("x " * 30)},
        ],
    })
    d = r.json()
    assert d["files_imported"] == 1
    assert any(s["reason"] == "missing_name" for s in d["skipped"])


def test_bad_base64_skipped(client):
    r = client.post("/api/portal/domain-kb/import-files", json={
        "kb_id": client.kb.id,
        "files": [
            {"name": "bad.md", "data_base64": "$$$not-base64$$$"},
            {"name": "ok.md", "data_base64": _b64("x " * 30)},
        ],
    })
    d = r.json()
    assert d["files_imported"] == 1
    reasons = [s["reason"] for s in d["skipped"]]
    assert any("base64" in r or "empty" in r for r in reasons)


# ── dedup within request ─────────────────────────────────


def test_duplicate_content_deduped_within_request(client):
    same = "identical body text " * 30
    r = client.post("/api/portal/domain-kb/import-files", json={
        "kb_id": client.kb.id,
        "files": [
            {"name": "a.md", "data_base64": _b64(same)},
            {"name": "b.md", "data_base64": _b64(same)},
        ],
    })
    d = r.json()
    assert d["files_imported"] == 2
    # But dedup ran at the chunk level so same-content chunks collapse.
    assert d["chunks_deduped"] > 0
    ingest_count = client.observed["calls"][0]["chunks"]
    # Only one copy of each unique hash.
    hashes = [c["content_hash"] for c in ingest_count]
    assert len(hashes) == len(set(hashes))


# ── edge cases ────────────────────────────────────────────


def test_missing_kb_404(client):
    r = client.post("/api/portal/domain-kb/import-files", json={
        "kb_id": "nope",
        "files": [{"name": "x.md", "data_base64": _b64("a")}],
    })
    assert r.status_code == 404


def test_empty_kb_id_400(client):
    r = client.post("/api/portal/domain-kb/import-files", json={
        "files": [{"name": "x.md", "data_base64": _b64("a")}],
    })
    assert r.status_code == 400


def test_empty_files_list_400(client):
    r = client.post("/api/portal/domain-kb/import-files", json={
        "kb_id": client.kb.id, "files": [],
    })
    assert r.status_code == 400


def test_files_not_a_list_400(client):
    r = client.post("/api/portal/domain-kb/import-files", json={
        "kb_id": client.kb.id, "files": "not a list",
    })
    assert r.status_code == 400


def test_pdf_like_bytes_parsed(client):
    """Verify the shared _parse_file_bytes_to_text helper fires
    appropriately based on extension. For .txt this is a raw decode."""
    r = client.post("/api/portal/domain-kb/import-files", json={
        "kb_id": client.kb.id,
        "files": [
            {"name": "foo.txt",
             "data_base64": _b64("hello world content " * 20)},
        ],
    })
    d = r.json()
    assert d["files_imported"] == 1
    sent = client.observed["calls"][0]["chunks"]
    assert "hello world" in sent[0]["content"]
