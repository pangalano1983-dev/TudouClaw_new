---
id: T10_comparison
name: Left-Right Comparison
name_zh: 左右对比页
category: compare
summary: "Two-column comparison: left panel vs right panel, with center VS badge."
summary_zh: "左右对照: 左栏 vs 右栏, 中间 VS 徽章; 用于 Before/After、A vs B、竞品对比。"
when_to_use: |
  - 2 个选项/方案/时期/角色 的对照, 每侧有标题+多条要点
  - 经典场景: Before/After, 现状/目标, 方案 A/方案 B, 我们/对手
  - 3+ 列对比 → 改用表格 (T21/T18) 或拆页

params_schema:
  type: object
  required: [title, left, right]
  properties:
    title:
      type: string
      max_len: 40
    vs_text:
      type: string
      max_len: 4
      desc: "中间徽章文字, 默认 'VS'; 也可用 '→' 表示前后对比。"
    left:
      type: object
      required: [label, items]
      properties:
        label:
          type: string
          max_len: 18
          desc: "左栏标题, 如 '传统做法' / '现状'。"
        items:
          type: array
          min_items: 1
          max_items: 5
          items:
            type: string
            max_len: 80
    right:
      type: object
      required: [label, items]
      properties:
        label:
          type: string
          max_len: 18
          desc: "右栏标题, 如 '新做法' / '目标'。"
        items:
          type: array
          min_items: 1
          max_items: 5
          items:
            type: string
            max_len: 80

layout:
  # 底
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

  - shape: rect
    x: 0.5
    y: 1.05
    w: 12.3
    h: 0.04
    fill: accent

  # 左栏 panel 背景
  - shape: rect
    x: 0.5
    y: 1.5
    w: 5.7
    h: 5.5
    fill: panel

  # 左栏 label bar (顶部色条)
  - shape: rect
    x: 0.5
    y: 1.5
    w: 5.7
    h: 0.6
    fill: muted

  - shape: text
    x: 0.5
    y: 1.5
    w: 5.7
    h: 0.6
    text: "{left.label}"
    style: card_heading
    align: center
    valign: middle
    color: bg

  # 左栏 items
  - for_each: "item in left.items[:5]"
    index_as: i
    vars:
      item_y: "2.3 + i * 0.85"
    children:
      - shape: oval
        x: 0.8
        y: "{item_y + 0.15}"
        w: 0.18
        h: 0.18
        fill: muted
      - shape: text
        x: 1.15
        y: "{item_y}"
        w: 4.9
        h: 0.7
        text: "{item}"
        style: card_body

  # 中间 VS 徽章 (圆形)
  - shape: oval
    x: 6.33
    y: 3.55
    w: 0.67
    h: 0.67
    fill: accent

  - shape: text
    x: 6.33
    y: 3.55
    w: 0.67
    h: 0.67
    text: "{vs_text|VS}"
    style: card_heading
    align: center
    valign: middle
    color: bg

  # 右栏 panel (高亮 — 用 accent 系作为 "推荐/目标/新" 侧)
  - shape: rect
    x: 7.13
    y: 1.5
    w: 5.7
    h: 5.5
    fill: panel

  - shape: rect
    x: 7.13
    y: 1.5
    w: 5.7
    h: 0.6
    fill: primary

  - shape: text
    x: 7.13
    y: 1.5
    w: 5.7
    h: 0.6
    text: "{right.label}"
    style: card_heading
    align: center
    valign: middle
    color: bg

  - for_each: "item in right.items[:5]"
    index_as: i
    vars:
      item_y: "2.3 + i * 0.85"
    children:
      - shape: oval
        x: 7.43
        y: "{item_y + 0.15}"
        w: 0.18
        h: 0.18
        fill: primary
      - shape: text
        x: 7.78
        y: "{item_y}"
        w: 4.9
        h: 0.7
        text: "{item}"
        style: card_body
---

# T10 Left-Right Comparison — 左右对比页

## 预览

```
┌────────────────────────────────────────────┐
│ {title}                                    │
├──── orange line ──────────────────────────┤
│ ┌─── left.label ───┐   ┌─── right.label ─┐│
│ │  • item 1         │ VS │  • item 1      ││
│ │  • item 2         │    │  • item 2      ││
│ │  • item 3         │    │  • item 3      ││
│ │  (muted color)    │    │  (primary color)││
│ └───────────────────┘   └─────────────────┘│
└────────────────────────────────────────────┘
```

## 调用示例

```python
render_from_md(prs, "corporate/T10_comparison", params={
    "title": "传统做法 vs 新做法",
    "vs_text": "VS",
    "left": {
        "label": "传统做法",
        "items": [
            "人工盯盘, 延迟 10-30 分钟",
            "每次需求改动走审批周期",
            "数据散落在 5 个系统",
            "故障恢复 SLA 4 小时",
        ],
    },
    "right": {
        "label": "新做法",
        "items": [
            "自动监控, 秒级告警",
            "策略预设, 触发即执行",
            "统一数据湖, 单一入口",
            "故障自愈, RTO < 10 分钟",
        ],
    },
})
```

## 设计说明

- 左栏 panel 顶部 label 用 `muted`(中性灰)色, 暗示"当前/传统/老"。
- 右栏用 `primary` 色, 暗示"目标/新/推荐"。
- 中间 VS 徽章是小圆形(0.67")accent 色, 突出对照关系。
- vs_text 可以换成 "→" 表示 Before→After 单向转变, 或 "vs" 小写等变体。
- Items 每条一行, 建议 ≤40 字; 5 条以内, 超过则拆页。
