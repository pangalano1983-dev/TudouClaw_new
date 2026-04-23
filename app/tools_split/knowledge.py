"""Knowledge / learning tools — save_experience, knowledge_lookup,
share_knowledge, learn_from_peers.

All four read/write either the role-based Experience Library or the
shared Knowledge Base, and need to resolve caller-agent attribution
through the hub.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from .. import knowledge as _knowledge
from ._common import _get_hub

logger = logging.getLogger(__name__)


# knowledge_lookup: max results per RAG tier before merging.
# v2 (Pack): raised 5 → 8. Aggregate-style queries ("how many?",
# "list all…") need more chunks to synthesize from.
_RAG_TOP_K = 8

# v2 (Pack): cap each RAG chunk's content at this many chars when
# packing into tool_result. Protects LLM context from anomalous
# giant chunks. Typical chunk is ~800 chars so this barely clips.
_MAX_CHUNK_CHARS_PER_HIT = 1500

# knowledge_lookup: cap on partial-match list returned to the LLM when
# there's no exact title match (legacy Shared-pool code path only).
_PARTIAL_MATCHES_CAP = 20

# learn_from_peers: clamp user-supplied limit to this range.
_LEARN_LIMIT_MIN = 1
_LEARN_LIMIT_MAX = 20


# ── memory_recall (新 A.3) ──────────────────────────────────────────
# Agent-PRIVATE L3 semantic memory lookup. Deliberately separate from
# knowledge_lookup (which hits the ROLE-wide shared knowledge base):
# memory_recall is "did I personally encounter this before, what did I
# conclude?" — use it BEFORE web_search / re-analysis to avoid
# re-spending tokens on a topic this agent has already figured out.

def _tool_memory_recall(query: str = "",
                        category: str = "",
                        top_k: int = 5,
                        **_: Any) -> str:
    """Query the calling agent's private L3 semantic memory.

    Returns a compact, ranked list of prior facts/conclusions/rules
    this agent recorded. Use it as the FIRST step on any topic: if a
    recent high-confidence memory covers it, you can skip web_search
    and go straight to action.
    """
    caller_id = _.get("_caller_agent_id", "") if isinstance(_, dict) else ""
    if not caller_id:
        return "Error: memory_recall requires a calling agent context."
    q = (query or "").strip()
    if not q:
        return "Error: query is required (what are you trying to remember?)."
    try:
        from ..core.memory import get_memory_manager as _get_mm
        mm = _get_mm()
    except Exception as e:
        return f"Error: memory manager unavailable ({e})"
    if mm is None:
        return "Error: memory manager not initialized."

    try:
        k = max(1, min(int(top_k or 5), 20))
    except Exception:
        k = 5
    try:
        hits = mm.recall(caller_id, q, top_k=k,
                         category=(category or "").strip())
    except Exception as e:
        return f"Error recalling memory: {e}"

    # ── 新 A.7: 把本轮用到的记忆 id 记在 agent 上，供响应合成时
    # 挂到 assistant 消息，UI 能渲染 🧠 badge + 删除按钮。
    try:
        hub = _get_hub()
        agent = hub.get_agent(caller_id) if hub else None
        if agent is not None:
            bucket = getattr(agent, "_turn_memory_refs", None)
            if bucket is None:
                bucket = []
                setattr(agent, "_turn_memory_refs", bucket)
            for h in hits:
                fid = h.get("id") or ""
                if not fid:
                    continue
                # Skip already-recorded refs within the same turn.
                if any(r.get("id") == fid for r in bucket):
                    continue
                bucket.append({
                    "id": fid,
                    "category": h.get("category", ""),
                    "content_preview": (h.get("content") or "").strip()[:200],
                    "confidence": h.get("confidence", 1.0),
                    "age_days": h.get("age_days", 0),
                    "source": h.get("source", "") or "",
                })
    except Exception as _trk_err:
        logger.debug("memory_recall bucket tracking skipped: %s", _trk_err)

    if not hits:
        return (
            f"No prior memory found for query '{q[:60]}'. "
            "You'll need to explore fresh — consider web_search or "
            "knowledge_lookup, and save_experience afterward so the "
            "next turn can skip it."
        )

    lines = [f"Memory recall for '{q[:80]}' — {len(hits)} hit(s):"]
    for i, h in enumerate(hits, 1):
        cat = h.get("category", "general")
        age = h.get("age_days", 0)
        conf = h.get("confidence", 1.0)
        content = (h.get("content") or "").strip().replace("\n", " ")
        if len(content) > 260:
            content = content[:260] + "…"
        src = h.get("source") or ""
        if src and len(src) > 40:
            src = src[:40] + "…"
        lines.append(
            f"  [{i}] ({cat}) conf={conf:.2f}  age={age}d  id={h.get('id','')[:8]}"
        )
        lines.append(f"       {content}")
        if src:
            lines.append(f"       (source: {src})")
    lines.append("")
    lines.append(
        "💡 Use these prior conclusions if relevant. If a memory looks "
        "out-of-date or wrong, run your own verification and then "
        "save_experience with the corrected finding — it'll refresh the old one."
    )
    return "\n".join(lines)


# ── save_experience ──────────────────────────────────────────────────

def _tool_save_experience(
    scene: str,
    core_knowledge: str,
    action_rules: list[str] | None = None,
    taboo_rules: list[str] | None = None,
    priority: str = "medium",
    tags: list[str] | None = None,
    exp_type: str = "retrospective",
    source: str = "",
    role: str = "",
    evidence: list[str] | None = None,
    **ctx: Any,
) -> str:
    """Persist an experience entry into the role-based experience library.

    Skills (installable capability packages) are managed by the Skill
    Registry and are NOT written through this tool. Experiences are
    short, scene-anchored lessons that get auto-injected into the
    relevant role's system prompt.
    """
    try:
        if not scene or not core_knowledge:
            return "Error: 'scene' and 'core_knowledge' are required"

        # Resolve role: explicit arg > calling agent's role > 'default'.
        resolved_role = (role or "").strip()
        if not resolved_role:
            try:
                caller_id = ctx.get("_caller_agent_id", "") if isinstance(ctx, dict) else ""
                if caller_id:
                    hub = _get_hub()
                    agent = hub.get_agent(caller_id) if hub else None
                    if agent is not None:
                        resolved_role = (getattr(agent, "role", "") or "").strip()
            except Exception:
                pass
        if not resolved_role:
            resolved_role = "default"

        # Validate priority.
        pri = (priority or "medium").strip().lower()
        if pri not in ("high", "medium", "low"):
            pri = "medium"

        # Validate exp_type.
        etype = (exp_type or "retrospective").strip().lower()
        if etype not in ("retrospective", "active_learning"):
            etype = "retrospective"

        from ..experience_library import get_experience_library, Experience

        # Normalize evidence: strip whitespace, drop empties, dedup while
        # preserving insertion order.
        evidence_clean: list[str] = []
        seen_refs: set[str] = set()
        for ref in (evidence or []):
            s = str(ref).strip()
            if s and s not in seen_refs:
                seen_refs.add(s)
                evidence_clean.append(s)

        lib = get_experience_library()
        exp = Experience(
            exp_type=etype,
            source=source or "agent.save_experience",
            scene=scene.strip(),
            core_knowledge=core_knowledge.strip(),
            action_rules=[str(r).strip() for r in (action_rules or []) if str(r).strip()],
            taboo_rules=[str(r).strip() for r in (taboo_rules or []) if str(r).strip()],
            priority=pri,
            tags=[str(t).strip() for t in (tags or []) if str(t).strip()],
            evidence=evidence_clean,
        )
        saved = lib.add_experience(resolved_role, exp)

        # ── 新 A.4: mirror to calling agent's L3 memory via upsert ──
        # The role-wide Experience Library is shared across agents of
        # this role, but the calling agent also benefits from its OWN
        # private L3 memory: memory_recall() stays fast & personal, and
        # the similarity-refresh layer means repeated saves of the same
        # lesson refresh rather than spam.
        mirror_note = ""
        try:
            caller_id = ctx.get("_caller_agent_id", "") if isinstance(ctx, dict) else ""
            if caller_id:
                from ..core.memory import (
                    get_memory_manager as _gmm, SemanticFact as _SF,
                )
                mm = _gmm()
                if mm is not None:
                    # Categorize by exp_type → L3 taxonomy.
                    # retrospective → rule (lesson for future)
                    # active_learning → reasoning (how I decided something)
                    l3_cat = "rule" if etype == "retrospective" else "reasoning"
                    # Compact content: scene + core_knowledge + rules.
                    parts = [
                        f"[{exp.scene.strip()}]",
                        exp.core_knowledge.strip(),
                    ]
                    if exp.action_rules:
                        parts.append(
                            "DO: " + "; ".join(exp.action_rules[:5])
                        )
                    if exp.taboo_rules:
                        parts.append(
                            "DON'T: " + "; ".join(exp.taboo_rules[:5])
                        )
                    compact = "\n".join(parts)
                    # Confidence from priority.
                    conf_map = {"high": 0.95, "medium": 0.8, "low": 0.6}
                    fact = _SF(
                        agent_id=caller_id,
                        category=l3_cat,
                        content=compact,
                        source=f"save_experience({resolved_role}/{saved.id[:8]})",
                        confidence=conf_map.get(pri, 0.8),
                    )
                    res = mm.upsert_fact(fact, threshold=0.75)
                    action = res.get("action")
                    if action == "updated":
                        mirror_note = (
                            f" │ L3 refreshed (sim={res.get('similarity', 0):.2f})"
                        )
                    elif action == "inserted":
                        mirror_note = " │ L3 inserted"
                    else:
                        mirror_note = " │ L3 unchanged"
        except Exception as _mirror_err:
            logger.debug("save_experience L3 mirror skipped: %s", _mirror_err)

        return (
            f"✓ Experience saved: id={saved.id} role={resolved_role} "
            f"priority={saved.priority} scene={saved.scene[:60]}"
            f"{mirror_note}"
        )
    except Exception as e:
        return f"Error saving experience: {e}"


# ── knowledge_lookup ─────────────────────────────────────────────────

# Pack v3: cap kb_list rows sent to the LLM to keep payload bounded.
# Max Markdown-table size = _KB_LIST_LIMIT × ~160 chars ≈ 32KB, still
# under typical context windows. LLM gets a ``truncated`` flag to know.
_KB_LIST_LIMIT = 200


def _kb_aggregate(mode: str, query: str, rag_mode: str,
                  agent_profile: Any, agent_id: str) -> str:
    """Pack v3 — run count / list across every domain KB bound to this
    agent + (for shared/both) the global 'knowledge' collection.

    Returns a JSON string ready to hand back to the LLM. Never raises.
    """
    from ..rag_provider import get_rag_registry, get_domain_kb_store
    reg = get_rag_registry()

    # Enumerate the (provider_id, collection, label) tuples to scan.
    targets: list[tuple[str, str, str]] = []
    if rag_mode in ("private", "both") and agent_profile is not None:
        provider_id = getattr(agent_profile, "rag_provider_id", "") or ""
        coll_ids = getattr(agent_profile, "rag_collection_ids", []) or []
        dkb_store = get_domain_kb_store()
        for kb_id in coll_ids:
            kb = dkb_store.get(kb_id)
            if kb:
                targets.append((kb.provider_id or provider_id,
                                kb.collection,
                                kb.name or kb_id))
            else:
                targets.append((provider_id, kb_id, kb_id))
        # Legacy advisor_{id} collection
        if agent_id:
            targets.append((provider_id, f"advisor_{agent_id}",
                            f"advisor_{agent_id}"))
    if rag_mode in ("shared", "both"):
        targets.append(("", "knowledge", "shared_knowledge"))

    if not targets:
        return json.dumps({
            "status": "not_found",
            "mode": mode,
            "message": "No knowledge base bound to this agent.",
        }, ensure_ascii=False)

    if mode == "count":
        per_kb = []
        grand_total_chunks = 0
        grand_total_files = 0
        grand_filter_matched = 0
        for pid, coll, label in targets:
            try:
                stat = reg.kb_statistics(pid, coll, query=query)
            except Exception as e:
                logger.warning("kb_statistics failed for %s: %s", label, e)
                continue
            stat["kb"] = label
            stat["collection"] = coll
            per_kb.append(stat)
            grand_total_chunks += stat.get("total_chunks", 0)
            grand_total_files += stat.get("unique_source_files", 0)
            grand_filter_matched += stat.get("filter_matched", 0)
        return json.dumps({
            "status": "success",
            "mode": "count",
            "filter": query or "",
            "grand_total_chunks": grand_total_chunks,
            "grand_total_source_files": grand_total_files,
            "grand_filter_matched": grand_filter_matched,
            "per_kb": per_kb,
            "usage_guidance": (
                "These counts come from a direct scan of the KB's "
                "metadata (not a top-k sample). Use them verbatim for "
                "aggregate answers like '有多少', '总数'. The "
                "`by_source_file` breakdown lets you report per-document "
                "counts. If `filter` was given, `filter_matched` is the "
                "number of chunks whose title/heading/source/content "
                "contained the filter — that is typically the number "
                "the user asked about."
            ),
        }, ensure_ascii=False, indent=2)

    # mode == "list"
    per_kb_lists = []
    for pid, coll, label in targets:
        try:
            lst = reg.kb_list(pid, coll, query=query,
                              limit=_KB_LIST_LIMIT)
        except Exception as e:
            logger.warning("kb_list failed for %s: %s", label, e)
            continue
        lst["kb"] = label
        lst["collection"] = coll
        per_kb_lists.append(lst)
    total_shown = sum(len(k.get("items", [])) for k in per_kb_lists)
    any_truncated = any(k.get("truncated") for k in per_kb_lists)
    return json.dumps({
        "status": "success",
        "mode": "list",
        "filter": query or "",
        "total_shown": total_shown,
        "any_truncated": any_truncated,
        "per_kb": per_kb_lists,
        "usage_guidance": (
            "Each item is a chunk's metadata only (no content body). "
            "Use this to render a table of contents or inventory of "
            "what's in the KB. If `any_truncated` is True some KBs "
            "have more items than were returned — suggest a narrower "
            "filter."
        ),
    }, ensure_ascii=False, indent=2)


def _tool_knowledge_lookup(query: str = "", entry_id: str = "",
                           agent_id: str = "", mode: str = "search",
                           **kw: Any) -> str:
    """Look up entries in the knowledge base.

    Routing is determined by the agent's rag_mode:
      - "shared"  → query global shared knowledge (default)
      - "private" → query agent's private collection
      - "both"    → query private first, then shared
      - "none"    → return empty

    Modes (Pack v3):
      - mode="search" (default): top-k vector+BM25 retrieval with content.
        Use for normal questions that can be answered from a few chunks.
      - mode="count": programmatic scan of ALL chunks in the collection,
        grouped by source_file. Use for aggregate queries ("how many?",
        "总数", "有多少个"). Optional ``query`` filters by substring
        match in title/heading_path/source_file/content.
      - mode="list": flat list of chunks' metadata (no content). Use
        when user wants a table of contents / inventory listing.

    If entry_id is provided, returns that entry's full content from
    shared KB. Otherwise searches / counts / lists by query using the
    agent's configured RAG routing.
    """
    try:
        # If entry_id is provided, fetch that entry directly from shared KB.
        if entry_id:
            entry = _knowledge.get_entry(entry_id)
            if entry:
                return json.dumps({"status": "success", "entry": entry},
                                  ensure_ascii=False, indent=2)
            return json.dumps({
                "status": "error",
                "message": f"Entry '{entry_id}' not found"
            })

        mode = (mode or "search").lower().strip()
        if mode not in ("search", "count", "list"):
            return json.dumps({
                "status": "error",
                "message": f"Unknown mode '{mode}'. Use search | count | list.",
            })

        # search mode requires query; count / list allow empty query
        # (whole-collection overview).
        if mode == "search" and not query:
            return json.dumps({
                "status": "error",
                "message": "Either 'query' or 'entry_id' must be provided "
                           "for mode=search",
            })

        # --- RAG-routed search ---
        agent_profile = kw.get("_agent_profile")
        rag_mode = "shared"  # default
        if agent_profile:
            rag_mode = getattr(agent_profile, "rag_mode", "shared") or "shared"

        if rag_mode == "none":
            return json.dumps({
                "status": "not_found",
                "message": "RAG is disabled for this agent (rag_mode=none)"
            })

        # --- Pack v3: count / list modes bypass top-k entirely. ---
        if mode in ("count", "list"):
            return _kb_aggregate(mode, query, rag_mode, agent_profile,
                                 agent_id)

        results_combined = []

        # Private / Both: search via RAG provider registry.
        # v2 (Pack): RAG chunks are already content — keep their bodies,
        # surface citation metadata (source_file, heading_path, chunk_index),
        # and cap each chunk to _MAX_CHUNK_CHARS_PER_HIT.
        rag_hits = []
        if rag_mode in ("private", "both") and agent_id:
            try:
                from ..rag_provider import search_for_agent
                rag_results = search_for_agent(agent_profile, query,
                                               agent_id=agent_id,
                                               top_k=_RAG_TOP_K)
                for r in rag_results:
                    meta = r.get("metadata") or {}
                    raw_content = r.get("content", "") or ""
                    trimmed = raw_content[:_MAX_CHUNK_CHARS_PER_HIT]
                    tags_raw = meta.get("tags", "")
                    tags_list = tags_raw.split(",") if isinstance(tags_raw, str) and tags_raw else []
                    rag_hits.append({
                        "id": r.get("id", ""),
                        "title": r.get("title", ""),
                        "content": trimmed,
                        "content_truncated": len(raw_content) > _MAX_CHUNK_CHARS_PER_HIT,
                        # ── citation fields (v1-C metadata persisted these) ──
                        "source_file": meta.get("source_file", ""),
                        "heading_path": meta.get("heading_path", ""),
                        "chunk_index": meta.get("chunk_index"),
                        "tags": tags_list,
                        "source": "private_rag",
                    })
            except Exception as e:
                logger.warning("RAG provider search failed: %s", e)

        # Shared / Both: also search the classic shared knowledge base.
        shared_hits = []
        if rag_mode in ("shared", "both"):
            shared_results = _knowledge.search(query)
            for e in shared_results:
                # Avoid duplicates (same ID already from RAG).
                if not any(r["id"] == e["id"] for r in rag_hits):
                    shared_hits.append(e)

        if not rag_hits and not shared_hits:
            return json.dumps({
                "status": "not_found",
                "message": f"知识库无匹配内容 for '{query}'. "
                           "Do NOT fabricate — tell the user no relevant knowledge found.",
            }, ensure_ascii=False)

        # v2 (Pack): RAG hits ARE content chunks (not titled entries),
        # so we return them directly as `entries` with full content + citation.
        # The Shared-pool legacy "partial/match-by-title" flow is kept for
        # shared entries only.
        if rag_hits:
            return json.dumps({
                "status": "success",
                "entries": rag_hits,
                "usage_guidance": (
                    "These are retrieved chunks from the expert knowledge base. "
                    "When answering: (1) cite source as [source_file §heading_path] "
                    "or [title #chunk_index]; (2) reason only from the content "
                    "provided — do NOT extrapolate or invent; (3) if the chunks "
                    "do not contain enough information to answer, say '知识库中未找到直接答案' "
                    "and propose what extra material would be needed."
                ),
            }, ensure_ascii=False, indent=2)

        # Fallback: only shared pool hits. Keep legacy title-match refinement.
        query_lower = query.lower().strip()
        for entry in shared_hits:
            if entry.get("title", "").lower().strip() == query_lower:
                return json.dumps({"status": "success", "entry": entry},
                                  ensure_ascii=False, indent=2)

        matches = [
            {"id": e.get("id", ""), "title": e.get("title", ""),
             "tags": e.get("tags", []),
             "source": e.get("source", "shared")}
            for e in shared_hits[:_PARTIAL_MATCHES_CAP]
        ]
        return json.dumps({
            "status": "partial",
            "message": (f"Found {len(matches)} shared entries matching title. "
                        "Use entry_id to read full content."),
            "matches": matches,
        }, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"Error querying knowledge base: {str(e)}"
        })


# ── share_knowledge ──────────────────────────────────────────────────

def _tool_share_knowledge(title: str, content: str,
                          tags: list[str] | None = None,
                          **ctx: Any) -> str:
    """Share knowledge with all agents via the shared Knowledge Base."""
    try:
        if not title or not title.strip():
            return "Error: 'title' is required"
        if not content or not content.strip():
            return "Error: 'content' is required"

        # Resolve caller agent info for attribution.
        caller_name = ""
        caller_role = ""
        try:
            caller_id = ctx.get("_caller_agent_id", "") if isinstance(ctx, dict) else ""
            if caller_id:
                hub = _get_hub()
                agent = hub.get_agent(caller_id) if hub else None
                if agent is not None:
                    caller_name = getattr(agent, "name", "") or ""
                    caller_role = getattr(agent, "role", "") or ""
        except Exception:
            pass

        # Add source attribution.
        source_info = ""
        if caller_name or caller_role:
            source_info = f"\n\n---\nShared by: {caller_name} (role: {caller_role})"

        resolved_tags = [str(t).strip() for t in (tags or []) if str(t).strip()]
        if caller_role:
            resolved_tags += ["shared-by-agent", caller_role]

        entry = _knowledge.add_entry(
            title=title.strip(),
            content=content.strip() + source_info,
            tags=resolved_tags,
        )
        return (
            f"Knowledge shared successfully: '{title.strip()}' "
            f"(id: {entry['id']}). "
            f"All agents can now access this via knowledge_lookup."
        )
    except Exception as e:
        return f"Failed to share knowledge: {e}"


# ── learn_from_peers ─────────────────────────────────────────────────

def _tool_learn_from_peers(source_role: str, topic: str = "",
                           limit: int = 5, **ctx: Any) -> str:
    """Learn from other agents' experiences by importing from another role."""
    try:
        if not source_role or not source_role.strip():
            return "Error: 'source_role' is required"

        source_role = source_role.strip()
        limit = max(_LEARN_LIMIT_MIN, min(int(limit), _LEARN_LIMIT_MAX))

        # Resolve caller's role.
        caller_role = ""
        try:
            caller_id = ctx.get("_caller_agent_id", "") if isinstance(ctx, dict) else ""
            if caller_id:
                hub = _get_hub()
                agent = hub.get_agent(caller_id) if hub else None
                if agent is not None:
                    caller_role = getattr(agent, "role", "") or ""
        except Exception:
            pass

        from ..experience_library import _get_global_library
        library = _get_global_library()
        experiences = library.import_cross_role(
            source_role=source_role,
            target_role=caller_role or "default",
            topic=topic.strip() if topic else "",
            limit=limit,
        )
        if not experiences:
            msg = f"No experiences found for role '{source_role}'"
            if topic:
                msg += f" on topic '{topic}'"
            return msg

        lines = [f"Imported {len(experiences)} experiences from role "
                 f"'{source_role}':"]
        for i, exp in enumerate(experiences, 1):
            lines.append(f"\n{i}. [{exp.priority}] {exp.scene}")
            lines.append(f"   Knowledge: {exp.core_knowledge[:200]}")
            if exp.action_rules:
                lines.append(f"   Rules: {'; '.join(exp.action_rules[:3])}")
            lines.append(f"   Success rate: {exp.success_rate:.0%}")
        return "\n".join(lines)
    except Exception as e:
        return f"Failed to learn from peers: {e}"
