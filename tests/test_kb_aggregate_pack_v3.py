"""Pack v3 — knowledge_lookup mode=count/list for aggregate queries.

Before Pack v3: 'how many HCS acceptance test cases?' went through
top-k RAG (8 chunks), which can never answer a full-KB aggregate — the
LLM reasons from 8 samples and guesses.

After Pack v3:
  * mode=count does a programmatic metadata scan of the whole collection,
    grouping chunks by source_file. Returns exact numbers.
  * mode=list returns per-chunk metadata (title/source/heading/index)
    without content, for TOC-style inventory.
  * mode=search (default) preserves the existing top-k behavior.
  * Both aggregate modes accept an optional query to filter by
    substring match on title/heading_path/source_file (+content for count).
  * Tool description + retrieval protocol both updated so the LLM picks
    the right mode instead of retrying search over and over.
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


# ── Registry.kb_statistics unit (rag_provider.py) ─────────────────


class _FakeChromaCollection:
    """In-memory chroma-ish collection supporting get(include=...)."""

    def __init__(self, ids, docs, metas):
        self._ids = list(ids)
        self._docs = list(docs)
        self._metas = list(metas)

    def get(self, ids=None, include=None):
        include = include or []
        if ids is None:
            sel = list(range(len(self._ids)))
        else:
            sel = [self._ids.index(i) for i in ids if i in self._ids]
        out = {"ids": [self._ids[i] for i in sel]}
        if "documents" in include:
            out["documents"] = [self._docs[i] for i in sel]
        if "metadatas" in include:
            out["metadatas"] = [self._metas[i] for i in sel]
        return out

    def count(self):
        return len(self._ids)


def _registry_with(chunks):
    """Build a RAGProviderRegistry pointing at an in-memory chroma shim.

    `chunks` is a list of (id, doc, meta) tuples.
    """
    from app import rag_provider as rp
    reg = rp.RAGProviderRegistry.__new__(rp.RAGProviderRegistry)
    reg._providers = {}
    reg._loaded = True
    ids = [c[0] for c in chunks]
    docs = [c[1] for c in chunks]
    metas = [c[2] for c in chunks]
    coll = _FakeChromaCollection(ids, docs, metas)

    class _MM:
        def _get_chroma_collection(self, name):
            return coll

    reg._get_memory_manager = lambda: _MM()
    return reg


def _mkchunk(i, source_file, title="", heading="", content=""):
    return (f"c{i}", content, {
        "source_file": source_file,
        "title": title,
        "heading_path": heading,
        "chunk_index": i,
    })


# ── kb_statistics ─────────────────────────────────────────────────


def test_kb_statistics_groups_by_source_file():
    chunks = [
        _mkchunk(0, "doc_A.md"),
        _mkchunk(1, "doc_A.md"),
        _mkchunk(2, "doc_A.md"),
        _mkchunk(3, "doc_B.md"),
        _mkchunk(4, "doc_B.md"),
        _mkchunk(5, "doc_C.md"),
    ]
    reg = _registry_with(chunks)
    stat = reg.kb_statistics("", "any")
    assert stat["total_chunks"] == 6
    assert stat["unique_source_files"] == 3
    by = {s["source_file"]: s["chunk_count"] for s in stat["by_source_file"]}
    assert by == {"doc_A.md": 3, "doc_B.md": 2, "doc_C.md": 1}
    # Sorted descending
    counts = [s["chunk_count"] for s in stat["by_source_file"]]
    assert counts == sorted(counts, reverse=True)


def test_kb_statistics_unknown_bucket_when_no_source():
    chunks = [
        ("c0", "body", {"title": "t"}),   # no source_file at all
        _mkchunk(1, "doc_A.md"),
    ]
    reg = _registry_with(chunks)
    stat = reg.kb_statistics("", "any")
    names = [s["source_file"] for s in stat["by_source_file"]]
    assert "unknown" in names
    assert "doc_A.md" in names


def test_kb_statistics_filter_matches_title_and_content():
    chunks = [
        _mkchunk(0, "HCS_8.5.1_Acceptance.docx", title="HCS part 1",
                 heading="验收指南 / 计算",
                 content="本章介绍 3 个验收用例"),   # matches (content)
        _mkchunk(1, "HCS_8.5.1_Acceptance.docx", title="HCS 验收用例 list",
                 heading="存储", content="存储相关"),  # matches (title)
        _mkchunk(2, "README.md", title="readme",
                 heading="overview", content="unrelated"),  # no match
    ]
    reg = _registry_with(chunks)
    stat = reg.kb_statistics("", "any", query="验收用例")
    assert stat["filter"] == "验收用例"
    assert stat["filter_matched"] == 2
    by = {s["source_file"]: s["chunk_count"] for s in stat["by_source_file"]}
    assert by == {"HCS_8.5.1_Acceptance.docx": 2}


def test_kb_statistics_empty_collection():
    reg = _registry_with([])
    stat = reg.kb_statistics("", "any")
    assert stat["total_chunks"] == 0
    assert stat["unique_source_files"] == 0
    assert stat["by_source_file"] == []


def test_kb_statistics_title_sample_capped():
    chunks = [_mkchunk(i, "doc.md", title=f"Title {i}") for i in range(10)]
    reg = _registry_with(chunks)
    stat = reg.kb_statistics("", "any")
    samples = stat["by_source_file"][0]["titles_sample"]
    assert len(samples) <= 5


# ── kb_list ───────────────────────────────────────────────────────


def test_kb_list_returns_metadata_only():
    chunks = [
        _mkchunk(0, "doc.md", title="Chapter 1", heading="intro",
                 content="long body should NOT be in output"),
        _mkchunk(1, "doc.md", title="Chapter 2", heading="detail",
                 content="another long body"),
    ]
    reg = _registry_with(chunks)
    lst = reg.kb_list("", "any")
    assert lst["total"] == 2
    assert not lst["truncated"]
    for item in lst["items"]:
        assert "title" in item
        assert "chunk_index" in item
        assert "source_file" in item
        assert "heading_path" in item
        # Content must not leak
        assert "body" not in json.dumps(item)


def test_kb_list_sorts_by_source_then_chunk_index():
    chunks = [
        _mkchunk(2, "doc_B.md", title="B2"),
        _mkchunk(0, "doc_A.md", title="A0"),
        _mkchunk(1, "doc_A.md", title="A1"),
    ]
    reg = _registry_with(chunks)
    lst = reg.kb_list("", "any")
    titles_in_order = [i["title"] for i in lst["items"]]
    assert titles_in_order == ["A0", "A1", "B2"]


def test_kb_list_limit_enforced():
    chunks = [_mkchunk(i, "doc.md", title=f"T{i}") for i in range(300)]
    reg = _registry_with(chunks)
    lst = reg.kb_list("", "any", limit=50)
    assert len(lst["items"]) == 50
    assert lst["total"] == 300
    assert lst["truncated"] is True


def test_kb_list_filter_substring():
    chunks = [
        _mkchunk(0, "a.md", title="HCS overview"),
        _mkchunk(1, "a.md", title="unrelated"),
        _mkchunk(2, "b.md", title="More HCS stuff"),
    ]
    reg = _registry_with(chunks)
    lst = reg.kb_list("", "any", query="HCS")
    titles = [i["title"] for i in lst["items"]]
    assert titles == ["HCS overview", "More HCS stuff"]


# ── knowledge_lookup mode dispatch ────────────────────────────────


def _profile(rag_mode="private", coll_ids=None):
    if coll_ids is None:
        coll_ids = ["dkb_1"]
    return SimpleNamespace(
        rag_mode=rag_mode,
        rag_provider_id="",
        rag_collection_ids=coll_ids,
    )


def _mock_registry_count(result_dict):
    """Patch get_rag_registry to return a fake that yields `result_dict`."""
    fake_reg = SimpleNamespace(
        kb_statistics=lambda pid, coll, query="": dict(result_dict),
        kb_list=lambda pid, coll, query="", limit=50: {"items": [], "total": 0,
                                                       "truncated": False},
    )
    return patch("app.rag_provider.get_rag_registry",
                 return_value=fake_reg)


def test_mode_count_returns_success_with_counts():
    from app.tools_split import knowledge as kn

    stats = {
        "total_chunks": 7187,
        "unique_source_files": 2,
        "by_source_file": [
            {"source_file": "HCS_Basic.docx", "chunk_count": 3421,
             "first_heading": "", "titles_sample": []},
            {"source_file": "HCS_Extended.docx", "chunk_count": 3766,
             "first_heading": "", "titles_sample": []},
        ],
        "filter": "验收用例", "filter_matched": 542,
    }
    # Need a domain KB store too
    fake_kb = SimpleNamespace(provider_id="", collection="dkb_coll_1",
                              name="云技术服务知识库")
    fake_store = SimpleNamespace(get=lambda kid: fake_kb)

    with patch("app.rag_provider.get_domain_kb_store",
               return_value=fake_store), \
         _mock_registry_count(stats):
        out = kn._tool_knowledge_lookup(
            # agent_id="" → skip legacy advisor_{id} collection
            # so per_kb has exactly 1 entry (the bound KB).
            query="验收用例", agent_id="", mode="count",
            _agent_profile=_profile(),
        )
    d = json.loads(out)
    assert d["status"] == "success"
    assert d["mode"] == "count"
    assert d["grand_total_chunks"] == 7187
    assert d["grand_filter_matched"] == 542
    assert d["filter"] == "验收用例"
    assert "usage_guidance" in d
    assert len(d["per_kb"]) == 1
    assert d["per_kb"][0]["kb"] == "云技术服务知识库"


def test_mode_count_no_query_scans_whole_kb():
    from app.tools_split import knowledge as kn
    stats = {"total_chunks": 100, "unique_source_files": 1,
             "by_source_file": [{"source_file": "d.md", "chunk_count": 100,
                                 "first_heading": "", "titles_sample": []}],
             "filter": "", "filter_matched": 0}
    fake_store = SimpleNamespace(get=lambda kid: SimpleNamespace(
        provider_id="", collection="c", name="k"))

    with patch("app.rag_provider.get_domain_kb_store",
               return_value=fake_store), \
         _mock_registry_count(stats):
        out = kn._tool_knowledge_lookup(
            query="", agent_id="", mode="count",
            _agent_profile=_profile(),
        )
    d = json.loads(out)
    assert d["status"] == "success"
    assert d["grand_total_chunks"] == 100


def test_mode_list_returns_inventory():
    from app.tools_split import knowledge as kn
    items = {"items": [
        {"id": "c0", "title": "T0", "source_file": "d.md",
         "heading_path": "h", "chunk_index": 0},
        {"id": "c1", "title": "T1", "source_file": "d.md",
         "heading_path": "h", "chunk_index": 1},
    ], "total": 2, "truncated": False, "filter": ""}
    fake_reg = SimpleNamespace(
        kb_statistics=lambda pid, coll, query="": {},
        kb_list=lambda pid, coll, query="", limit=50: dict(items),
    )
    fake_store = SimpleNamespace(get=lambda kid: SimpleNamespace(
        provider_id="", collection="c", name="k"))
    with patch("app.rag_provider.get_rag_registry",
               return_value=fake_reg), \
         patch("app.rag_provider.get_domain_kb_store",
               return_value=fake_store):
        out = kn._tool_knowledge_lookup(
            query="", agent_id="", mode="list",
            _agent_profile=_profile(),
        )
    d = json.loads(out)
    assert d["status"] == "success"
    assert d["mode"] == "list"
    assert d["total_shown"] == 2


def test_mode_search_default_still_works():
    """Legacy behavior: no mode arg → mode=search (Pack v2 path)."""
    from app.tools_split import knowledge as kn

    fake_rag = [{
        "id": "c1", "title": "T",
        "content": "matched body",
        "metadata": {"source_file": "f.md", "chunk_index": 1},
    }]
    with patch("app.rag_provider.search_for_agent",
               return_value=fake_rag):
        out = kn._tool_knowledge_lookup(
            query="anything", agent_id="a1",
            _agent_profile=_profile(),
        )
    d = json.loads(out)
    assert d["status"] == "success"
    assert "entries" in d
    # Not a count/list payload
    assert "grand_total_chunks" not in d
    assert "per_kb" not in d


def test_mode_unknown_returns_error():
    from app.tools_split import knowledge as kn
    out = kn._tool_knowledge_lookup(
        query="x", agent_id="a1", mode="weird",
        _agent_profile=_profile(),
    )
    d = json.loads(out)
    assert d["status"] == "error"


def test_mode_count_when_rag_none_returns_not_found():
    from app.tools_split import knowledge as kn
    out = kn._tool_knowledge_lookup(
        query="x", agent_id="a1", mode="count",
        _agent_profile=_profile(rag_mode="none"),
    )
    d = json.loads(out)
    assert d["status"] == "not_found"


def test_mode_count_no_kb_bound_returns_not_found():
    from app.tools_split import knowledge as kn
    # rag_mode private but no collection ids AND no agent_id → no targets
    out = kn._tool_knowledge_lookup(
        query="x", agent_id="", mode="count",
        _agent_profile=_profile(rag_mode="private", coll_ids=[]),
    )
    d = json.loads(out)
    assert d["status"] == "not_found"


# ── tool description propagation ──────────────────────────────────


def test_tool_description_mentions_all_three_modes():
    from app import tools
    specs = [t for t in tools.TOOL_DEFINITIONS
             if t["function"]["name"] == "knowledge_lookup"]
    assert specs
    desc = specs[0]["function"]["description"]
    assert "mode=\"count\"" in desc
    assert "mode=\"list\"" in desc
    assert "mode=\"search\"" in desc


def test_tool_schema_exposes_mode_enum():
    from app import tools
    spec = [t for t in tools.TOOL_DEFINITIONS
            if t["function"]["name"] == "knowledge_lookup"][0]
    props = spec["function"]["parameters"]["properties"]
    assert "mode" in props
    assert set(props["mode"]["enum"]) == {"search", "count", "list"}


def test_retrieval_protocol_mentions_mode_count():
    """The protocol injected for RAG-bound agents must teach the LLM to
    use mode=count for aggregate queries."""
    from app.agent import _RETRIEVAL_PROTOCOL_TEXT
    assert "mode=\"count\"" in _RETRIEVAL_PROTOCOL_TEXT
    assert "mode=\"list\"" in _RETRIEVAL_PROTOCOL_TEXT
    assert "有多少" in _RETRIEVAL_PROTOCOL_TEXT or "总数" in _RETRIEVAL_PROTOCOL_TEXT
