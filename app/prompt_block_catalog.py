"""Default prompt block catalog — 把当前 ``agent._build_static_system_prompt``
里所有 ``parts.append`` 的块,转成有 ``BlockGate`` 元数据的
``PromptBlock`` 列表。

Stage A 范围:13 个块 metadata,2 个 placeholder
Stage B(本文件当前状态):**全部 18 个块用真实文本**,placeholder 已替换
================================================================
* **块 id + 装入条件**:精确
* **块 text**:全部从 ``app.system_prompt`` 引用单一来源常量/函数;
  agent.py inline 块(file_display_long / workspace_context_full /
  image_display_long / attachment_contract / plan_protocol)对应文本已
  抽到 system_prompt.py
* **不读文件 / 不查 hub**:catalog 里所有块都是纯数据 / lambda(ctx),不
  读任何 IO。文件类内容(PROJECT_CONTEXT.md / granted_skills_roster 等)
  留给 caller 在构造 ``AssemblyContext`` 前 prefetch 进 ``extras``。

跟 v1 的对照(v1=agent._build_static_system_prompt 的 parts 顺序)
=================================================================
* v1 emit 的所有内容,catalog 都覆盖了对应的 PromptBlock
* v1 有的 **重复**(scene_prompts 在最前面被 prepend 一次,又在
  compose_full_prompt 内 build_settings_block 时再 emit 一次)→ catalog
  只 emit 一次,这是 v2 的**第一个有意去重**

未来扩展
========
* operator 可在 settings 里追加块(scene_prompts 已有结构,Stage B 后续
  把每个条目变成一个 PromptBlock 加到 catalog)
* 块的 owner 字段:让 reviewer 知道改某块要找谁
"""

from __future__ import annotations

from typing import Callable

from . import system_prompt as _sp
from .prompt_blocks import (
    AssemblyContext,
    Always,
    BlockGate,
    PromptBlock,
)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _use_zh(ctx: AssemblyContext) -> bool:
    """根据 extras 里的 language 字段判断是否用中文版本。默认中文优先。"""
    lang = (ctx.extras.get("language") or "auto").lower()
    if lang.startswith("zh"):
        return True
    if lang.startswith("en"):
        return False
    # auto:看 agent persona 字段是否有大量中文(让 caller 提前判好,
    # 这里只看 extras['use_zh'] 兜底)
    return bool(ctx.extras.get("use_zh", True))


# 工具集合 — 触发 file_display 长版的工具
_FILE_PRODUCING_TOOLS = frozenset({
    "write_file", "edit_file", "create_pptx", "create_pptx_advanced",
    "create_video", "web_screenshot", "desktop_screenshot",
})

# 触发 attachment_contract 的工具
_MESSAGING_TOOLS = frozenset({
    "send_email", "send_message", "ack_message", "reply_message",
})


# ──────────────────────────────────────────────────────────────────────
# Block definitions(13+ blocks)
# ──────────────────────────────────────────────────────────────────────


def _identity_text(ctx: AssemblyContext) -> str:
    name = ctx.extras.get("agent_name") or ""
    role = ctx.extras.get("agent_role") or ""
    language = ctx.extras.get("language") or "auto"
    if not name or not role:
        return ""
    return _sp._identity_line(name, role, language)


def _language_directive_text(ctx: AssemblyContext) -> str:
    language = ctx.extras.get("language") or "auto"
    return _sp._language_directive(language)


def _tool_rules_text(ctx: AssemblyContext) -> str:
    return _sp._TOOL_RULES_ZH if _use_zh(ctx) else _sp._TOOL_RULES_EN


def _knowledge_rules_text(ctx: AssemblyContext) -> str:
    return _sp._KNOWLEDGE_RULES_ZH if _use_zh(ctx) else _sp._KNOWLEDGE_RULES_EN


def _image_display_text(ctx: AssemblyContext) -> str:
    return _sp._IMAGE_DISPLAY_ZH if _use_zh(ctx) else _sp._IMAGE_DISPLAY_EN


