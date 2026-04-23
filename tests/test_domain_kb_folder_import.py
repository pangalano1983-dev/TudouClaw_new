"""Folder import into domain KB.

Contract:
  * Walks a server-local folder, parses each file, chunks, ingests once.
  * Obeys recursive / extensions allowlist / max_files / max_file_size_mb.
  * Returns per-file breakdown + skipped reasons.
  * Refuses missing/invalid kb_id / folder.
"""
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


@pytest.fixture
def fresh_store(tmp_path, monkeypatch):
    """Fresh in-memory domain KB store pointing at tmp files."""
    monkeypatch.setenv("TUDOU_CLAW_DATA_DIR", str(tmp_path))
    import app.rag_provider as rp
    monkeypatch.setattr(rp, "_DOMAIN_KB_FILE", tmp_path / "domain_kb.json")
    monkeypatch.setattr(rp, "_domain_kb_store_singleton", None,
                        raising=False)
    store = rp.get_domain_kb_store()
    # Pre-create a KB.
    kb = store.create(name="test-kb", description="test", provider_id="")
    yield store, kb
    monkeypatch.setattr(rp, "_domain_kb_store_singleton", None,
                        raising=False)


@pytest.fixture
def client(fresh_store, monkeypatch):
    store, kb = fresh_store

    # Stub the RAG registry's ingest — we don't actually want to create
    # real vector collections in a unit test. Observe the call.
    import app.rag_provider as rp
    observed = {"calls": []}

    class _StubRAG:
        def ingest(self, provider_id, collection, chunks):
            observed["calls"].append({
                "provider_id": provider_id,
                "collection": collection,
                "n_chunks": len(chunks),
            })
            return len(chunks)

        def create_collection(self, provider_id, name):
            return True

    monkeypatch.setattr(rp, "get_rag_registry", lambda: _StubRAG())

    from app.api.deps.auth import get_current_user, CurrentUser

    async def _fake_user():
        return CurrentUser(user_id="u", role="superAdmin")

    from app.api.routers import knowledge as kn_router

    app = FastAPI()
    app.dependency_overrides[get_current_user] = _fake_user
    from app.api.deps.hub import get_hub as _get_hub
    app.dependency_overrides[_get_hub] = lambda: object()
    app.include_router(kn_router.router)

    with TestClient(app) as tc:
        tc.store = store
        tc.kb = kb
        tc.observed = observed
        yield tc


# ── happy path: flat folder, 3 files ─────────────────────────


