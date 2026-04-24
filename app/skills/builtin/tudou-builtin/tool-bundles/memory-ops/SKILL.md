---
name: memory-ops
description: 检索知识库、保存经验、跨 agent 共享。 Grants tools: knowledge_lookup, save_experience, share_knowledge, learn_from_peers, memory_recall
icon: "🧠"
metadata:
  tier: core-bundle
  tools:
    - knowledge_lookup
    - save_experience
    - share_knowledge
    - learn_from_peers
    - memory_recall
---

# 🧠 记忆操作 / memory ops

检索知识库、保存经验、跨 agent 共享。

## 🔧 包含的工具 (5 个)

- `knowledge_lookup`
- `save_experience`
- `share_knowledge`
- `learn_from_peers`
- `memory_recall`

## 📌 用途

Agent 授权此 skill 后,可以在 tool_calls 里调用上面列的工具。这是
一个**工具包 skill** —— 没有可执行代码,它的作用就是"打开一类工具
的开关"。

## ⚙️ 默认授权

`memory-ops` 默认授权给所有新建 agent (详见 `tool_capabilities.py` 里的
`_FACTORY_DEFAULT_CAPABILITIES`)。

想取消默认,修改 `app/tool_capabilities.py`。

## 🏷️ Bundle 类型

core-bundle —— 和 file-ops / shell-ops / web-ops 等并列,按功能域归类。
