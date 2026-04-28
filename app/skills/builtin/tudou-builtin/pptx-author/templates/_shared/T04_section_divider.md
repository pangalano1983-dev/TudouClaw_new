---
id: T04_section_divider
name: Section Divider
name_zh: 章节分隔页
category: divider
summary: "Giant chapter number on left + chapter heading + short subtitle."
summary_zh: "左侧巨大章节号 + 章节标题 + 短副题,用于章节切换。"
when_to_use: |
  - 章节之间的过渡页,让读者知道进入新章节
  - 数字 01/02/03... 用超大字号,视觉上"翻页"感强
  - 不适合单页报告; 适合多章节长报告

params_schema:
  type: object
  required: [no, heading]
  properties:
    no:
      type: string
      max_len: 3
      desc: "章节编号,如 '01' / '02'。"
    heading:
      type: string
      max_len: 20
      desc: "章节标题,建议 4-10 字。"
    subtitle:
      type: string
      max_len: 40
      desc: "章节副题,可选。建议 ≤20 字。"

layout:
  # 白底 (对比封面的深色)
  - shape: rect
    x: 0
    y: 0
    w: sw
    h: sh
    fill: bg

  # 左侧 panel 浅灰背景
  - shape: rect
    x: 0
    y: 0
    w: 5.5
    h: sh
    fill: panel

  # 巨大章节号
  - shape: text
    x: 0.5
    y: 2.2
    w: 4.5
    h: 3.0
    text: "{no}"
    style: section_num

  # 右侧橙竖条
  - shape: rect
    x: 6.0
    y: 2.9
    w: 0.08
    h: 1.8
    fill: accent

  # 章节标题
  - shape: text
    x: 6.3
    y: 2.9
    w: 6.5
    h: 1.0
    text: "{heading}"
    style: section_head

  # 章节副题
  - if: "subtitle"
    shape: text
    x: 6.3
    y: 4.0
    w: 6.5
    h: 0.8
    text: "{subtitle}"
    style: section_sub
---

# T04 Section Divider — 章节分隔页

## 预览

```
┌─────────────┬──────────────────────────┐
│             │                          │
│             │  ▎ {heading}             │
│    01       │    {subtitle}            │
│  (huge)     │                          │
│             │                          │
│             │                          │
└─────────────┴──────────────────────────┘
  panel bg         white bg
```

## 调用示例

```python
render_from_md(prs, "corporate/T04_section_divider", params={
    "no": "02",
    "heading": "增长质量诊断",
    "subtitle": "结构、效率与可持续性三维评估",
})
```

## 设计说明

- 左侧 panel 区域宽 5.5"(约占 41%),放超大章节号。
- 数字使用 140pt bold accent 色 —— 视觉冲击强,让读者明确知道"进入新章节"。
- 右侧留白 + 橙色小竖条引导视线到章节标题。
