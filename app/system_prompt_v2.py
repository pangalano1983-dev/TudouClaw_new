"""System prompt assembler v2 — declarative block-based assembly.

Stage A (dry-run) 阶段
======================
本模块**不替换** ``agent._build_static_system_prompt`` 的真实返回值。
它跟 v1 并行计算,产出 ``BlockAssemblyResult`` 写到 ``tudou.prompt_v2``
logger,运营按一两周窗口观察:

  * v2 选了哪些块、跳了哪些块、跳的原因
  * 同 scope 多次 turn 之间 cache prefix 是否真的稳定
  * v1 和 v2 文本的 diff(找漏装 / 误装)

Stage B/C 切流量后,本模块返回值才会成为真 system prompt。届时切换通过
ENV ``TUDOU_PROMPT_V2=1`` + 按 role 灰度。

设计要点
========
* 装配函数纯函数(给 blocks + ctx → 输出 + result)
* 不读文件、不调网络、不依赖 hub — 一切上下文从 AssemblyContext 拿
* 默认按 priority 升序;同 priority 按 block.id 字母序保稳定
* exclusion reason 用人话写,便于运营定位"为什么没装这块"
"""

from __future__ import annotations

import logging
from typing import Iterable

from .prompt_blocks import (
    AssemblyContext,
    BlockAssemblyResult,
    PromptBlock,
)

logger = logging.getLogger("tudou.prompt_v2")


# ──────────────────────────────────────────────────────────────────────
# Core assembly
# ──────────────────────────────────────────────────────────────────────


def _exclusion_reason(block: PromptBlock, ctx: AssemblyContext) -> str:
    """对运营友好的"为什么这个块没装"原因。"""
    g = block.applies_when
    if g.scopes is not None and not (g.scopes & set(ctx.scope_tags)):
        return f"scope_mismatch: needs {sorted(g.scopes)} got {list(ctx.scope_tags)}"
    if g.has_tools_in is not None and not (g.has_tools_in & ctx.granted_tools):
        return f"missing_tool: needs any of {sorted(g.has_tools_in)}"
    if g.has_skill_in is not None and not (g.has_skill_in & ctx.granted_skills):
        return f"missing_skill: needs any of {sorted(g.has_skill_in)}"
    if g.role_kind_in is not None and ctx.role_kind not in g.role_kind_in:
        return f"role_mismatch: needs {sorted(g.role_kind_in)} got {ctx.role_kind!r}"
    if g.ctx_type_in is not None and ctx.ctx_type not in g.ctx_type_in:
        return f"ctx_mismatch: needs {sorted(g.ctx_type_in)} got {ctx.ctx_type!r}"
    if g.requires_image is not None and bool(g.requires_image) != bool(ctx.has_image):
        return f"image_mismatch: needs has_image={g.requires_image}"
    if g.custom is not None:
        return "custom_gate_returned_false"
    return "unknown"


def assemble_static_prompt(
    blocks: Iterable[PromptBlock],
    ctx: AssemblyContext,
    *,
    separator: str = "\n\n",
) -> tuple[str, BlockAssemblyResult]:
    """按 ctx 装配 blocks。返回 (拼接好的字符串, result 元数据)。

    流程:
      1. 按 priority 升序、id 字母序排序
      2. 逐块判 ``applies_when.matches(ctx)``
      3. 通过 → 调 ``render(ctx)`` 取文本;非空才装入
      4. 失败 → 记 (id, reason) 到 result.excluded
      5. 拼接 + 返回
    """
    # 排序 — priority 升序;同 priority 按 id 字母,保装配稳定可重现
    sorted_blocks = sorted(blocks, key=lambda b: (b.priority, b.id))

    result = BlockAssemblyResult(scope_tags=tuple(ctx.scope_tags))
    parts: list[str] = []

    for block in sorted_blocks:
        if not block.applies_when.matches(ctx):
            result.excluded.append((block.id, _exclusion_reason(block, ctx)))
            continue
        text = block.render(ctx)
        if not text or not text.strip():
            # render 返回空 → 也算 excluded(empty render)
            result.excluded.append((block.id, "empty_render"))
            continue
        parts.append(text)
        result.included.append(block.id)
        if block.cache_anchor:
            result.cache_anchor_ids.append(block.id)

    full_text = separator.join(parts)
    result.total_chars = len(full_text)
    return full_text, result


def assemble_with_log(
    blocks: Iterable[PromptBlock],
    ctx: AssemblyContext,
    *,
    separator: str = "\n\n",
    log_level: int = logging.INFO,
    agent_id: str = "",
) -> tuple[str, BlockAssemblyResult]:
    """跟 ``assemble_static_prompt`` 一样,但额外打一行装配日志。

    日志格式:::

      [prompt_v2] agent=ag-xx scope=['pptx_authoring'] in=12 out=5
        included=['identity', 'tool_rules', ...]
        excluded_ids=['attachment_contract', 'image_display', ...]
        chars=4321
    """
    text, result = assemble_static_prompt(blocks, ctx, separator=separator)
    try:
        logger.log(
            log_level,
            "[prompt_v2] agent=%s scope=%s in=%d out=%d chars=%d "
            "included=%s excluded_ids=%s",
            (agent_id or "")[:8] or "-",
            list(result.scope_tags),
            len(result.included), len(result.excluded),
            result.total_chars,
            result.included,
            [eid for eid, _ in result.excluded],
        )
    except Exception:
        # 日志失败不影响装配
        pass
    return text, result


# ──────────────────────────────────────────────────────────────────────
# Diff utilities — 给 dry-run 阶段对比 v1 / v2 用
# ──────────────────────────────────────────────────────────────────────


def diff_summary(v1_text: str, v2_text: str) -> dict:
    """v1 / v2 文本差异的高层摘要(不打全 diff,长 prompt 会刷屏)。"""
    v1_lines = (v1_text or "").splitlines()
    v2_lines = (v2_text or "").splitlines()
    only_v1 = set(v1_lines) - set(v2_lines)
    only_v2 = set(v2_lines) - set(v1_lines)
    return {
        "v1_chars": len(v1_text or ""),
        "v2_chars": len(v2_text or ""),
        "delta_chars": len(v2_text or "") - len(v1_text or ""),
        "v1_lines": len(v1_lines),
        "v2_lines": len(v2_lines),
        "only_in_v1_count": len(only_v1),
        "only_in_v2_count": len(only_v2),
        # 避免序列化大 prompt — 只取前 5 行 sample
        "only_in_v1_sample": list(only_v1)[:5],
        "only_in_v2_sample": list(only_v2)[:5],
    }


__all__ = [
    "assemble_static_prompt",
    "assemble_with_log",
    "diff_summary",
    "logger",
]
