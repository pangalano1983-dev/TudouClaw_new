# Phase 2b — System Prompt 块化条件装入

> 状态:**Stage A + Stage B Step 1 已交付**。
> Stage B 余项(scene_prompts schema + 1-2 周观察)+ Stage C(切流量)留下个 session。

## 为什么做这件事

不只是省 token。完整收益分布:

| 收益 | 量级 | 衡量方式 |
|---|---|---|
| LLM 月账单砍约一半(~50%) | 高 | 直接对账 |
| cache 命中率 25% → 65-75% | 高 | Phase 1 度量 (`get_token_totals().cache_hit_rate`) |
| TTFT(首 token 延迟)减半(简单场景) | 中-高 | 客户端打点 |
| LLM 指令服从更准 | 中 | 主观,人审 / 对比 |
| 装入日志的可观测性 | 中 | `tudou.prompt_v2` logger 直接看 |
| Prompt 实验成本 1/10 | 中 | 改完容易看到迭代节奏变化 |
| 块化打开的长期演化空间 | 高(战略性)| 难量化 |
| 运营 / 灰度能力的精细化 | 中-高 | 出 bug 时是质变 |

更准确的描述:**这是一次把 system prompt 从"硬编码字符串拼接"升级为"声明式数据"的架构改造**。token 节省是第一阶效果,真正的杠杆是把 prompt 变成可度量、可灰度、可独立演化的资产。

---

## 现状(Phase 1+3+4 之前)

```
agent._build_static_system_prompt()   →  STATIC(hash 缓存)
agent_llm._build_dynamic_context()    →  DYNAMIC(per turn)
```

STATIC 部分 13+ 个 `parts.append`,**全部无条件装入**:

| # | 块 | 条件 |
|---|---|---|
| 1 | identity / tool_rules / knowledge_rules / file_display_short / image_display | 全装 |
| 2 | scene_prompts(operator) | ✅ 已有 role 过滤,无 scope 过滤 |
| 3 | persona | 全装 |
| 4 | retrieval_protocol(RAG advisor) | ✅ 已条件 |
| 5 | `<file_display>` 长版 | 全装(700 字符) |
| 6 | PROJECT_CONTEXT.md 等 | 全装 |
| 7 | model-specific guidance | ✅ 已条件 |
| 8 | workspace_context ZH+EN 长版 | 全装 |
| 9 | `<attachment_contract>` | 全装(700 字符) |
| 10+ | 其他 inline 块 | 全装 |

**典型 STATIC 大小:4000-8000 tokens / agent / turn**。

---

## 目标方案(Stage A 已实现)

### 数据结构(`app/prompt_blocks.py`)

```python
@dataclass
class BlockGate:
    """全部 AND。维度为 None 表示该维度无约束。"""
    scopes:        set[str] | None = None
    has_tools_in:  set[str] | None = None
    has_skill_in:  set[str] | None = None
    role_kind_in:  set[str] | None = None
    ctx_type_in:   set[str] | None = None
    requires_image: bool | None = None
    custom: Callable | None = None

@dataclass
class PromptBlock:
    id: str
    text: str | Callable[[AssemblyContext], str]
    applies_when: BlockGate
    priority: int = 50
    cache_anchor: bool = False
    description: str = ""
    owner: str = ""
```

### 装配函数(`app/system_prompt_v2.py`)

```python
def assemble_static_prompt(blocks, ctx) -> tuple[str, BlockAssemblyResult]:
    """按 ctx 装配 blocks,返回 (拼接结果, 元数据)。"""

def assemble_with_log(blocks, ctx, *, agent_id="") -> ...:
    """同上 + 自动打 INFO 日志(tudou.prompt_v2)。"""

def diff_summary(v1_text, v2_text) -> dict:
    """v1/v2 文本差异的高层摘要。"""
```

### 默认 catalog(`app/prompt_block_catalog.py`)

**18 个 PromptBlock**,priority 10-85(Stage B 把 Stage A 的 13 块 + 2 个
placeholder 真实化,新增 5 块完整覆盖 v1 的所有 inline 块):