def _workspace_context_text(ctx: AssemblyContext) -> str:
    """复用 system_prompt._workspace_context — 数据从 ctx.extras 拿。"""
    return _sp._workspace_context(
        ctx_type=ctx.ctx_type,
        use_zh=_use_zh(ctx),
        working_dir=ctx.extras.get("working_dir") or "",
        shared_workspace=ctx.extras.get("shared_workspace") or "",
        project_name=ctx.extras.get("project_name") or "",
        project_id=ctx.extras.get("project_id") or "",
        meeting_id=ctx.extras.get("meeting_id") or "",
    )


def _persona_text(ctx: AssemblyContext) -> str:
    """从 ctx.extras 拿 system_prompt / soul_md / custom_instructions。"""
    return _sp.build_persona_block(
        system_prompt=ctx.extras.get("agent_system_prompt") or "",
        soul_md=ctx.extras.get("agent_soul_md") or "",
        custom_instructions=ctx.extras.get("agent_custom_instructions") or "",
        use_zh=_use_zh(ctx),
    )


def _settings_block_text(ctx: AssemblyContext) -> str:
    """operator-configured scene_prompts(系统级 + 角色级)。

    Stage A:整体复用现有 build_settings_block(已有 role 过滤)。
    Stage B:把 scene_prompts schema 加 ``scopes: [...]``,逐条变 PromptBlock。
    """
    return _sp.build_settings_block(agent_role=ctx.extras.get("agent_role") or "")


def _project_context_text(ctx: AssemblyContext) -> str:
    """PROJECT_CONTEXT.md / TUDOU_CLAW.md / CLAW.md / README.md 内容。

    数据由 caller prefetch 到 ``ctx.extras['project_context_files']`` —
    list[(filename, content)]。空列表 → 块自动跳过(empty_render)。
    """
    files: list = ctx.extras.get("project_context_files") or []
    if not files:
        return ""
    parts: list[str] = []
    for entry in files:
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            continue
        fname, content = entry
        if not content:
            continue
        # 跟 agent.py 现有块格式保持一致
        parts.append(
            f"<project_context file=\"{fname}\">\n"
            f"{content}\n"
            f"</project_context>"
        )
    return "\n\n".join(parts)


def _model_guidance_text(ctx: AssemblyContext) -> str:
    """model-specific guidance — caller prefetch 到 extras['model_guidance']。"""
    return ctx.extras.get("model_guidance") or ""


def _retrieval_protocol_text(ctx: AssemblyContext) -> str:
    """RAG advisor 的 retrieval protocol — caller prefetch 到
    extras['retrieval_protocol']。RAG-bound advisor agent 才会有。"""
    return ctx.extras.get("retrieval_protocol") or ""


def _file_display_short_text(ctx: AssemblyContext) -> str:
    """SHORT-form file_display — 镜像 ``compose_full_prompt`` 里的 _FILE_DISPLAY,
    跟 LONG 版互为补充(LONG 加 detail rules + 中文摘要)。Always 装入,
    跟 v1 ``compose_full_prompt`` 行为一致。"""
    return _sp._FILE_DISPLAY


def _file_display_long_text(ctx: AssemblyContext) -> str:
    """LONG-form file_display — 加 5 条详细规则 + 中文摘要。仅当 agent 有
    文件产出工具时装,无文件产出工具的 agent 无须背这条 contract。"""
    return _sp._FILE_DISPLAY_LONG


def _attachment_contract_text(ctx: AssemblyContext) -> str:
    """根据 ctx 选 zh / en 版,交回单一来源常量。"""
    return _sp._ATTACHMENT_CONTRACT_ZH if _use_zh(ctx) else _sp._ATTACHMENT_CONTRACT_EN


def _image_display_long_text(ctx: AssemblyContext) -> str:
    """LONG-form image_display — 含前端 markdown 路径渲染细节。"""
    return _sp._IMAGE_DISPLAY_LONG_ZH if _use_zh(ctx) else _sp._IMAGE_DISPLAY_LONG_EN


