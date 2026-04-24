---
name: ui-visibility
description: 向 chat 发送结构化 UI 块 (表格、卡片、图等)。 Grants tools: emit_ui_block
icon: "🎨"
metadata:
  tier: core-bundle
  tools:
    - emit_ui_block
---

# 🎨 富 UI 块 / rich UI

向 chat 发送结构化 UI 块 (表格、卡片、图等)。

## 🔧 包含的工具 (1 个)

- `emit_ui_block`

## 📌 用途

Agent 授权此 skill 后,可以在 tool_calls 里调用上面列的工具。这是
一个**工具包 skill** —— 没有可执行代码,它的作用就是"打开一类工具
的开关"。

## ⚙️ 默认授权

`ui-visibility` 默认授权给所有新建 agent (详见 `tool_capabilities.py` 里的
`_FACTORY_DEFAULT_CAPABILITIES`)。

想取消默认,修改 `app/tool_capabilities.py`。

## 🏷️ Bundle 类型

core-bundle —— 和 file-ops / shell-ops / web-ops 等并列,按功能域归类。
