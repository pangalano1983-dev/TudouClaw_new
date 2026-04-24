---
name: web-ops
description: 搜索网页、抓取内容。研究类任务必备。 Grants tools: web_search, web_fetch
icon: "🌐"
metadata:
  tier: core-bundle
  tools:
    - web_search
    - web_fetch
---

# 🌐 网络操作 / web ops

搜索网页、抓取内容。研究类任务必备。

## 🔧 包含的工具 (2 个)

- `web_search`
- `web_fetch`

## 📌 用途

Agent 授权此 skill 后,可以在 tool_calls 里调用上面列的工具。这是
一个**工具包 skill** —— 没有可执行代码,它的作用就是"打开一类工具
的开关"。

## ⚙️ 默认授权

`web-ops` 默认授权给所有新建 agent (详见 `tool_capabilities.py` 里的
`_FACTORY_DEFAULT_CAPABILITIES`)。

想取消默认,修改 `app/tool_capabilities.py`。

## 🏷️ Bundle 类型

core-bundle —— 和 file-ops / shell-ops / web-ops 等并列,按功能域归类。
