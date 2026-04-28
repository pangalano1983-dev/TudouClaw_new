---
id: T02_three_column
name: 3-Column Cards
name_zh: 3 列卡片
category: grid
summary: "Three horizontal columns, each with icon + heading + body."
summary_zh: "3 列横向卡片, 每列含图标+标题+正文。"
when_to_use: |
  - 恰好 3 个并列的要点 / 支柱 / 类别 / 角色
  - 每项有短标题(≤12字) + 2-3 句说明(≤60字)
  - 4 项用 T06 (2×2 网格); 5+ 项用列表 T07 或考虑拆页
  - 经典使用: "Three Pillars", "三大优势", "三个利益相关方"

params_schema:
  type: object
  required: [title, columns]
  properties:
    title:
      type: string
      max_len: 40
      desc: "顶部标题, 建议 ≤20 字。"
    columns:
      type: array
      min_items: 3
      max_items: 3
      items:
        type: object
        required: [heading, body]
        properties:
          icon:
            type: string
            desc: "图标名 (lucide), 如 users / target / shield。留空用圆点。"
          heading:
            type: string
            max_len: 18
          body:
            type: string
            max_len: 140

layout:
  # 底色
  - shape: rect
    x: 0
    y: 0
    w: sw
    h: sh
    fill: bg

  # 顶部标题
  - shape: text
    x: 0.5
    y: 0.35
    w: 12.3
    h: 0.7
    text: "{title}"
    style: title

  # 细线装饰
  - shape: rect
    x: 0.5
    y: 1.05
    w: 12.3
    h: 0.04
    fill: accent

  # 3 列,每列 4.0" 宽,列间距 0.15"; 左右 0.35" 留白 (safe margin 0.3")
  - for_each: "column in columns[:3]"
    index_as: i
    vars:
      cx: "0.35 + i * 4.15"
      cy: 1.6
    children:
      # 顶部 icon 圆底
      - shape: oval
        x: "{cx + 1.5}"
        y: "{cy + 0.1}"
        w: 1.0
        h: 1.0
        fill: panel

      - shape: icon
        name: "{column.icon|target}"
        x: "{cx + 1.8}"
        y: "{cy + 0.35}"
        size: 0.5
        color: primary

      # Heading (居中)
      - shape: text
        x: "{cx}"
        y: "{cy + 1.4}"
        w: 4.0
        h: 0.6
        text: "{column.heading}"
        style: card_heading
        align: center

      # 短分隔线
      - shape: rect
        x: "{cx + 1.7}"
        y: "{cy + 2.15}"
        w: 0.6
        h: 0.03
        fill: accent

      # Body (居中)
      - shape: text
        x: "{cx + 0.15}"
        y: "{cy + 2.4}"
        w: 3.7
        h: 2.5
        text: "{column.body}"
        style: card_body
        align: center
---

# T02 Three Column — 3 列卡片

## 预览

```
┌─────────────────────────────────────────────┐
│ {title}                                     │
├──── orange line ───────────────────────────┤
│   (icon)       (icon)       (icon)         │
│                                             │
│   Heading      Heading      Heading         │
│   ─────        ─────        ─────          │
│   body         body         body            │
│   text         text         text            │
└─────────────────────────────────────────────┘
```

## 调用示例

```python
render_from_md(prs, "corporate/T02_three_column", params={
    "title": "三大核心支柱",
    "columns": [
        {"icon": "users",   "heading": "以人为本", "body": "将用户需求置于决策的最前端, 每次迭代都来自真实反馈。"},
        {"icon": "zap",     "heading": "极致效率", "body": "从流程到工具, 全链路压缩响应时间, 让价值更快到达。"},
        {"icon": "shield",  "heading": "稳健合规", "body": "内建合规检查, 每个环节可审计、可追溯、可恢复。"},
    ],
})
```

## 设计说明

- 3 列等宽 4.1", 每列居中对齐。
- 圆形 icon 底色用 `panel`(浅)色, icon 本身用 `primary` 色。
- 标题下方有一条 0.6" 宽的 accent 色短分隔线, 让每列的信息层次更清晰。
- Body 文字居中, 建议 40-80 字(2-3 句)。过长会显得拥挤, 应该拆页或改用 T07。
