---
id: T06_requirement_grid
name: 2×2 Requirement Grid
name_zh: 2×2 要求网格
category: grid
summary: "Four-quadrant grid. Each cell: icon + heading + body."
summary_zh: "2×2 网格, 4 个并列要点, 每格含图标+小标题+正文。"
when_to_use: |
  - 恰好 4 个并列的要点 / 要求 / 特性 / 支柱
  - 每项有短标题(≤12字) + 1-3 句说明
  - 不是时间顺序 (那用 T09), 不是对比 (那用 T11)
  - 多于 4 条: 拆两页或用 T07 列表

params_schema:
  type: object
  required: [title, cells]
  properties:
    title:
      type: string
      max_len: 40
      desc: "顶部标题, 建议 ≤20 字。"
    cells:
      type: array
      min_items: 4
      max_items: 4
      items:
        type: object
        required: [heading, body]
        properties:
          icon:
            type: string
            desc: "图标名 (lucide), 如 shield / target / zap。留空用圆点。"
          heading:
            type: string
            max_len: 20
            desc: "格子标题, 建议 ≤12 字。"
          body:
            type: string
            max_len: 140
            desc: "正文, 建议 2-3 句, ≤60 字。"

layout:
  # 底色
  - shape: rect
    x: 0
    y: 0
    w: sw
    h: sh
    fill: bg

  # 顶部标题条
  - shape: text
    x: 0.5
    y: 0.35
    w: 12.3
    h: 0.7
    text: "{title}"
    style: title

  # 顶部细线装饰
  - shape: rect
    x: 0.5
    y: 1.05
    w: 12.3
    h: 0.04
    fill: accent

  # 2×2 网格, for-each 展开
  - for_each: "cell in cells[:4]"
    index_as: i
    vars:
      row: "i // 2"
      col: "i % 2"
      cx: "0.6 + col * 6.3"
      cy: "1.5 + row * 2.7"
    children:
      - shape: rect
        x: "{cx}"
        y: "{cy}"
        w: 0.08
        h: 2.3
        fill: accent

      - shape: icon
        name: "{cell.icon|target}"
        x: "{cx + 0.3}"
        y: "{cy + 0.1}"
        size: 0.5
        color: primary

      - shape: text
        x: "{cx + 1.1}"
        y: "{cy + 0.1}"
        w: 5.0
        h: 0.5
        text: "{cell.heading}"
        style: card_heading

      - shape: text
        x: "{cx + 0.3}"
        y: "{cy + 0.8}"
        w: 5.8
        h: 1.5
        text: "{cell.body}"
        style: card_body
---

# T06 Requirement Grid — 2×2 要求网格

## 预览

```
┌─────────────────────────────────────────┐
│ {title}                                 │
├──── 0.04" orange line ─────────────────┤
│ ▎[icon] {heading}   ▎[icon] {heading} │
│   {body}              {body}            │
│                                         │
│ ▎[icon] {heading}   ▎[icon] {heading} │
│   {body}              {body}            │
└─────────────────────────────────────────┘
```

## 调用示例

```python
render_from_md(prs, "corporate/T06_requirement_grid", params={
    "title": "四大核心能力",
    "cells": [
        {"icon": "shield",  "heading": "安全合规", "body": "..."},
        {"icon": "chart",   "heading": "实时监控", "body": "..."},
        {"icon": "zap",     "heading": "自动响应", "body": "..."},
        {"icon": "users",   "heading": "统一治理", "body": "..."},
    ],
})
```

## 设计说明

- 每格约 6.0" × 2.3", 左侧 0.08" 橙色 accent bar。
- 图标 0.5" 大小, 使用 theme 的 primary 色填充。
- Heading bold, body regular muted 色。