def test_import_flat_folder(client, tmp_path):
    folder = tmp_path / "docs"
    folder.mkdir()
    (folder / "a.md").write_text("# Heading A\n\nbody a " * 50, encoding="utf-8")
    (folder / "b.txt").write_text("text B " * 100, encoding="utf-8")
    (folder / "c.md").write_text("content C " * 80, encoding="utf-8")

    r = client.post("/api/portal/domain-kb/import-folder", json={
        "kb_id": client.kb.id,
        "folder": str(folder),
        "recursive": False,
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] is True
    assert d["files_scanned"] == 3
    assert d["files_imported"] == 3
    assert d["chunks_total"] > 0
    assert d["ingest_count"] > 0
    assert len(d["by_file"]) == 3
    # ingest called once with all chunks.
    assert len(client.observed["calls"]) == 1
    assert client.observed["calls"][0]["n_chunks"] == d["chunks_total"]


# ── recursive vs flat ────────────────────────────────────────


def test_recursive_walks_subfolders(client, tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "top.md").write_text("top " * 30, encoding="utf-8")
    sub = root / "sub"
    sub.mkdir()
    (sub / "deep.md").write_text("deep " * 30, encoding="utf-8")

    r = client.post("/api/portal/domain-kb/import-folder", json={
        "kb_id": client.kb.id,
        "folder": str(root),
        "recursive": True,
    })
    d = r.json()
    assert d["files_imported"] == 2
    paths = [b["relative_path"] for b in d["by_file"]]
    assert "top.md" in paths
    assert os.path.join("sub", "deep.md") in paths


def test_non_recursive_skips_subfolders(client, tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "top.md").write_text("top " * 30, encoding="utf-8")
    sub = root / "sub"
    sub.mkdir()
    (sub / "deep.md").write_text("deep " * 30, encoding="utf-8")

    r = client.post("/api/portal/domain-kb/import-folder", json={
        "kb_id": client.kb.id,
        "folder": str(root),
        "recursive": False,
    })
    d = r.json()
    assert d["files_imported"] == 1
    assert d["by_file"][0]["relative_path"] == "top.md"


# ── extension allowlist ──────────────────────────────────────


def test_extension_allowlist_filters(client, tmp_path):
    folder = tmp_path / "mixed"
    folder.mkdir()
    (folder / "keep.md").write_text("a " * 30)
    (folder / "skip.xyz").write_text("b " * 30)
    (folder / "skip.bin").write_bytes(b"\x00\x01\x02" * 100)

    r = client.post("/api/portal/domain-kb/import-folder", json={
        "kb_id": client.kb.id,
        "folder": str(folder),
        "extensions": ["md", "txt"],
    })
    d = r.json()
    assert d["files_imported"] == 1
    assert d["files_skipped"] == 2
    reasons = [s["reason"] for s in d["skipped"]]
    assert all("extension_" in r for r in reasons)


def test_extensions_tolerate_leading_dot_and_case(client, tmp_path):
    folder = tmp_path / "folder"
    folder.mkdir()
    (folder / "file.MD").write_text("x " * 30)
    (folder / "other.TXT").write_text("y " * 30)

    r = client.post("/api/portal/domain-kb/import-folder", json={
        "kb_id": client.kb.id,
        "folder": str(folder),
        "extensions": [".md", "TXT"],
    })
    assert r.json()["files_imported"] == 2


# ── size / count limits ──────────────────────────────────────


def test_max_file_size_skipped(client, tmp_path):
    folder = tmp_path / "sz"
    folder.mkdir()
    big = "x" * (3 * 1024 * 1024)
    (folder / "big.txt").write_text(big)
    (folder / "small.txt").write_text("ok " * 10)

    r = client.post("/api/portal/domain-kb/import-folder", json={
        "kb_id": client.kb.id,
        "folder": str(folder),
        "max_file_size_mb": 1,
    })
    d = r.json()
    assert d["files_imported"] == 1
    skipped_reasons = " ".join(s["reason"] for s in d["skipped"])
    assert "too_large" in skipped_reasons


def test_max_files_cap(client, tmp_path):
    folder = tmp_path / "many"
    folder.mkdir()
    for i in range(6):
        (folder / f"f{i}.md").write_text("x " * 20)

    r = client.post("/api/portal/domain-kb/import-folder", json={
        "kb_id": client.kb.id,
        "folder": str(folder),
        "max_files": 3,
    })
    d = r.json()
    assert d["files_imported"] == 3
    assert any("max_files_cap_reached" in s["reason"] for s in d["skipped"])


# ── edge cases ───────────────────────────────────────────────


def test_missing_kb_returns_404(client, tmp_path):
    folder = tmp_path / "a"
    folder.mkdir()
    r = client.post("/api/portal/domain-kb/import-folder", json={
        "kb_id": "does-not-exist", "folder": str(folder),
    })
    assert r.status_code == 404


def test_missing_folder_returns_400(client):
    r = client.post("/api/portal/domain-kb/import-folder", json={
        "kb_id": client.kb.id,
        "folder": "/nope/definitely/does/not/exist",
    })
    assert r.status_code == 400


def test_empty_kb_id_400(client, tmp_path):
    r = client.post("/api/portal/domain-kb/import-folder", json={
        "folder": str(tmp_path),
    })
    assert r.status_code == 400


def test_empty_folder_returns_400(client):
    r = client.post("/api/portal/domain-kb/import-folder", json={
        "kb_id": client.kb.id,
    })
    assert r.status_code == 400


def test_empty_file_skipped(client, tmp_path):
    folder = tmp_path / "x"
    folder.mkdir()
    (folder / "empty.md").write_text("")
    (folder / "ok.md").write_text("real content " * 20)

    r = client.post("/api/portal/domain-kb/import-folder", json={
        "kb_id": client.kb.id,
        "folder": str(folder),
    })
    d = r.json()
    assert d["files_imported"] == 1
    assert any(s["reason"] == "empty" for s in d["skipped"])


def test_folder_all_skipped_returns_zero_ingest(client, tmp_path):
    folder = tmp_path / "x"
    folder.mkdir()
    (folder / "skip.unknownext").write_text("data")

    r = client.post("/api/portal/domain-kb/import-folder", json={
        "kb_id": client.kb.id,
        "folder": str(folder),
        "extensions": ["md"],
    })
    d = r.json()
    assert d["files_imported"] == 0
    assert d["chunks_total"] == 0
    # Ingest NOT called when no chunks.
    assert len(client.observed["calls"]) == 0


# ── chunking sanity ──────────────────────────────────────────


def test_large_file_gets_multiple_chunks(client, tmp_path):
    folder = tmp_path / "big"
    folder.mkdir()
    # Produce paragraphs that will exceed chunk_size cleanly.
    paragraphs = ["paragraph %d content " % i + ("X" * 200) for i in range(10)]
    (folder / "long.md").write_text("\n\n".join(paragraphs),
                                    encoding="utf-8")

    r = client.post("/api/portal/domain-kb/import-folder", json={
        "kb_id": client.kb.id,
        "folder": str(folder),
        "chunk_size": 500,
    })
    d = r.json()
    assert d["files_imported"] == 1
    assert d["chunks_total"] > 1   # split into multiple chunks


def test_tags_propagate_into_chunks(client, tmp_path, monkeypatch):
    """Chunks must carry the tags the user passed in."""
    folder = tmp_path / "t"
    folder.mkdir()
    (folder / "one.md").write_text("content x " * 30, encoding="utf-8")

    # Capture actual ingested chunks.
    captured = {"chunks": None}

    import app.rag_provider as rp

    class _CapturingRAG:
        def ingest(self, pid, col, chunks):
            captured["chunks"] = list(chunks)
            return len(chunks)

        def create_collection(self, pid, name):
            return True

    monkeypatch.setattr(rp, "get_rag_registry", lambda: _CapturingRAG())

    r = client.post("/api/portal/domain-kb/import-folder", json={
        "kb_id": client.kb.id,
        "folder": str(folder),
        "tags": ["legal", "compliance"],
    })
    assert r.status_code == 200
    chunks = captured["chunks"]
    assert chunks, "ingest didn't capture anything"
    for c in chunks:
        assert "legal" in c["tags"]
        assert "compliance" in c["tags"]
        # Source is annotated with the relative path.
        assert c["source"].startswith("domain_import_folder:")


def test_doc_count_incremented(client, tmp_path):
    folder = tmp_path / "dc"
    folder.mkdir()
    (folder / "one.md").write_text("x " * 30)
    (folder / "two.md").write_text("y " * 30)

    before = client.store.get(client.kb.id).doc_count
    r = client.post("/api/portal/domain-kb/import-folder", json={
        "kb_id": client.kb.id,
        "folder": str(folder),
    })
    d = r.json()
    after = client.store.get(client.kb.id).doc_count
    assert after == before + d["chunks_total"]
