---
name: scheduling
description: 创建提醒、延时任务、cron 定时任务。 Grants tools: task_update
icon: "⏰"
metadata:
  tier: core-bundle
  tools:
    - task_update
---

# ⏰ 任务调度 / scheduling

创建提醒、延时任务、cron 定时任务。

## 🔧 包含的工具 (1 个)

- `task_update`

## 📌 用途

Agent 授权此 skill 后,可以在 tool_calls 里调用上面列的工具。这是
一个**工具包 skill** —— 没有可执行代码,它的作用就是"打开一类工具
的开关"。

## ⚙️ 默认授权

`scheduling` 默认授权给所有新建 agent (详见 `tool_capabilities.py` 里的
`_FACTORY_DEFAULT_CAPABILITIES`)。

想取消默认,修改 `app/tool_capabilities.py`。

## 🏷️ Bundle 类型

core-bundle —— 和 file-ops / shell-ops / web-ops 等并列,按功能域归类。
