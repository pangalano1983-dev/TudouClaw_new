---
id: T23_six_card_grid
name: 6-Card Grid (3×2)
name_zh: 6 卡片网格
category: grid
summary: "3-column × 2-row grid of small cards with icon + heading + 1-line note."
summary_zh: "3×2 共 6 张小卡片, 每张含图标+标题+一句简介; 用于呈现 6 个并列要点 / 模块 / 团队成员。"
when_to_use: |
  - 6 个并列项 (模块 / 优势 / 团队 / 客户案例 / 产品系列)
  - 每张卡片信息少 (图标 + 8 字标题 + 30 字简介)
  - 4 项用 T06; 3 项用 T02; 6 项以上拆页

params_schema:
  type: object
  required: [title, cells]
  properties:
    title:
      type: string
      max_len: 40
    cells:
      type: array
      min_items: 6
      max_items: 6
      items:
        type: object
        required: [heading]
        properties:
          icon:
            type: string
          heading:
            type: string
            max_len: 16
          body:
            type: string
            max_len: 60

layout:
  - shape: rect
    x: 0
    y: 0
    w: sw
    h: sh
    fill: bg
  - shape: text
    x: 0.5
    y: 0.35
    w: 12.3
    h: 0.7
    text: "{title}"
    style: title
  - shape: rect
    x: 0.5
    y: 1.05
    w: 12.3
    h: 0.04
    fill: accent
  - for_each: "cell in cells[:6]"
    index_as: i
    vars:
      row: "i // 3"
      col: "i % 3"
      cx: "0.5 + col * 4.15"
      cy: "1.5 + row * 2.85"
    children:
      # 卡片背景
      - shape: rect
        x: "{cx}"
        y: "{cy}"
        w: 3.95
        h: 2.6
        fill: panel
      # 顶部 accent 细条
      - shape: rect
        x: "{cx}"
        y: "{cy}"
        w: 3.95
        h: 0.06
        fill: accent
      # 图标
      - shape: icon
        name: "{cell.icon|target}"
        x: "{cx + 0.25}"
        y: "{cy + 0.3}"
        size: 0.55
        color: primary
      # 标题
      - shape: text
        x: "{cx + 0.25}"
        y: "{cy + 1.0}"
        w: 3.5
        h: 0.5
        text: "{cell.heading}"
        style: card_heading
      # 正文
      - shape: text
        x: "{cx + 0.25}"
        y: "{cy + 1.55}"
        w: 3.5
        h: 0.95
        text: "{cell.body|}"
        style: card_body
---

# T23 6-Card Grid — 3×2 卡片网格

## 预览

```
┌────────────────────────────────────────────┐
│ {title}                                    │
├──── orange line ──────────────────────────┤
│ ┌─────┐ ┌─────┐ ┌─────┐                  │
│ │ico  │ │ico  │ │ico  │  <- row 1 (3 cards)│
│ │head │ │head │ │head │                  │
│ │body │ │body │ │body │                  │
│ └─────┘ └─────┘ └─────┘                  │
│ ┌─────┐ ┌─────┐ ┌─────┐                  │
│ │ico  │ │ico  │ │ico  │  <- row 2 (3 cards)│
│ │head │ │head │ │head │                  │
│ │body │ │body │ │body │                  │
│ └─────┘ └─────┘ └─────┘                  │
└────────────────────────────────────────────┘
```

## 调用示例

```python
render_from_md(prs, "corporate/T23_six_card_grid", params={
    "title": "六大业务模块",
    "cells": [
        {"icon":"users",   "heading":"客户管理", "body":"统一客户视图,生命周期可视化"},
        {"icon":"chart",   "heading":"数据分析", "body":"实时报表 + AI 洞察"},
        {"icon":"shield",  "heading":"安全合规", "body":"端到端加密,合规审计"},
        {"icon":"zap",     "heading":"自动化",   "body":"流程自动化,工单自动派发"},
        {"icon":"layers",  "heading":"集成中台", "body":"对接 30+ 第三方系统"},
        {"icon":"globe",   "heading":"全球部署", "body":"多区域低延迟"},
    ],
})
```

## 设计说明

- 每张卡 3.95"宽 × 2.6"高,3 列 × 2 行刚好填满 12.3" 宽内容区。
- 卡片顶部 0.06" accent 细条作为视觉锚点。
- 图标 0.55" 大小, 比 T06 的 4 卡略小。
