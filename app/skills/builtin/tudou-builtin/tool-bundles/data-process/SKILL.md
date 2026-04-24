---
name: data-process
description: 日期计算、JSON/文本处理工具。 Grants tools: datetime_calc, json_process, text_process
icon: "⚙️"
metadata:
  tier: core-bundle
  tools:
    - datetime_calc
    - json_process
    - text_process
---

# ⚙️ 数据处理 / data process

日期计算、JSON/文本处理工具。

## 🔧 包含的工具 (3 个)

- `datetime_calc`
- `json_process`
- `text_process`

## 📌 用途

Agent 授权此 skill 后,可以在 tool_calls 里调用上面列的工具。这是
一个**工具包 skill** —— 没有可执行代码,它的作用就是"打开一类工具
的开关"。

## ⚙️ 默认授权

`data-process` 默认授权给所有新建 agent (详见 `tool_capabilities.py` 里的
`_FACTORY_DEFAULT_CAPABILITIES`)。

想取消默认,修改 `app/tool_capabilities.py`。

## 🏷️ Bundle 类型

core-bundle —— 和 file-ops / shell-ops / web-ops 等并列,按功能域归类。