def _workspace_context_full_text(ctx: AssemblyContext) -> str:
    """LONG-form workspace context with deliverable routing — 来自 agent.py
    inline,现在统一从 system_prompt 拉。空 working_dir + 空 shared 时返回
    空串(assembler 自动跳过)。"""
    return _sp._workspace_context_long(
        ctx_type=ctx.ctx_type,
        use_zh=_use_zh(ctx),
        working_dir=ctx.extras.get("working_dir") or "",
        shared_workspace=ctx.extras.get("shared_workspace") or "",
        project_name=ctx.extras.get("project_name") or "",
        project_id=ctx.extras.get("project_id") or "",
    )


def _plan_protocol_text(ctx: AssemblyContext) -> str:
    """任务分解 + ✓ 步骤汇报协议。当前只有中文版(原 inline 也只有中文)。
    驱动 UI TASK QUEUE 面板,所有 agent 都装。"""
    return _sp._PLAN_PROTOCOL_ZH


def _granted_skills_roster_text(ctx: AssemblyContext) -> str:
    """已装配 skill roster — caller prefetch 到 extras['granted_skills_roster']。
    内容是字符串(由 ``_build_granted_skills_roster`` 计算好;catalog 不
    自己读 skill registry 避免 IO)。空时跳过。"""
    return ctx.extras.get("granted_skills_roster") or ""


# ──────────────────────────────────────────────────────────────────────
# Default catalog
# ──────────────────────────────────────────────────────────────────────


