---
id: T01_cover
name: Cover
name_zh: 封面
category: cover
summary: "Full-bleed dark background + centered title + subtitle + accent tag."
summary_zh: "深色满屏背景 + 居中大标题 + 副标题 + 橙色 tag 条。"
when_to_use: |
  - 报告首页 / 章节册首页
  - 只有一个核心主题 + 1 句副题
  - 不要用在目录 / Executive Summary 之前的占位页 (那用 T04)

params_schema:
  type: object
  required: [title]
  properties:
    title:
      type: string
      max_len: 40
      desc: "主标题,建议 8-20 字。"
    subtitle:
      type: string
      max_len: 60
      desc: "副标题,可选。"
    tag:
      type: string
      max_len: 30
      desc: "底部小标签,如 '2026 Q2 | 专业研究'。可选。"

layout:
  # 深色满屏底
  - shape: rect
    x: 0
    y: 0
    w: sw
    h: sh
    fill: bg_dark

  # 橙色 accent 竖条 (左侧装饰)
  - shape: rect
    x: 0.8
    y: 2.4
    w: 0.1
    h: 2.7
    fill: accent

  # 主标题
  - shape: text
    x: 1.2
    y: 2.6
    w: 11.0
    h: 1.5
    text: "{title}"
    style: cover_title

  # 副标题 (if present)
  - if: "subtitle"
    shape: text
    x: 1.2
    y: 4.0
    w: 11.0
    h: 0.8
    text: "{subtitle}"
    style: cover_subtitle

  # 底部 tag
  - if: "tag"
    shape: text
    x: 1.2
    y: 6.5
    w: 11.0
    h: 0.4
    text: "{tag}"
    style: cover_tag
---

# T01 Cover — 封面页

## 预览

```
╔═══════════════════════════════════════════╗
║                                           ║
║  ▎                                        ║
║  ▎ {title}                                ║
║  ▎ {subtitle}                             ║
║                                           ║
║  {tag}                                    ║
╚═══════════════════════════════════════════╝
      ↑ dark bg + orange accent bar
```

## 调用示例

```python
render_from_md(prs, "corporate/T01_cover", params={
    "title": "年度经营分析",
    "subtitle": "从增长质量到价值创造：三大关键发现",
    "tag": "2026 Q2 | 经营分析报告",
})
```

## 设计说明

- 画布满屏深蓝 `bg_dark` (theme 定义)。
- 橙色竖条 accent bar 放在标题左侧,起视觉焦点作用。
- 标题 40pt bold,副标题 20pt regular,两行足够。
- Tag 小字 12pt,橙色 accent。
