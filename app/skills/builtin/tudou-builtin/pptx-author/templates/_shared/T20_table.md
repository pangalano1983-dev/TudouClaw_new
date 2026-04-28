---
id: T20_table
name: Table
name_zh: 表格页
category: data
summary: "Title + caption + multi-column table for structured data."
summary_zh: "标题 + 说明 + 表格,适合呈现行列结构化数据(对比表 / 名单 / 指标表)。"
when_to_use: |
  - 多行多列数据对比 (3-5 列, 4-10 行最佳)
  - KPI 表 / 价格表 / 功能对比 / 名单
  - 不要用来呈现"流程"(用 T26) 或"时间线"(用 T09)

params_schema:
  type: object
  required: [title, headers, rows]
  properties:
    title:
      type: string
      max_len: 40
    caption:
      type: string
      max_len: 80
      desc: "表格上方的简短说明,可选。"
    headers:
      type: array
      min_items: 2
      max_items: 6
      items:
        type: string
        max_len: 18
    rows:
      type: array
      min_items: 1
      max_items: 12
      items:
        type: array
        items:
          type: string
          max_len: 30

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
  - if: "caption"
    shape: text
    x: 0.5
    y: 1.2
    w: 12.3
    h: 0.5
    text: "{caption}"
    style: subtitle
  - shape: table
    x: 0.5
    y: 1.85
    w: 12.3
    h: 5.0
    headers: "{headers}"
    rows: "{rows}"
    header_fill: primary
    header_text: bg
    row_fill: bg
    row_alt_fill: panel
    border: border
---

# T20 Table — 表格页

## 预览

```
┌────────────────────────────────────────────┐
│ {title}                                    │
├──── orange line ──────────────────────────┤
│ {caption}                                  │
│ ┌─────┬─────┬─────┬─────┐                 │
│ │ H1  │ H2  │ H3  │ H4  │ ← 表头 primary  │
│ ├─────┼─────┼─────┼─────┤                 │
│ │ ... │ ... │ ... │ ... │ ← 行            │
│ │ ... │ ... │ ... │ ... │ ← 隔行 panel    │
│ └─────┴─────┴─────┴─────┘                 │
└────────────────────────────────────────────┘
```

## 调用示例

```python
render_from_md(prs, "corporate/T20_table", params={
    "title": "三大供应商对比",
    "caption": "数据来源: 2026 Q1 内部测试",
    "headers": ["维度", "供应商 A", "供应商 B", "供应商 C"],
    "rows": [
        ["响应时间",   "200ms", "150ms", "300ms"],
        ["可用性",     "99.9%", "99.5%", "99.99%"],
        ["单价",       "$0.5",  "$0.8",  "$0.3"],
        ["技术支持",   "邮件",  "工单",  "7×24"],
    ],
})
```

## 设计说明

- 表头使用 primary 色填充 + 白字。
- 隔行使用 panel 色,提升可读性。
- 单元格 padding 6px,字号 12pt 正文,自适应列宽。
- 超过 5 列建议拆成两页或改用列表;超过 10 行建议分块或改用 docs。
