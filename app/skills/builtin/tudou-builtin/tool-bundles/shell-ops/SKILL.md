---
name: shell-ops
description: 执行 bash 命令、跑测试。需要谨慎,有副作用。 Grants tools: bash, run_tests
icon: "🖥️"
metadata:
  tier: core-bundle
  tools:
    - bash
    - run_tests
---

# 🖥️ Shell / 测试 / shell & tests

执行 bash 命令、跑测试。需要谨慎,有副作用。

## 🔧 包含的工具 (2 个)

- `bash`
- `run_tests`

## 📌 用途

Agent 授权此 skill 后,可以在 tool_calls 里调用上面列的工具。这是
一个**工具包 skill** —— 没有可执行代码,它的作用就是"打开一类工具
的开关"。

## ⚙️ 默认授权

`shell-ops` 默认授权给所有新建 agent (详见 `tool_capabilities.py` 里的
`_FACTORY_DEFAULT_CAPABILITIES`)。

想取消默认,修改 `app/tool_capabilities.py`。

## 🏷️ Bundle 类型

core-bundle —— 和 file-ops / shell-ops / web-ops 等并列,按功能域归类。
