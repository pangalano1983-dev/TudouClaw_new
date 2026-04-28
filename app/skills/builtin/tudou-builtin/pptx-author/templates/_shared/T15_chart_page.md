---
id: T15_chart_page
name: Chart Page
name_zh: 图表页
category: chart
summary: "Big chart placeholder + title + takeaway banner at the bottom."
summary_zh: "大图表占位 + 顶部标题 + 底部 takeaway 标语条。"
when_to_use: |
  - 需要突出 1 张图表(柱状图/折线/饼图)+ 一句核心结论
  - 图表本身由 agent 另行调 add_bar_chart / add_line_chart 等 helper
    填入占位区域 (见下方"图表区坐标")
  - 多张图表同页 → 违反 verify_slides 规则, 必须拆页

params_schema:
  type: object
  required: [title]
  properties:
    title:
      type: string
      max_len: 40
      desc: "标题, 建议是具体的数据主题, 如 'Q2 营收按地区'。"
    takeaway:
      type: string
      max_len: 80
      desc: "核心结论, 底部 banner 显示。建议一句话 ≤25 字。"
    subtitle:
      type: string
      max_len: 60
      desc: "数据来源/说明, 可选, 右上角小字。"

layout:
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
    w: 9.0
    h: 0.7
    text: "{title}"
    style: title

  # 右上角小 subtitle / 数据来源
  - if: "subtitle"
    shape: text
    x: 9.5
    y: 0.5
    w: 3.4
    h: 0.5
    text: "{subtitle}"
    style: subtitle
    align: right

  - shape: rect
    x: 0.5
    y: 1.05
    w: 12.3
    h: 0.04
    fill: accent

  # 图表占位区 — 浅色 panel 作为 "这里将填入图表" 的视觉提示
  # 坐标: x=0.5 y=1.3 w=12.3 h=4.8 (agent 插入 chart 时用这组数字)
  - shape: rect
    x: 0.5
    y: 1.3
    w: 12.3
    h: 4.8
    fill: panel

  # 提示文字 (会被后续 chart 遮盖, 但万一没画 chart 也提醒 agent)
  - shape: text
    x: 0.5
    y: 3.4
    w: 12.3
    h: 0.6
    text: "[chart placeholder · agent 用 add_bar_chart/add_line_chart 填入此区域]"
    style: card_body
    align: center

  # 底部 takeaway 横幅 (accent 色条)
  - if: "takeaway"
    shape: rect
    x: 0.5
    y: 6.3
    w: 12.3
    h: 0.85
    fill: accent

  - if: "takeaway"
    shape: text
    x: 0.8
    y: 6.3
    w: 11.8
    h: 0.85
    text: "💡  {takeaway}"
    style: card_heading
    valign: middle
    color: bg
---

# T15 Chart Page — 图表页

## 预览

```
┌────────────────────────────────────────────┐
│ {title}                   {subtitle}       │
├──── orange line ──────────────────────────┤
│ ┌────────────────────────────────────────┐│
│ │                                        ││
│ │       [chart placeholder]              ││
│ │    (agent 在这里插入 bar/line chart)   ││
│ │                                        ││
│ └────────────────────────────────────────┘│
│ ╔══ 💡 {takeaway} ═══════════════════════╗│
│ ╚═══════════════════════════════════════╝│
└────────────────────────────────────────────┘
```

## 图表区坐标 (agent 自行插入 chart 用)

```
x = 0.5"    y = 1.3"
w = 12.3"   h = 4.8"
```

## 调用示例

```python
from pptx.util import Inches
from _pptx_helpers import add_bar_chart
from _template_loader import render_from_md

# Step 1: 用模板画好骨架(标题+占位+takeaway)
render_from_md(prs, "corporate/T15_chart_page", params={
    "title": "2026 各季度营收增长",
    "subtitle": "单位：亿元 | 来源：财务部",
    "takeaway": "Q2 同比 +32%, 为四季度中最强增长",
})

# Step 2: 往刚才这张 slide 的占位区域插入真正的 chart
# 注意 add_bar_chart 的坐标要用 Inches() 包一层(EMU 单位)
slide = prs.slides[-1]
add_bar_chart(slide,
    Inches(0.5), Inches(1.3), Inches(12.3), Inches(4.8),   # ← 与占位区一致
    categories=["Q1", "Q2", "Q3", "Q4"],
    series_name="营收",
    values=[280, 370, 330, 350])
```

## 设计说明

- 占位区是一整块 `panel` 色矩形, 其坐标固定为 `(0.5, 1.3, 12.3, 4.8)` 供 chart 调用参考。
- Takeaway 底部 banner 使用 accent 色, 白字,像新闻标语条一样抓眼球。
- 如果不传 `takeaway`, 底部 banner 不渲染, 图表区可适当下延 (但当前固定高度 4.8")。
- subtitle 在右上角, 12pt 小字, 通常放"单位/数据来源/截止时间"。
