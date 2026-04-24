---
name: handoff
description: 结构化 baton-pass —— 把任务交给下一个 agent。 Grants tools: emit_handoff, handoff_request, team_create
icon: "🔀"
metadata:
  tier: core-bundle
  tools:
    - emit_handoff
    - handoff_request
    - team_create
---

# 🔀 任务交接 / handoff

结构化 baton-pass —— 把任务交给下一个 agent。

## 🔧 包含的工具 (3 个)

- `emit_handoff`
- `handoff_request`
- `team_create`

## 📌 用途

Agent 授权此 skill 后,可以在 tool_calls 里调用上面列的工具。这是
一个**工具包 skill** —— 没有可执行代码,它的作用就是"打开一类工具
的开关"。

## ⚙️ 默认授权

`handoff` 默认授权给所有新建 agent (详见 `tool_capabilities.py` 里的
`_FACTORY_DEFAULT_CAPABILITIES`)。

想取消默认,修改 `app/tool_capabilities.py`。

## 🏷️ Bundle 类型

core-bundle —— 和 file-ops / shell-ops / web-ops 等并列,按功能域归类。
