---
id: T26_process_flow
name: Process Flow (Horizontal Arrows)
name_zh: 横向流程图
category: process
summary: "3-5 step horizontal arrow chain with title + body per step."
summary_zh: "3-5 步横向箭头链条,每步含标题+一句简介; 用于流程图、用户旅程、转化漏斗、SOP 步骤。"
when_to_use: |
  - 有顺序的流程,且每步彼此推进 (箭头表达"先后")
  - 不需要时间维度 (用 T09 时间线)
  - 不需要并列对照 (用 T06)

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
        required: [heading]
        properties:
          heading:
            type: string
            max_len: 14
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
  # 流程链条 - 等距分布
  - for_each: "step in steps"
    index_as: i
    vars:
      n: "len(steps)"
      step_w: "(12.3 - 0.5 * (max(n, 1) - 1)) / max(n, 1)"
      cx: "0.5 + i * (step_w + 0.5)"
      cy: 2.6
      arrow_x: "0.5 + i * (step_w + 0.5) + step_w"
      arrow_y: 3.7
      is_last: "i == n - 1"
    children:
      # 步骤圆角块
      - shape: rect
        x: "{cx}"
        y: "{cy}"
        w: "{step_w}"
        h: 2.4
        fill: panel
      # 顶部 accent
      - shape: rect
        x: "{cx}"
        y: "{cy}"
        w: "{step_w}"
        h: 0.06
        fill: accent
      # 序号圆点
      - shape: oval
        x: "{cx + step_w/2 - 0.3}"
        y: "{cy + 0.3}"
        w: 0.6
        h: 0.6
        fill: primary
      - shape: text
        x: "{cx + step_w/2 - 0.3}"
        y: "{cy + 0.3}"
        w: 0.6
        h: 0.6
        text: "{str(i+1)}"
        style: timeline_num
        align: center
        valign: middle
      # 标题
      - shape: text
        x: "{cx + 0.1}"
        y: "{cy + 1.05}"
        w: "{step_w - 0.2}"
        h: 0.55
        text: "{step.heading}"
        style: card_heading
        align: center
      # 描述
      - shape: text
        x: "{cx + 0.15}"
        y: "{cy + 1.65}"
        w: "{step_w - 0.3}"
        h: 0.7
        text: "{step.body|}"
        style: card_body
        align: center
      # 箭头 (除最后一步)
      - if: "not is_last"
        shape: text
        x: "{arrow_x + 0.05}"
        y: "{arrow_y - 0.4}"
        w: 0.4
        h: 0.8
        text: "→"
        style: arrow
        align: center
        valign: middle
        color: accent
---

# T26 Process Flow — 横向流程图

## 预览

```
┌────────────────────────────────────────────────┐
│ {title}                                        │
├──── orange line ──────────────────────────────┤
│ ┌────┐    ┌────┐    ┌────┐    ┌────┐        │
│ │ ① │ →  │ ② │ →  │ ③ │ →  │ ④ │        │
│ │head│    │head│    │head│    │head│        │
│ │body│    │body│    │body│    │body│        │
│ └────┘    └────┘    └────┘    └────┘        │
└────────────────────────────────────────────────┘
```

## 调用示例

```python
render_from_md(prs, "corporate/T26_process_flow", params={
    "title": "客户成功四步法",
    "steps": [
        {"heading": "需求识别", "body": "倾听 + 提问, 锁定真实痛点"},
        {"heading": "方案设计", "body": "差异化方案,匹配客户场景"},
        {"heading": "落地实施", "body": "分阶段交付,设定验收标准"},
        {"heading": "持续运营", "body": "数据驱动迭代,定期复盘"},
    ],
})
```

## 设计说明

- 步骤宽度按数量动态计算,3 步每个 ~3.93", 5 步每个 ~2.30"。
- 步骤之间留 0.5" 间距,中央放 `→` 箭头。
- 序号圆点 0.6" 圆,primary 色 + 白字。
- 4-5 步是最佳;再多建议拆两页。

## theme.yaml 可选样式

```yaml
styles:
  arrow: {font: sans, size: 36, bold: true, color: accent}
```
不存在时回退到默认 12pt, 箭头会偏小。
