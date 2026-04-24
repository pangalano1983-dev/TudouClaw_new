---
name: messaging
description: 给其他 agent / 频道发消息、收消息。 Grants tools: send_message, ack_message, reply_message, check_inbox
icon: "💬"
metadata:
  tier: core-bundle
  tools:
    - send_message
    - ack_message
    - reply_message
    - check_inbox
---

# 💬 消息交互 / messaging

给其他 agent / 频道发消息、收消息。

## 🔧 包含的工具 (4 个)

- `send_message`
- `ack_message`
- `reply_message`
- `check_inbox`

## 📌 用途

Agent 授权此 skill 后,可以在 tool_calls 里调用上面列的工具。这是
一个**工具包 skill** —— 没有可执行代码,它的作用就是"打开一类工具
的开关"。

## ⚙️ 默认授权

`messaging` 默认授权给所有新建 agent (详见 `tool_capabilities.py` 里的
`_FACTORY_DEFAULT_CAPABILITIES`)。

想取消默认,修改 `app/tool_capabilities.py`。

## 🏷️ Bundle 类型

core-bundle —— 和 file-ops / shell-ops / web-ops 等并列,按功能域归类。
