"""Block 3 Day 4-5 — Checkpoint digest.

Compresses an `AgentCheckpoint` into a continuation-oriented prompt
that's much shorter than the raw state. The digest is what gets
prepended to the LLM's prompt on resume.

Philosophy:
  * Deterministic by default — no LLM call needed for a usable digest.
  * LLM compression is OPTIONAL (Day 5) and only kicks in when the
    deterministic text exceeds the token budget.
  * Crash-safe: a failure in the LLM path falls back to the
    deterministic output, never raising.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .checkpoint import AgentCheckpoint, get_store

logger = logging.getLogger("tudou.digest")


# A cheap "tokens ≈ chars/4" heuristic. Good enough for budget decisions;
# we never use this for billing or precise limits.
CHARS_PER_TOKEN_EST = 4


def _approx_tokens(s: str) -> int:
    return max(1, len(s) // CHARS_PER_TOKEN_EST)


# ── Result dataclass ────────────────────────────────────────────────


@dataclass
class DigestResult:
    text: str = ""
    token_estimate: int = 0
    sections_included: list[str] = field(default_factory=list)
    truncated: bool = False
    llm_compressed: bool = False

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "token_estimate": self.token_estimate,
            "sections_included": list(self.sections_included),
            "truncated": self.truncated,
            "llm_compressed": self.llm_compressed,
        }


# ── Section builders ────────────────────────────────────────────────


def _fmt_header(ckpt: AgentCheckpoint) -> str:
    from datetime import datetime as _dt
    when = ""
    try:
        when = _dt.fromtimestamp(ckpt.created_at).strftime("%Y-%m-%d %H:%M")
    except Exception:
        pass
    reason = ckpt.reason or "manual"
    scope_desc = ckpt.scope
    if ckpt.scope_id:
        scope_desc += f" ({ckpt.scope_id})"
    return (
        "你之前的工作被保存在一个检查点里，现在要**继续**，不要从头开始。\n"
        f"- 检查点 ID: {ckpt.id}\n"
        f"- 作用域: {scope_desc}\n"
        f"- 保存于: {when}\n"
        f"- 中断原因: {reason}"
    )


def _fmt_plan_sections(plan_json: dict) -> tuple[str, str]:
    """Return (completed_section, unfinished_section). Either may be empty."""
    if not plan_json or not isinstance(plan_json, dict):
        return "", ""
    steps = plan_json.get("steps") or []
    completed_lines: list[str] = []
    unfinished_lines: list[str] = []
    for s in steps:
        status = (s.get("status") or "").lower()
        title = s.get("title") or s.get("task_summary") or "(untitled)"
        order = s.get("order")
        prefix = f"- [{order}] " if order is not None else "- "
        summary = (s.get("result_summary") or "").strip()
        acceptance = (s.get("acceptance") or "").strip()
        if status in ("completed", "done", "skipped"):
            bullet = prefix + title
            if summary:
                bullet += f' — "{summary[:120]}"'
            completed_lines.append(bullet)
        elif status in ("in_progress", "pending", "failed", "todo"):
            bullet = prefix + f"**{title}** ({status or 'pending'})"
            if acceptance:
                bullet += f"\n    acceptance: {acceptance}"
            if summary and status == "failed":
                bullet += f"\n    上次失败: {summary[:150]}"
            unfinished_lines.append(bullet)
    completed = ""
    if completed_lines:
        completed = "## ✅ 已完成 (不要重做)\n" + "\n".join(completed_lines)
    unfinished = ""
    if unfinished_lines:
        unfinished = "## ⏳ 待完成 (你的任务)\n" + "\n".join(unfinished_lines)
    return completed, unfinished


def _fmt_artifacts(refs: list[dict]) -> str:
    if not refs:
        return ""
    lines = ["## 📂 已有产物 (可以直接复用)"]
    for r in refs[:15]:
        rid = r.get("id") or ""
        kind = r.get("kind") or ""
        path = r.get("path") or ""
        size = r.get("size_bytes") or r.get("size")
        label = path or rid or "artifact"
        size_str = ""
        if isinstance(size, int):
            size_str = (f" ({size} B)" if size < 1024
                        else f" ({size // 1024} KB)" if size < 1024 * 1024
                        else f" ({size // (1024 * 1024)} MB)")
        lines.append(f"- `{label}` [{kind or 'ref'}]{size_str}")
    if len(refs) > 15:
        lines.append(f"- … 还有 {len(refs) - 15} 个")
    return "\n".join(lines)


def _fmt_chat_tail(tail: list[dict], max_msgs: int = 8,
                   max_chars_per_msg: int = 320) -> str:
    if not tail:
        return ""
    slice_ = tail[-max_msgs:] if len(tail) > max_msgs else tail
    lines = ["## 💬 最近对话 (上下文)"]
    for m in slice_:
        role = (m.get("role") or m.get("sender") or "").strip() or "?"
        content = (m.get("content") or "").strip().replace("\n", " ")
        if len(content) > max_chars_per_msg:
            content = content[:max_chars_per_msg] + "…"
        lines.append(f"- **{role}**: {content}")
    return "\n".join(lines)


def _fmt_reason_hint(ckpt: AgentCheckpoint) -> str:
    meta = ckpt.metadata or {}
    reason_detail = meta.get("interrupt_reason") or meta.get("reason_detail")
    if not reason_detail:
        return ""
    return f"## ⚠️ 上次中断线索\n{reason_detail}"


def _fmt_next_action(ckpt: AgentCheckpoint) -> str:
    return (
        "## ▶ 下一步\n"
        "1. 读上面的「⏳ 待完成」。\n"
        "2. 复用「📂 已有产物」而不是重新生成。\n"
        "3. 先更新 plan（用 plan_update 把当前步骤设为 in_progress），"
        "再动手。"
    )


# ── Public API ─────────────────────────────────────────────────────


def build_digest(ckpt: AgentCheckpoint,
                 *,
                 token_budget: int = 2000,
                 llm_call: Optional[Callable[[str], str]] = None) -> DigestResult:
    """Build a continuation digest from a checkpoint.

    If the deterministic text exceeds `token_budget` AND `llm_call` is
    provided, the completed-steps section is rewritten to a short prose
    summary by the LLM. LLM failure falls back to the uncompressed
    deterministic text (never raises).

    `llm_call(prompt) -> str` must be a blocking callable that returns
    the model's reply text. Pass a lambda wrapping your provider.
    """
    if ckpt is None:
        return DigestResult(text="", token_estimate=0,
                            sections_included=[], truncated=False)

    sections: list[tuple[str, str]] = []

    hdr = _fmt_header(ckpt)
    sections.append(("header", hdr))

    completed, unfinished = _fmt_plan_sections(ckpt.plan_json or {})
    if completed:
        sections.append(("completed", completed))
    if unfinished:
        sections.append(("unfinished", unfinished))

    artifacts = _fmt_artifacts(ckpt.artifact_refs or [])
    if artifacts:
        sections.append(("artifacts", artifacts))

    tail = _fmt_chat_tail(ckpt.chat_tail or [])
    if tail:
        sections.append(("chat_tail", tail))

    hint = _fmt_reason_hint(ckpt)
    if hint:
        sections.append(("reason_hint", hint))

    sections.append(("next_action", _fmt_next_action(ckpt)))

    text = "\n\n".join(body for _, body in sections)
    tokens = _approx_tokens(text)
    included = [name for name, _ in sections]

    llm_compressed = False
    truncated = False

    # LLM compression: only if over budget and callable provided.
    if tokens > token_budget and callable(llm_call) and completed:
        try:
            prompt = (
                "以下是一段 agent 执行历史的「已完成步骤」清单，请用不超过 "
                "180 字的中文要点总结（保留关键文件名/产物；用 '- ' 项目符号）：\n\n"
                + completed
            )
            summary = llm_call(prompt) or ""
            summary = summary.strip()
            if summary:
                # Rebuild with the compressed completed block.
                new_sections = []
                for name, body in sections:
                    if name == "completed":
                        new_sections.append(
                            (name, "## ✅ 已完成 (摘要)\n" + summary))
                    else:
                        new_sections.append((name, body))
                new_text = "\n\n".join(b for _, b in new_sections)
                new_tokens = _approx_tokens(new_text)
                # Only accept if it actually shrank.
                if new_tokens < tokens:
                    text = new_text
                    tokens = new_tokens
                    llm_compressed = True
        except Exception as e:
            logger.debug("digest LLM compression failed, falling back: %s", e)

    # Hard truncation backstop — we never want to blow budget by >2x.
    if tokens > token_budget * 2:
        keep_chars = token_budget * 2 * CHARS_PER_TOKEN_EST
        text = text[:keep_chars] + "\n…(truncated for budget)"
        tokens = _approx_tokens(text)
        truncated = True

    return DigestResult(
        text=text,
        token_estimate=tokens,
        sections_included=included,
        truncated=truncated,
        llm_compressed=llm_compressed,
    )


def update_checkpoint_digest(checkpoint_id: str,
                             *,
                             token_budget: int = 2000,
                             llm_call: Optional[Callable[[str], str]] = None
                             ) -> Optional[DigestResult]:
    """Build a digest and persist it onto the checkpoint row.

    Returns the DigestResult, or None if the checkpoint doesn't exist.
    """
    store = get_store()
    c = store.load(checkpoint_id)
    if c is None:
        return None
    result = build_digest(c, token_budget=token_budget, llm_call=llm_call)
    try:
        store.update_digest(checkpoint_id, result.text)
    except Exception as e:
        logger.warning("update_checkpoint_digest: store write failed: %s", e)
    return result
