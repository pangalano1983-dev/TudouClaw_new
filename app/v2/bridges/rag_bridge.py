"""Task-level RAG injection for V2 tasks.

When a V2 task starts, we look up relevant ``wiki`` pages and
``experience_library`` entries by the task's intent string and produce
a small markdown block (~3-5 entries) that the planner / executor can
read as "what I already know about this kind of task". Top-K and
similarity threshold mirror /recall's policy so behaviour stays
predictable.

Returned block is empty string when nothing relevant exists — callers
should treat that as "no knowledge to inject" rather than error.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("tudouclaw.v2.rag_bridge")


# Caps tuned for "background hint" use, not interactive recall.
# Plan/Execute prompts have a token budget; we don't want to bloat
# them with marginal entries.
_MAX_WIKI = 3
_MAX_EXPERIENCE = 3


def retrieve_task_knowledge(intent: str, role: str = "") -> str:
    """Return a compact markdown block of relevant wiki + experience.

    Empty string when nothing relevant. Never raises — returns "" on
    any internal error (RAG injection is best-effort, must not break
    the task pipeline).
    """
    if not intent or not intent.strip():
        return ""
    intent = intent.strip()
    role_norm = (role or "").lower().strip()

    blocks: list[str] = []

    # ── Wiki layer (role-scoped + global) ───────────────────────────
    try:
        from ...knowledge.wiki_store import get_wiki_store
        wiki = get_wiki_store()
        seen: set[str] = set()
        wiki_hits = []
        if role_norm:
            for p in wiki.search(intent, scope=f"role:{role_norm}", limit=_MAX_WIKI):
                if p.id in seen:
                    continue
                seen.add(p.id)
                wiki_hits.append(p)
        for p in wiki.search(intent, scope="global", limit=_MAX_WIKI):
            key = (p.scope, p.slug)
            if key in seen:
                continue
            seen.add(key)
            wiki_hits.append(p)
        wiki_hits = wiki_hits[:_MAX_WIKI]
        if wiki_hits:
            lines = ["📚 **相关经验 / Wiki 知识**："]
            for p in wiki_hits:
                preview = (p.body or "").replace("\n", " ").strip()[:150]
                lines.append(
                    f"- **{p.title}** [{p.kind}] (✓{p.success_count}/✗{p.fail_count}): "
                    f"{preview}{'…' if len(p.body or '') > 150 else ''}"
                )
            blocks.append("\n".join(lines))
    except Exception as e:
        logger.debug("rag wiki fetch failed: %s", e)

    # ── Experience library (role-matched, scene-keyword) ────────────
    try:
        from ...experience_library import get_experience_library
        lib = get_experience_library()
        if lib is not None and role_norm:
            try:
                exps = lib.search(role_norm, scene=intent, limit=_MAX_EXPERIENCE)
            except Exception as _e:
                logger.debug("experience_library.search failed: %s", _e)
                exps = []
            if exps:
                lines = ["💡 **同类任务经验**："]
                for e in exps[:_MAX_EXPERIENCE]:
                    scene = (getattr(e, "scene", "") or "").strip()
                    core = (getattr(e, "core_knowledge", "") or "").replace("\n", " ").strip()[:150]
                    if scene or core:
                        lines.append(f"- **{scene}**: {core}{'…' if len(core) >= 150 else ''}")
                if len(lines) > 1:
                    blocks.append("\n".join(lines))
    except Exception as e:
        logger.debug("rag experience fetch failed: %s", e)

    if not blocks:
        return ""
    return "\n\n".join(blocks)