| id | priority | 条件 | text 来源 |
|---|---|---|---|
| identity | 10 ⚓ | Always | system_prompt._identity_line |
| language_directive | 15 | Always | system_prompt._language_directive |
| tool_rules | 20 ⚓ | Always | system_prompt._TOOL_RULES_ZH/EN |
| knowledge_rules | 25 | Always | system_prompt._KNOWLEDGE_RULES_ZH/EN |
| **file_display_short** 🆕 | 30 | Always | system_prompt._FILE_DISPLAY |
| image_display | 32 | scopes={data_analysis, tech_review, prd_writing, pptx_authoring, one_on_one} | system_prompt._IMAGE_DISPLAY_ZH/EN |
| workspace_context_basic | 40 | empty render auto-skip | system_prompt._workspace_context |
| persona | 50 ⚓ | Always(三字段空时空 render)| system_prompt.build_persona_block |
| retrieval_protocol | 55 | extras['retrieval_protocol'] 非空 | caller prefetch |
| settings_block | 58 | Always(已有 role 过滤)| system_prompt.build_settings_block |
| file_display_long | 60 | has_tools_in={write_file, edit_file, create_pptx, ...} | **system_prompt._FILE_DISPLAY_LONG** ✅ Stage B 真实文本 |
| **workspace_context_full** 🆕 | 62 | empty render auto-skip(working_dir+shared 都空才跳)| system_prompt._workspace_context_long |
| project_context_md | 65 | ctx_type∈{project,meeting} + extras['project_context_files'] 非空 | caller prefetch |
| model_guidance | 70 | extras['model_guidance'] 非空 | caller prefetch |
| **image_display_long** 🆕 | 72 | Always(后续可加 has_tools_in 收紧)| system_prompt._IMAGE_DISPLAY_LONG_ZH/EN |
| attachment_contract | 75 | has_tools_in={send_email, send_message, ...} | **system_prompt._ATTACHMENT_CONTRACT_ZH/EN** ✅ Stage B 真实文本 |
| **plan_protocol** 🆕 | 80 | Always(只有中文版)| system_prompt._PLAN_PROTOCOL_ZH |
| **granted_skills_roster** 🆕 | 85 | extras['granted_skills_roster'] 非空 | caller prefetch(_build_granted_skills_roster) |

⚓ = `cache_anchor=True`(prefix 稳定边界标记)。
🆕 = Stage B 新增。

### Dry-run wire-in(已加,默认 OFF)

```bash
# 开启(只观察,不切流量)
export TUDOU_PROMPT_V2_DRYRUN=1
```

每次 `_build_static_system_prompt` 被调,会**额外**算一遍 v2,日志:

```
[prompt_v2] agent=ag-12345 scope=[] in=8 out=5 chars=4321 included=[...] excluded_ids=[...]
[prompt_v2_diff] agent=ag-12345 v1=7400ch v2=4500ch delta=-2900ch v1_only_lines=42 v2_only_lines=3
```

v1 返回值不变 — agent 行为完全不变。

---

## 三场景 token 节省

### Stage A 实测预期(基于 13 块 + placeholder)
- casual_chat:~66%、data_analysis:~26%、pptx_authoring:~31%、加权平均:~39%

### Stage B 实测(2026-04-26,18 块 + 真实文本 + dry-run)

通过 `TUDOU_PROMPT_V2_DRYRUN=1` 跑 3 个 synthetic agent,实际 byte 对比:

| 场景 | v1 chars | v2 chars | 节省 | v2_only_lines |
|---|---|---|---|---|
| casual_chat(zh,solo,无文件工具) | 12,748 | 6,633 | **-48%** | 0 |
| pptx_authoring(zh,project,file+send) | 13,085 | 8,572 | **-34%** | 0 |
| meeting(en,meeting,send 无文件) | 14,515 | 8,643 | **-40%** | 0 |

**关键验证**:`v2_only_lines=0` — v2 是 v1 的真子集,不会"误装"v1 不会发的内容。
所有节省全部来自有意 gating(scope / has_tools_in / extras-prefetch 为空)。

平均节省 **-41%**,接近 Stage A 预期的 -39% 加权平均上限。

---

## 切流量路线图(Stage B → C)

### Stage B Step 1 ✅ 已完成(2026-04-26)

1. ✅ **精确文本提取** — `file_display_long` / `attachment_contract` placeholder 替换为真实文本
2. ✅ **拓展 catalog** — 5 个新块覆盖了 agent.py 里所有遗漏的 inline 块
   (file_display_short, workspace_context_full, image_display_long,
   plan_protocol, granted_skills_roster)
3. ✅ **agent.py inline 块抽到 system_prompt.py** — 5 个常量 + 1 个 fn,
   单一来源;byte-equivalent 重构,v1 行为不变
4. ✅ **dry-run hook prefetch IO 数据** — retrieval_protocol / model_guidance /
   granted_skills_roster / project_context_files 都 prefetch 到 extras,
   diff_summary 反映真实差距
5. ✅ **测试** — 51 个 unit test(原 43 + 新 8),全过

### Stage B 余项(下个 session)

1. **scene_prompts schema 加 `scopes: [...]` 字段** — operator UI 露出 scope 选择
2. v2 装入但 v1 仍是真返回值,日志双跑 1-2 周收集线上数据
3. 与 Phase 1 cache_hit_rate 度量对比验证(`get_token_totals().cache_hit_rate`
   预期从 25% 涨到 65-75%)

### Stage C: 切流量(再下个 session)

