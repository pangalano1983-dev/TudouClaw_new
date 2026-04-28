---
id: T09_vertical_timeline
name: Vertical Timeline
name_zh: 垂直时间线
category: timeline
summary: "Vertical timeline with left column of numbered dots, right column of step cards."
summary_zh: "左侧编号圆点 + 连接线, 右侧步骤卡; 用于流程 / 阶段 / 路线图。"
when_to_use: |
  - 有顺序的步骤 / 阶段 / 流程 (3-5 步最佳)
  - 每步有短标题 + 1-2 句说明
  - 如果无顺序关系用 T06 网格; 4 个以上步骤用 T18 横向路线图

params_schema:
  type: object
  required: [title, steps]
  properties:
    title:
      type: string
      max_len: 40
    steps:
      type: array
      min_items: 3
      max_items: 5
      items:
        type: object
        required: [heading, body]
        properties:
          no:
            type: string
            max_len: 2
            desc: "编号, 默认 1/2/3... 可覆盖为 A/B/C 或任意 1-2 字符。"
          heading:
            type: string
            max_len: 24
          body:
            type: string
            max_len: 120

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

  # 垂直连接线 (左侧) — 高度根据 step 数量自动收缩
  - shape: rect
    x: 1.28
    y: 1.6
    w: 0.04
    h: 4.2
    fill: border

  # 步骤圆点 + 文字 — 均匀分布在 1.5" ~ 5.8" 之间 (留底部空间避免越界)
  - for_each: "step in steps"
    index_as: i
    vars:
      row_y: "1.5 + i * (4.3 / max(len(steps) - 1, 1))"
      dot_y: "row_y"
      num_text: "step.no if step.no else str(i+1)"
    children:
      # 圆形编号底
      - shape: oval
        x: 1.0
        y: "{dot_y}"
        w: 0.6
        h: 0.6
        fill: primary

      - shape: text
        x: 1.0
        y: "{dot_y}"
        w: 0.6
        h: 0.6
        text: "{num_text}"
        style: timeline_num
        align: center
        valign: middle

      # 右侧 heading + body
      - shape: text
        x: 2.0
        y: "{dot_y - 0.05}"
        w: 10.5
        h: 0.5
        text: "{step.heading}"
        style: timeline_head

      - shape: text
        x: 2.0
        y: "{dot_y + 0.5}"
        w: 10.5
        h: 0.8
        text: "{step.body}"
        style: timeline_body
---

# T09 Vertical Timeline — 垂直时间线

## 预览

```
┌────────────────────────────────────────┐
│ {title}                                │
├──── orange line ───────────────────────┤
│  (1) {step.heading}                    │
│   |  {step.body}                       │
│   |                                    │
│  (2) {step.heading}                    │
│   |  {step.body}                       │
│   |                                    │
│  (3) {step.heading}                    │
│      {step.body}                       │
└────────────────────────────────────────┘
```

## 调用示例

```python
render_from_md(prs, "corporate/T09_vertical_timeline", params={
    "title": "三步实施路径",
    "steps": [
        {"heading": "规划期",   "body": "明确目标、团队与预算 (4-6 周)"},
        {"heading": "试点期",   "body": "3-5 个业务场景验证 (2 个月)"},
        {"heading": "推广期",   "body": "全量迁移并建立治理体系 (6-9 个月)"},
    ],
})
```

## 设计说明

- 圆点间距自动根据 `steps` 数量平均分布 (见 `row_y` 表达式)。
- 编号可自定义; 默认 1/2/3...
- 圆点用 primary 色, 连接线用 border 色。
