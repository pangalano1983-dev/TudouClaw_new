"""Pack v2 — knowledge_lookup returns content+citation instead of partial index.

Before Pack v2: RAG hits were stripped of content and served only as a
title/id list ("status: partial, use entry_id for full content"). That
list was useless because entry_id resolved against the legacy FTS5 store,
which has no RAG chunk ids.

After Pack v2:
  * RAG hits go into `entries` with full content + citation metadata
    (source_file / heading_path / chunk_index), status=success.
  * Each chunk truncated at _MAX_CHUNK_CHARS_PER_HIT.
  * `usage_guidance` attaches citation + anti-fabrication rules.
  * `_RAG_TOP_K` raised 5 → 8.
  * Shared-pool legacy partial flow preserved for title-only entries.
"""
from __future__ import annotations

import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ── constants ──────────────────────────────────────────────────────

def test_top_k_raised_to_eight():
    from app.tools_split import knowledge as kn
    assert kn._RAG_TOP_K == 8


def test_max_chunk_chars_cap_exists():
    from app.tools_split import knowledge as kn
    assert kn._MAX_CHUNK_CHARS_PER_HIT == 1500


# ── RAG hit returns content + citation (not partial) ──────────────


def _make_profile(rag_mode="private", rag_coll=None):
    return SimpleNamespace(
        rag_mode=rag_mode,
        rag_provider_id="",
        rag_collection_ids=rag_coll or ["dkb_1"],
    )


def test_rag_hit_returns_content_and_citation():
    from app.tools_split import knowledge as kn

    fake_rag = [{
        "id": "c1",
        "title": "HCS 8.5.1 验收测试指南 Part 29",
        "content": "本节包含 15 个验收用例，涵盖计算、存储、网络三个维度。",
        "metadata": {
            "source_file": "docs/HCS_8.5.1_Part29.md",
            "heading_path": "验收指南 / 计算模块",
            "chunk_index": 29,
            "tags": "验收,HCS",
        },
    }]
    with patch("app.rag_provider.search_for_agent", return_value=fake_rag):
        out = kn._tool_knowledge_lookup(
            query="HCS 验收用例",
            agent_id="a1",
            _agent_profile=_make_profile(),
        )
    d = json.loads(out)
    assert d["status"] == "success", d
    entries = d["entries"]
    assert len(entries) == 1
    e = entries[0]
    # content surfaced (not stripped).
    assert "验收用例" in e["content"]
    # citation fields surfaced.
    assert e["source_file"] == "docs/HCS_8.5.1_Part29.md"
    assert e["heading_path"] == "验收指南 / 计算模块"
    assert e["chunk_index"] == 29
    assert "验收" in e["tags"]
    # usage_guidance drilled into the LLM: cite + no fabrication.
    g = d["usage_guidance"].lower()
    assert "cite" in g
    assert "do not" in g or "do not extrapolate" in g


def test_rag_hit_truncates_long_content():
    from app.tools_split import knowledge as kn

    long_body = "x" * 5000
    fake_rag = [{
        "id": "c1", "title": "T",
        "content": long_body,
        "metadata": {"source_file": "f.md", "chunk_index": 0},
    }]
    with patch("app.rag_provider.search_for_agent", return_value=fake_rag):
        out = kn._tool_knowledge_lookup(
            query="anything",
            agent_id="a1",
            _agent_profile=_make_profile(),
        )
    d = json.loads(out)
    e = d["entries"][0]
    assert len(e["content"]) == kn._MAX_CHUNK_CHARS_PER_HIT
    assert e["content_truncated"] is True


def test_rag_hit_short_content_not_flagged_truncated():
    from app.tools_split import knowledge as kn

    fake_rag = [{
        "id": "c1", "title": "T",
        "content": "short body",
        "metadata": {"chunk_index": 0},
    }]
    with patch("app.rag_provider.search_for_agent", return_value=fake_rag):
        out = kn._tool_knowledge_lookup(
            query="x",
            agent_id="a1",
            _agent_profile=_make_profile(),
        )
    d = json.loads(out)
    assert d["entries"][0]["content_truncated"] is False


# ── not_found path carries anti-fabrication hint ───────────────────


def test_not_found_tells_llm_not_to_fabricate():
    from app.tools_split import knowledge as kn

    with patch("app.rag_provider.search_for_agent", return_value=[]):
        with patch("app.tools_split.knowledge._knowledge.search", return_value=[]):
            out = kn._tool_knowledge_lookup(
                query="stuff that won't match",
                agent_id="a1",
                _agent_profile=_make_profile(rag_mode="both"),
            )
    d = json.loads(out)
    assert d["status"] == "not_found"
    msg = d["message"].lower()
    assert "fabricate" in msg or "do not" in msg


# ── RAG miss + Shared hit → still falls back to legacy title flow ─


def test_shared_only_hits_keep_legacy_partial_flow():
    from app.tools_split import knowledge as kn

    shared_hits = [
        {"id": "k1", "title": "Python style guide", "tags": ["py"], "source": "shared"},
        {"id": "k2", "title": "Markdown tips", "tags": [], "source": "shared"},
    ]
    with patch("app.rag_provider.search_for_agent", return_value=[]):
        with patch("app.tools_split.knowledge._knowledge.search", return_value=shared_hits):
            out = kn._tool_knowledge_lookup(
                query="coding",
                agent_id="a1",
                _agent_profile=_make_profile(rag_mode="both"),
            )
    d = json.loads(out)
    assert d["status"] == "partial"
    assert any(m["id"] == "k1" for m in d["matches"])


def test_shared_exact_title_match_returns_success():
    from app.tools_split import knowledge as kn

    shared_hits = [
        {"id": "k1", "title": "Python style guide", "content": "Use 4 spaces.",
         "tags": ["py"], "source": "shared"},
    ]
    with patch("app.rag_provider.search_for_agent", return_value=[]):
        with patch("app.tools_split.knowledge._knowledge.search", return_value=shared_hits):
            out = kn._tool_knowledge_lookup(
                query="Python style guide",
                agent_id="a1",
                _agent_profile=_make_profile(rag_mode="both"),
            )
    d = json.loads(out)
    assert d["status"] == "success"
    assert d["entry"]["content"] == "Use 4 spaces."


# ── tool-description constraints reach the LLM ────────────────────


def test_tool_description_mentions_citation_and_no_fabrication():
    from app import tools
    specs = [t for t in tools.TOOL_DEFINITIONS
             if t.get("function", {}).get("name") == "knowledge_lookup"]
    assert specs, "knowledge_lookup spec must exist"
    desc = specs[0]["function"]["description"].lower()
    # Must tell the LLM to cite.
    assert "cite" in desc
    # Must forbid fabrication explicitly.
    assert "do not" in desc and ("fabricate" in desc or "extrapolate" in desc or "invent" in desc)