1. ENV `TUDOU_PROMPT_V2=1` 全局开关
2. 按 role 分桶切流量(先选无 deliverable 的 role 如 casual / 客服)
3. 出问题:`TUDOU_PROMPT_V2=0` 即时回退
4. 全量发布 — 同时把 v1 的 `_build_static_system_prompt` 删除或仅保留 fallback
5. 顺手 dedup:v1 今天 emit `<file_display>` / `<image_display>` /
   `<workspace_context>` 各 2 次(SHORT + LONG),v2 catalog 里 SHORT/LONG 都
   保留是为了 Stage B 等价对比;Stage C 切完可以根据 LLM 表现决定保留哪个

---

## 反指标(发布后强制守住)

| 指标 | 红线 |
|---|---|
| 工具调用 success rate | 不下降 |
| 用户主观满意度 | 不变 / 上升 |
| 复杂任务首轮命中率 | 不下降 |
| LLM 拒答 / 道歉率 | 不上升 |
| `cache_hit_rate` (Phase 1 度量) | 不下降(预期上升)|

---

## 给团队拍板的几件事

1. **新文件 vs inplace 改 system_prompt.py** — 已选**新文件**(prompt_blocks.py + system_prompt_v2.py + prompt_block_catalog.py)。v1 保留可对比。Stage C 稳定后再删 v1。
2. **scene_prompts 是否扩 schema 加 `scopes` 字段** — 待 Stage B 决定。需要 schema migration。
3. **cache_anchor 标几个** — 已选 3 个(identity / tool_rules / persona)。可以根据 dry-run 数据再调。
4. **灰度起点选哪个 role** — 推荐先选 casual_chat agent / 客服 agent(无 deliverable 容忍度高)。
5. **placeholder 块的真实文本提取** — Stage B 必做。建议每个块作为单独 PR,reviewer + owner 双签字。

---

## Stage A 工作量(已完成)

| 文件 | LOC | 状态 |
|---|---|---|
| `app/prompt_blocks.py` | 230 | ✅ |
| `app/system_prompt_v2.py` | 130 | ✅ |
| `app/prompt_block_catalog.py` | 290 | ✅ |
| `tests/test_prompt_blocks.py` | 360 | ✅ 43 tests pass |
| `app/agent.py` dry-run 钩子 | +60 | ✅ |
| **合计** | **~1070 LOC** | ✅ |

---

## Stage B Step 1 工作量(已完成 2026-04-26)

| 文件 | LOC | 状态 |
|---|---|---|
| `app/system_prompt.py` 抽常量 + workspace_context_long fn | +180 | ✅ |
| `app/agent.py` 重构 inline → 引用常量 | -130(净减)| ✅ byte-equiv |
| `app/agent.py` dry-run hook prefetch IO 数据 | +60 | ✅ |
| `app/prompt_block_catalog.py` 5 块 + placeholder 替换 | +130 | ✅ |
| `tests/test_prompt_blocks.py` 8 个新测试 | +180 | ✅ 51 tests pass |
| **合计** | **~+420 LOC 净** | ✅ |

---

## Stage B 余项 / Stage C 工作量估算

| 任务 | LOC | 时间 |
|---|---|---|
| scene_prompts schema migration(scopes 字段)| ~150 | 0.5-1 天 |
| dry-run 数据分析 + catalog 调优 | — | 1-2 天(等线上数据)|
| 切流量基础设施(ENV / per-role 分桶) | ~100 | 0.5 天 |
| 灰度发布 + 监控 | — | 1 周窗口 |
| 切完 v1/v2 dedup | ~50 | 0.5 天 |
| **合计** | **~300 LOC + 1 周观察** | **2 天 + 1 周** |

---

## 当前测试覆盖

`tests/test_prompt_blocks.py` 共 **51 个测试**(Stage A 43 + Stage B 8):

- BlockGate 各维度:scopes / tools / skills / role_kind / ctx_type / requires_image / custom
- AND 语义、custom 异常 fail-safe
- PromptBlock render:str / callable / 异常 / 非 str 返回
- AssemblyContext factory:类型转换、frozen 不可变
- assemble_static_prompt:排序(priority + id)、装入、跳过、cache_anchor
- 7 种 exclusion reason 全覆盖
- assemble_with_log 不崩
- diff_summary 基本场景
- 默认 catalog:size(18)、唯一 id、3 场景集成
- scope 切换导致装入集合变化(cache 稳定性核心)
- **Stage B 新增**:
  - `file_display_short` Always 装入 + 真实文本(非 placeholder)
  - `file_display_long` 真实文本(去掉 placeholder)+ 5 条规则 + 中文摘要
  - `attachment_contract` zh/en 分支真实文本
  - `workspace_context_full` solo/project 分支 + empty render skip
  - `image_display_long` zh/en 分支
  - `plan_protocol` Always 装入
  - `granted_skills_roster` extras-prefetch gating
  - Stage B 完整 17 块场景集成(pptx_authoring + project + 全 prefetch)
