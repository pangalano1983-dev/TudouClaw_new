---
name: file-ops
description: 读写文件、搜索、目录遍历 — 基础文件系统能力。 Grants tools: read_file, write_file, edit_file, search_files, glob_files
icon: "📁"
metadata:
  tier: core-bundle
  tools:
    - read_file
    - write_file
    - edit_file
    - search_files
    - glob_files
---

# 📁 文件操作 / file ops

读写文件、搜索、目录遍历 — 基础文件系统能力。

## 🔧 包含的工具 (5 个)

- `read_file`
- `write_file`
- `edit_file`
- `search_files`
- `glob_files`

## 📌 用途

Agent 授权此 skill 后,可以在 tool_calls 里调用上面列的工具。这是
一个**工具包 skill** —— 没有可执行代码,它的作用就是"打开一类工具
的开关"。

## ⚙️ 默认授权

`file-ops` 默认授权给所有新建 agent (详见 `tool_capabilities.py` 里的
`_FACTORY_DEFAULT_CAPABILITIES`)。

想取消默认,修改 `app/tool_capabilities.py`。

## 🏷️ Bundle 类型

core-bundle —— 和 file-ops / shell-ops / web-ops 等并列,按功能域归类。
