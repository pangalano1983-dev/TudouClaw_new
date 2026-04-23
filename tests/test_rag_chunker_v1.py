"""RAG Enhancement Pack v1-A — recursive semantic chunker.

Covers:
  * Markdown heading-aware split (builds heading_path breadcrumb)
  * Paragraph-level split when section still > chunk_size
  * Sentence-level split inside oversized paragraph
  * Char-level slice for monster sentences (last resort)
  * 15% overlap between adjacent chunks
  * v1-C: content_hash / heading_path / source_file / chunk_index / imported_at
"""
from __future__ import annotations

import hashlib
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


from app.api.routers.knowledge import (  # noqa: E402
    _chunk_text_for_rag,
    _split_by_headings,
    _recursive_split,
    _apply_overlap,
)


# ── heading split ────────────────────────────────────────────


def test_heading_split_builds_breadcrumb():
    text = (
        "preamble line\n"
        "\n"
        "# 第一章\n"
        "\n"
        "chapter one body\n"
        "\n"
        "## 第二节\n"
        "\n"
        "section two body\n"
        "\n"
        "# 第二章\n"
        "\n"
        "chapter two body\n"
    )
    sections = _split_by_headings(text)
    # preamble + 3 titled sections
    assert len(sections) == 4
    paths = [p for p, _b in sections]
    assert paths[0] == ""
    assert paths[1] == "第一章"
    assert paths[2] == "第一章 / 第二节"
    assert paths[3] == "第二章"


def test_heading_split_no_headings_single_section():
    text = "just a flat paragraph with no headings at all."
    sections = _split_by_headings(text)
    assert len(sections) == 1
    assert sections[0][0] == ""


def test_heading_split_pops_lower_levels():
    text = (
        "# A\n\nbody A\n"
        "## A.1\n\nbody A.1\n"
        "### A.1.a\n\nbody A.1.a\n"
        "## A.2\n\nbody A.2\n"   # should pop A.1.a and A.1, keep A
        "# B\n\nbody B\n"         # should pop to root
    )
    sections = _split_by_headings(text)
    paths = [p for p, _b in sections]
    assert paths == ["A", "A / A.1", "A / A.1 / A.1.a", "A / A.2", "B"]


# ── recursive split ──────────────────────────────────────────


def test_recursive_split_short_returns_single():
    out = _recursive_split("short body", chunk_size=1000)
    assert out == ["short body"]


def test_recursive_split_by_paragraphs():
    body = "\n\n".join([f"paragraph {i} " + "X" * 300 for i in range(5)])
    out = _recursive_split(body, chunk_size=500)
    # Multiple chunks, each paragraph in its own chunk (since each > 300 chars).
    assert len(out) >= 3


def test_recursive_split_handles_oversized_paragraph():
    # Single paragraph with multiple sentences, way over chunk_size.
    body = ("Sentence one. " * 50 + "终端句。" * 20)
    out = _recursive_split(body, chunk_size=200)
    assert len(out) >= 3
    # Each chunk ≤ chunk_size (approximately).
    for c in out:
        assert len(c) <= 210, f"chunk overshot: {len(c)}"


def test_recursive_split_char_slice_on_monster_sentence():
    # A single "sentence" with no terminator and huge length.
    body = "X" * 5000
    out = _recursive_split(body, chunk_size=500)
    assert len(out) >= 10
    for c in out:
        assert len(c) <= 500


def test_recursive_split_empty_returns_empty():
    assert _recursive_split("", 1000) == []
    assert _recursive_split("   \n\n  ", 1000) == []


# ── overlap ─────────────────────────────────────────────────


def test_apply_overlap_adds_tail_of_previous():
    pieces = ["first " + "A" * 200, "second " + "B" * 200,
              "third " + "C" * 200]
    out = _apply_overlap(pieces, chunk_size=1000, ratio=0.15)
    assert len(out) == 3
    # First unchanged.
    assert out[0] == pieces[0]
    # Subsequent chunks have '…' prefix marker + tail of previous.
    assert out[1].startswith("…")
    assert "A" in out[1]     # tail of first's content
    assert "second" in out[1]


def test_apply_overlap_zero_ratio_returns_copy():
    pieces = ["a", "b", "c"]
    assert _apply_overlap(pieces, chunk_size=100, ratio=0.0) == pieces


def test_apply_overlap_single_piece_unchanged():
    assert _apply_overlap(["only"], chunk_size=100) == ["only"]


