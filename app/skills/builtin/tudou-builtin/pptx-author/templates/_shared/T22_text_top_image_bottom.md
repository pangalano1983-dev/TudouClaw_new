---
id: T22_text_top_image_bottom
name: Text Top, Image Bottom
name_zh: 上文下图
category: media
summary: "Heading + paragraph on top half, full-width image below."
summary_zh: "上半部分标题+正文 / 下半部分宽图。适合"先讲结论,后看证据"的叙述。"
when_to_use: |
  - 上面一段总结性文字, 下面一张大宽图 (架构图 / 趋势图 / 屏幕截图)
  - 图片是横向的、宽幅展示更合适 (左右图侧重特写, 用 T21)

params_schema:
  type: object
  required: [title, image_path]
  properties:
    title:
      type: string
      max_len: 40
    summary:
      type: string
      max_len: 200
      desc: "标题下方的一段说明 (1-3 句)。"
    image_path:
      type: string
    image_caption:
      type: string
      max_len: 80

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
  - if: "summary"
    shape: text
    x: 0.5
    y: 1.25
    w: 12.3
    h: 1.4
    text: "{summary}"
    style: card_body
  # 全宽大图区
  - shape: rect
    x: 0.5
    y: 2.85
    w: 12.3
    h: 4.2
    fill: panel
  - shape: image
    path: "{image_path}"
    x: 0.5
    y: 2.85
    w: 12.3
    h: 4.2
    fit: contain
  - if: "image_caption"
    shape: text
    x: 0.5
    y: 7.1
    w: 12.3
    h: 0.35
    text: "{image_caption}"
    style: subtitle
    align: center
---

# T22 Text Top, Image Bottom — 上文下图

## 预览

```
┌────────────────────────────────────────┐
│ {title}                                │
├──── orange line ──────────────────────┤
│ {summary}                              │
│ (1-3 sentences)                        │
│ ┌──────────────────────────────────┐ │
│ │                                    │ │
│ │       [wide image]                 │ │
│ │                                    │ │
│ └──────────────────────────────────┘ │
│ {caption}                              │
└────────────────────────────────────────┘
```

## 调用示例

```python
render_from_md(prs, "corporate/T22_text_top_image_bottom", params={
    "title": "Q2 营收趋势",
    "summary": "Q2 同比增长 32%,创历史新高。主要驱动来自海外市场的 AI 业务,占总营收 18%。",
    "image_path": "/workspace/charts/q2_trend.png",
    "image_caption": "图: 2025 Q1 - 2026 Q2 月度营收趋势",
})
```

## 设计说明

- 上文区高度 2.85"(标题+说明), 下图区高度 4.2", 比例约 4:6 偏图。
- 大图 fit=contain, 不会裁剪。如果你的图是 16:9, 这块基本铺满。