DEFAULT_BLOCKS: list[PromptBlock] = [
    PromptBlock(
        id="identity",
        text=_identity_text,
        applies_when=Always(),
        priority=10,
        cache_anchor=True,
        description="身份陈述:'You are <name>, <role>.'",
        owner="platform",
    ),
    PromptBlock(
        id="language_directive",
        text=_language_directive_text,
        applies_when=Always(),
        priority=15,
        description="语言偏好:e.g. '请用中文回答'",
        owner="platform",
    ),
    PromptBlock(
        id="tool_rules",
        text=_tool_rules_text,
        applies_when=Always(),
        priority=20,
        cache_anchor=True,
        description="工具使用基本规则(并行 / plan_update / handoff)",
        owner="platform",
    ),
    PromptBlock(
        id="knowledge_rules",
        text=_knowledge_rules_text,
        applies_when=Always(),
        priority=25,
        description="wiki_ingest / knowledge_lookup 规则",
        owner="platform",
    ),
    PromptBlock(
        id="file_display_short",
        text=_file_display_short_text,
        applies_when=Always(),
        priority=30,
        description="<file_display> 短版 — 跟 v1 ``compose_full_prompt`` 一致,所有 agent 装",
        owner="ui",
    ),
    PromptBlock(
        id="image_display",
        text=_image_display_text,
        applies_when=BlockGate(
            # 不在明显纯文字场景装 — 注意"casual_chat"也不需要(短话本来不该
            # 引入图片协议)
            scopes={
                "data_analysis", "tech_review", "prd_writing",
                "pptx_authoring", "one_on_one",
            },
        ),
        priority=32,
        description="图片显示协议(短版) — markdown 图片语法 + 工作区路径",
        owner="ui",
    ),
    PromptBlock(
        id="workspace_context_basic",
        text=_workspace_context_text,
        applies_when=BlockGate(
            # 当 working_dir / shared_workspace 都空时,_workspace_context
            # 会返回空,assembler 自动当 empty_render 跳过
        ),
        priority=40,
        description="<workspace_context> 短版 — 写文件去哪、共享/私有目录",
        owner="platform",
    ),
    PromptBlock(
        id="persona",
        text=_persona_text,
        applies_when=Always(),  # 三字段都空时 build_persona_block 返回空
        priority=50,
        cache_anchor=True,
        description="agent 人格三件套:身份 / 沟通风格 / 补充指令",
        owner="agent_owner",
    ),
    PromptBlock(
        id="retrieval_protocol",
        text=_retrieval_protocol_text,
        applies_when=BlockGate(
            custom=lambda c: bool(c.extras.get("retrieval_protocol")),
        ),
        priority=55,
        description="RAG advisor 检索协议 — 仅 profile.rag_* 配置时装入",
        owner="rag",
    ),
    PromptBlock(
        id="settings_block",
        text=_settings_block_text,
        applies_when=Always(),  # build_settings_block 内部已 role 过滤
        priority=58,
        description="operator-configured scene_prompts(已有 role 过滤)",
        owner="operator",
    ),
    PromptBlock(
        id="file_display_long",
        text=_file_display_long_text,
        applies_when=BlockGate(
            has_tools_in=set(_FILE_PRODUCING_TOOLS),
        ),
        priority=60,
        description="<file_display> 长版协议 — 仅当 agent 有文件产出工具时装",
        owner="ui",
    ),
    PromptBlock(
        id="workspace_context_full",
        text=_workspace_context_full_text,
        applies_when=BlockGate(
            # working_dir / shared_workspace 都空时返回空 → 自动跳过
        ),
        priority=62,
        description="<workspace_context> 长版 — deliverable routing rules + 子 agent 提示",
        owner="platform",
    ),
    PromptBlock(
        id="project_context_md",
        text=_project_context_text,
        applies_when=BlockGate(
            ctx_type_in={"project", "meeting"},
            custom=lambda c: bool(c.extras.get("project_context_files")),
        ),
        priority=65,
        description="PROJECT_CONTEXT.md / TUDOU_CLAW.md 内容(项目/会议模式)",
        owner="platform",
    ),
    PromptBlock(
        id="model_guidance",
        text=_model_guidance_text,
        applies_when=BlockGate(
            custom=lambda c: bool(c.extras.get("model_guidance")),
        ),
        priority=70,
        description="model-specific guidance(o1 / qwen3 等模型特定提示)",
        owner="platform",
    ),
    PromptBlock(
        id="image_display_long",
        text=_image_display_long_text,
        applies_when=BlockGate(
            # v1 unconditional emit。catalog 也保持 Always — 后续可加
            # has_tools_in={create_pptx,...} 进一步收紧。
        ),
        priority=72,
        description="<image_display> 长版 — markdown 图片语法 + 前端渲染细节",
        owner="ui",
    ),
    PromptBlock(
        id="attachment_contract",
        text=_attachment_contract_text,
        applies_when=BlockGate(
            has_tools_in=set(_MESSAGING_TOOLS),
        ),
        priority=75,
        description="<attachment_contract> — 调发送类工具时必须把文件放 attachments",
        owner="messaging",
    ),
    PromptBlock(
        id="plan_protocol",
        text=_plan_protocol_text,
        applies_when=Always(),  # v1 unconditional;只有 zh 版本
        priority=80,
        description="任务分解 + ✓ 步骤汇报协议(驱动 TASK QUEUE 面板)",
        owner="ui",
    ),
    PromptBlock(
        id="granted_skills_roster",
        text=_granted_skills_roster_text,
        applies_when=BlockGate(
            # 由 caller prefetch 到 extras;空时跳过
            custom=lambda c: bool(c.extras.get("granted_skills_roster")),
        ),
        priority=85,
        description="已装配 skill roster — list[skill] one-line-per-skill,装在静态 prompt 末尾",
        owner="platform",
    ),
]


def get_default_catalog() -> list[PromptBlock]:
    """返回默认 block catalog 的副本。修改副本不影响他人。"""
    return list(DEFAULT_BLOCKS)


def block_by_id(catalog: list[PromptBlock], block_id: str) -> PromptBlock | None:
    for b in catalog:
        if b.id == block_id:
            return b
    return None


__all__ = [
    "DEFAULT_BLOCKS",
    "get_default_catalog",
    "block_by_id",
]
