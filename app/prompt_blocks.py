"""Prompt block library — declarative system prompt assembly.

为什么要这一层
==============
今天 ``agent._build_static_system_prompt`` 是 ~400 行命令式代码,把 13+ 个
块无条件 ``parts.append`` 拼起来。同一个 agent 在闲聊(`casual_chat`)和
做 PPT(`pptx_authoring`)时,都装入同样的 25+ 条规则。后果:

  * system prompt 7-8K token / turn,中位数 4-7K 是无效内容
  * cache prefix 不稳定(persona 改、project 文件改 → 全 prefix 失效)
  * 操作员改一行规则,无法判断影响哪些 turn
  * 简单 chat 也带"远程协作 / skill 协议 / attachment_contract"等淹没注意力

本模块提供的能力
================
把每个块表达成 ``PromptBlock`` 数据,带 ``BlockGate`` 条件元数据。装配
函数读条件 → 按当前 turn 上下文(scope tags / agent state / ctx_type)决定
装入哪些块。配套的 dry-run 日志让运营在不切流量的情况下观察"v2 会装入
哪些块、漏装哪些"。

设计约束
========
* **不引入 LLM 调用** — 装配纯数据计算,微秒级
* **向后兼容** — v1 ``compose_full_prompt`` 不动,本模块是平行 v2
* **可观测** — 每次装配产生 ``BlockAssemblyResult``,记录装入 / 跳过的
  块 id,接到 ``logger.info`` 即可定位 prefix 漂移问题
* **声明式** — block 定义集中在一处,operator 改条件不需要懂控制流

使用
====

::

    from app.prompt_blocks import BlockGate, PromptBlock, AssemblyContext
    from app.system_prompt_v2 import assemble_static_prompt

    blocks = [
        PromptBlock(
            id="file_display",
            text="<file_display>...rules...</file_display>",
            applies_when=BlockGate(
                has_tools_in={"write_file", "edit_file", "create_pptx"},
            ),
            priority=40,
        ),
        # ... 更多块
    ]

    ctx = AssemblyContext(
        scope_tags=["pptx_authoring"],
        granted_tools={"write_file", "create_pptx", "memory_recall"},
        granted_skills={"pptx-author", "file-ops"},
        role_kind="coder",
        ctx_type="solo",
    )

    text, result = assemble_static_prompt(blocks, ctx)
    # text   → 拼接好的 prompt
    # result → BlockAssemblyResult(included=[...], excluded=[...], scope=[...])
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# ──────────────────────────────────────────────────────────────────────
# AssemblyContext — 装配时的上下文信息(只读)
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AssemblyContext:
    """装配时刻的上下文。所有 BlockGate 都基于这个 context 求值。

    Fields
    ------
    scope_tags     — scope_detector 输出的 tag 列表(如 ['pptx_authoring'])
    granted_tools  — 当前 agent 实际拿到的工具名集合(已经过 tool_capabilities 过滤)
    granted_skills — 当前 agent 实际拿到的 skill id 集合
    role_kind      — agent 的 role 大类(如 'coder' / 'analyst' / 'pm')
    ctx_type       — 'solo' | 'project' | 'meeting'
    has_image      — 当前 turn 的 user message 是否含图片(多模态条件)
    extras         — 自定义条件用,custom callable 可读
    """

    scope_tags: tuple[str, ...] = ()
    granted_tools: frozenset[str] = frozenset()
    granted_skills: frozenset[str] = frozenset()
    role_kind: str = ""
    ctx_type: str = "solo"
    has_image: bool = False
    extras: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def make(
        cls,
        scope_tags: list[str] | tuple[str, ...] | None = None,
        granted_tools: set[str] | frozenset[str] | None = None,
        granted_skills: set[str] | frozenset[str] | None = None,
        role_kind: str = "",
        ctx_type: str = "solo",
        has_image: bool = False,
        extras: dict[str, Any] | None = None,
    ) -> "AssemblyContext":
        """Builder 兼顾常见可变类型 → frozen dataclass 转换。"""
        return cls(
            scope_tags=tuple(scope_tags or ()),
            granted_tools=frozenset(granted_tools or ()),
            granted_skills=frozenset(granted_skills or ()),
            role_kind=role_kind or "",
            ctx_type=ctx_type or "solo",
            has_image=bool(has_image),
            extras=dict(extras or {}),
        )


# ──────────────────────────────────────────────────────────────────────
# BlockGate — 装入条件
# ──────────────────────────────────────────────────────────────────────


@dataclass
class BlockGate:
    """装入条件,所有维度逻辑 AND。维度为 None 表示该维度无约束。

    Fields
    ------
    scopes        — 必须有至少一个 scope tag 命中(set 与 ctx.scope_tags 交集非空)
    has_tools_in  — 必须有至少一个工具命中(set 与 ctx.granted_tools 交集非空)
    has_skill_in  — 必须有至少一个 skill 命中
    role_kind_in  — agent 的 role_kind 必须在这个集合里
    ctx_type_in   — agent 的 ctx_type 必须在这个集合里
    requires_image — True 表示当前 turn 必须含图片;False 表示必须不含;None 不约束
    custom        — 兜底自定义,签名 ``Callable[[AssemblyContext], bool]``
    """

    scopes: Optional[set[str]] = None
    has_tools_in: Optional[set[str]] = None
    has_skill_in: Optional[set[str]] = None
    role_kind_in: Optional[set[str]] = None
    ctx_type_in: Optional[set[str]] = None
    requires_image: Optional[bool] = None
    custom: Optional[Callable[[AssemblyContext], bool]] = None

    def matches(self, ctx: AssemblyContext) -> bool:
        """返回 True 表示所有非 None 维度都通过。短路求值。"""
        if self.scopes is not None:
            if not (self.scopes & set(ctx.scope_tags)):
                return False
        if self.has_tools_in is not None:
            if not (self.has_tools_in & ctx.granted_tools):
                return False
        if self.has_skill_in is not None:
            if not (self.has_skill_in & ctx.granted_skills):
                return False
        if self.role_kind_in is not None:
            if ctx.role_kind not in self.role_kind_in:
                return False
        if self.ctx_type_in is not None:
            if ctx.ctx_type not in self.ctx_type_in:
                return False
        if self.requires_image is not None:
            if bool(self.requires_image) != bool(ctx.has_image):
                return False
        if self.custom is not None:
            try:
                if not self.custom(ctx):
                    return False
            except Exception:
                # custom callable 异常 → 视为不通过(保守),不影响装配
                return False
        return True


def Always() -> BlockGate:
    """语义糖:一个永远通过的 gate(所有维度 None)。"""
    return BlockGate()


# ──────────────────────────────────────────────────────────────────────
# PromptBlock — 一个 prompt 块的定义
# ──────────────────────────────────────────────────────────────────────


# text 字段:可以是 str(静态)或者函数(根据 agent / ctx 动态构造)。
# 函数签名:Callable[[AssemblyContext], str]。返回空串等价于"该 turn 无内容"。
TextSource = str | Callable[[AssemblyContext], str]


@dataclass
class PromptBlock:
    """一个 prompt 块。

    Fields
    ------
    id            — 唯一标识(打日志 / 度量 / A-B test 用)。约定 snake_case。
    text          — 块内容(str 或 ``Callable[[AssemblyContext], str]``)。
                    函数返回 "" 表示这次没有内容,等价于跳过装入。
    applies_when  — ``BlockGate``,Always() 表示永远装入。
    priority      — 装配排序键。小的在前。建议:
                       10 identity / 入门
                       20-30 平台规则(tools / knowledge)
                       30-40 persona
                       40-60 上下文 / contracts
                       60-80 specialty
    cache_anchor  — True 表示这个块装完后,Anthropic 客户端可以加 cache_control
                    边界(用于稳定 prefix)。装配函数返回 anchor 位置列表给
                    上层去标记。
    description   — 给 reviewer / operator UI 看的人话描述。
    owner         — 责任人 / 责任组(`tools` / `meeting` / `pm` / ...),可选
    """

    id: str
    text: TextSource
    applies_when: BlockGate = field(default_factory=Always)
    priority: int = 50
    cache_anchor: bool = False
    description: str = ""
    owner: str = ""

    def render(self, ctx: AssemblyContext) -> str:
        """返回该 block 的字符串内容,空串表示无内容。"""
        if isinstance(self.text, str):
            return self.text
        try:
            out = self.text(ctx)
        except Exception:
            # 动态构造失败 → 跳过,不影响其他 block
            return ""
        return out if isinstance(out, str) else ""


# ──────────────────────────────────────────────────────────────────────
# 装配结果
# ──────────────────────────────────────────────────────────────────────


@dataclass
class BlockAssemblyResult:
    """装配产物的元数据,用于日志 / 度量 / 调试。

    Fields
    ------
    included         — 装入的 block id(按 priority 升序)
    excluded         — 跳过的 block id 与原因 [(id, reason)]
    cache_anchor_ids — 标记了 cache_anchor=True 的 block id 列表
    scope_tags       — 当时的 scope tags
    total_chars      — 拼接结果总字符数
    """

    included: list[str] = field(default_factory=list)
    excluded: list[tuple[str, str]] = field(default_factory=list)
    cache_anchor_ids: list[str] = field(default_factory=list)
    scope_tags: tuple[str, ...] = ()
    total_chars: int = 0

    def to_log_dict(self) -> dict:
        """适合直接 ``logger.info("[prompt_v2] %s", res.to_log_dict())`` 的 dict。"""
        return {
            "in": self.included,
            "out_count": len(self.excluded),
            "out_ids": [eid for eid, _ in self.excluded],
            "anchors": self.cache_anchor_ids,
            "scope": list(self.scope_tags),
            "chars": self.total_chars,
        }


__all__ = [
    "AssemblyContext",
    "BlockGate",
    "Always",
    "PromptBlock",
    "BlockAssemblyResult",
    "TextSource",
]