def test_apply_overlap_handles_short_prev():
    pieces = ["short", "later content here"]
    out = _apply_overlap(pieces, chunk_size=1000, ratio=0.15)
    # Overlap chars = 150 but prev is only 5 chars → whole prev reused.
    assert "short" in out[1]


# ── end-to-end _chunk_text_for_rag ───────────────────────────


def test_chunker_emits_heading_path_metadata():
    text = (
        "# 合同总则\n\n"
        "总则正文 " * 50 + "\n\n"
        "## 第一条\n\n"
        "第一条正文 " * 50 + "\n\n"
        "## 第二条\n\n"
        "第二条正文 " * 50 + "\n\n"
    )
    chunks = _chunk_text_for_rag(
        text, base_id="dkb_x", base_title="合同法",
        tags=["legal"], chunk_size=500,
    )
    # Each chunk carries heading_path metadata.
    paths = {c["heading_path"] for c in chunks}
    assert "合同总则" in paths
    # Deep subsection path exists.
    assert "合同总则 / 第一条" in paths or "合同总则 / 第二条" in paths


def test_chunker_adds_content_hash_and_dedup_hash_uniqueness():
    text = "unique content for testing purposes " * 30
    c1 = _chunk_text_for_rag(text, "id1", "t", [], chunk_size=200)
    c2 = _chunk_text_for_rag(text, "id2", "t", [], chunk_size=200)
    # Same text → same content_hashes, same quantity.
    h1 = [c["content_hash"] for c in c1]
    h2 = [c["content_hash"] for c in c2]
    assert h1 == h2
    # And hashes are sha256 = 64 hex chars.
    assert all(len(h) == 64 for h in h1)


def test_chunker_source_file_and_chunk_index():
    text = "a " * 50 + "\n\n" + "b " * 50 + "\n\n" + "c " * 50
    chunks = _chunk_text_for_rag(
        text, "base", "doc", [], chunk_size=80,
        source_file="docs/foo.md",
    )
    # chunk_index monotonic from 1.
    assert all(c["source_file"] == "docs/foo.md" for c in chunks)
    assert [c["chunk_index"] for c in chunks] == list(
        range(1, len(chunks) + 1))


def test_chunker_empty_text_returns_empty():
    assert _chunk_text_for_rag("", "id", "t", [], chunk_size=500) == []
    assert _chunk_text_for_rag("   \n\n", "id", "t", [], chunk_size=500) == []


def test_chunker_tags_propagate():
    text = "\n\n".join(["body " * 30 for _ in range(3)])
    chunks = _chunk_text_for_rag(
        text, "id", "t", ["legal", "compliance"], chunk_size=100,
    )
    for c in chunks:
        assert "legal" in c["tags"]
        assert "compliance" in c["tags"]


def test_chunker_ids_are_unique_and_ordered():
    text = "\n\n".join(["x" * 100 for _ in range(5)])
    chunks = _chunk_text_for_rag(
        text, "base", "t", [], chunk_size=80)
    ids = [c["id"] for c in chunks]
    assert len(set(ids)) == len(ids)
    # Sorted lexicographically matches insertion order (0001, 0002, ...)
    assert ids == sorted(ids)


def test_chunker_imported_at_is_timestamp():
    import time
    before = time.time()
    chunks = _chunk_text_for_rag("body text here " * 10, "b", "t", [],
                                  chunk_size=500)
    after = time.time()
    assert chunks
    assert all(before <= c["imported_at"] <= after for c in chunks)


def test_chunker_real_world_doc_smoke():
    """Realistic mixed Chinese/English document — no crashes, valid shape."""
    doc = """# Product Spec: LoginFlow

## Overview

This spec describes the login flow for our application.
It covers both password and OAuth paths.

## Authentication Methods

### Password Auth

Users enter username + password. System checks bcrypt hash.

### OAuth (Google / GitHub)

Users click the provider button. We redirect to OAuth consent,
then exchange code for token.

## Security Considerations

- Rate limiting: 5 attempts per minute.
- Password requirements: 8+ chars, 1 number, 1 symbol.
- Session expiry: 24 hours.

## 验收标准

完成以下任务即视为完成：
1. 用户可通过密码登录
2. 用户可通过 OAuth 登录
3. 所有安全要求通过审计
"""
    chunks = _chunk_text_for_rag(doc, "prod", "LoginFlow spec",
                                  ["eng", "login"], chunk_size=400)
    assert len(chunks) >= 3
    # All required metadata present on every chunk.
    for c in chunks:
        for key in ("id", "title", "content", "tags", "source",
                    "content_hash", "heading_path", "source_file",
                    "chunk_index", "imported_at"):
            assert key in c, f"missing {key}"
