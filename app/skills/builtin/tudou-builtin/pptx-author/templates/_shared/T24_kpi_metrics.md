---
id: T24_kpi_metrics
name: KPI Metrics
name_zh: KPI 大数字
category: data
summary: "Title + 3-4 huge metric numbers with labels and deltas."
summary_zh: "标题 + 3-4 个大数字 KPI, 每个含数值/单位/标签/同比变化; 适合业务总览、季报、增长仪表盘。"
when_to_use: |
  - 3-4 个核心指标 (营收 / DAU / 转化率 / NPS)
  - 数字本身是焦点, 文字解读次之
  - 多于 4 个 → 用 T23 卡片; 一个数字 → 直接放大

params_schema:
  type: object
  required: [title, metrics]
  properties:
    title:
      type: string
      max_len: 40
    subtitle:
      type: string
      max_len: 80
      desc: "标题下方的小字 (周期 / 数据来源)。"
    metrics:
      type: array
      min_items: 2
      max_items: 4
      items:
        type: object
        required: [value, label]
        properties:
          value:
            type: string
            max_len: 12
            desc: "大数字本体, 如 '32%' / '¥1.2B' / '99.9%'"
          label:
            type: string
            max_len: 18
            desc: "指标名称, 如 '营收同比' / 'DAU'"
          delta:
            type: string
            max_len: 16
            desc: "同比/环比变化, 如 '+12% YoY'。可选; 字符 '+' 显示绿, '-' 显示红"

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
  - if: "subtitle"
    shape: text
    x: 0.5
    y: 1.2
    w: 12.3
    h: 0.5
    text: "{subtitle}"
    style: subtitle
  # 数字大卡片 - 等宽分布在 12.3" 宽度内
  - for_each: "metric in metrics[:4]"
    index_as: i
    vars:
      n: "len(metrics)"
      cw: "12.3 / max(n, 1) - 0.2"
      cx: "0.5 + i * (12.3 / max(n, 1))"
      cy: 2.4
    children:
      # 卡片底
      - shape: rect
        x: "{cx}"
        y: "{cy}"
        w: "{cw}"
        h: 4.0
        fill: panel
      # 顶部 accent
      - shape: rect
        x: "{cx}"
        y: "{cy}"
        w: "{cw}"
        h: 0.08
        fill: accent
      # 大数字
      - shape: text
        x: "{cx}"
        y: "{cy + 0.6}"
        w: "{cw}"
        h: 1.8
        text: "{metric.value}"
        style: kpi_number
        align: center
        valign: middle
      # 标签
      - shape: text
        x: "{cx}"
        y: "{cy + 2.55}"
        w: "{cw}"
        h: 0.5
        text: "{metric.label}"
        style: card_heading
        align: center
      # delta
      - if: "metric.delta"
        shape: text
        x: "{cx}"
        y: "{cy + 3.15}"
        w: "{cw}"
        h: 0.5
        text: "{metric.delta}"
        style: card_body
        align: center
---

# T24 KPI Metrics — 大数字 KPI 仪表盘

## 预览

```
┌────────────────────────────────────────────┐
│ {title}                                    │
├──── orange line ──────────────────────────┤
│ {subtitle}                                 │
│ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐      │
│ │      │ │      │ │      │ │      │      │
│ │  32% │ │ 12M  │ │ 99.9%│ │ ¥1.2B│      │
│ │      │ │      │ │      │ │      │      │
│ │label │ │label │ │label │ │label │      │
│ │+12%  │ │+8%   │ │stable│ │+25%  │      │
│ └──────┘ └──────┘ └──────┘ └──────┘      │
└────────────────────────────────────────────┘
```

## 调用示例

```python
render_from_md(prs, "corporate/T24_kpi_metrics", params={
    "title": "2026 Q2 业务指标",
    "subtitle": "数据截止 2026-06-30, 来源: 财务部 + 数据中台",
    "metrics": [
        {"value": "+32%",   "label": "营收同比",   "delta": "↑ 行业平均"},
        {"value": "12M",    "label": "MAU",        "delta": "+8% QoQ"},
        {"value": "99.9%",  "label": "服务可用性", "delta": "持平"},
        {"value": "¥1.2B",  "label": "ARR",        "delta": "+25% YoY"},
    ],
})
```

## 设计说明

- 数字使用 `kpi_number` 样式 (一般是大号 bold primary 色, 见 theme.yaml)
- 卡片宽度按数量动态分布: 2 个就两边各占 ~6", 3 个 ~4.1", 4 个 ~3.0"
- 顶部 0.08" accent 条作为锚点
- delta 字段建议格式: "+12% YoY" / "-3% QoQ" / "持平" — 视觉一致

## theme.yaml 需要补 kpi_number 样式

如果你换主题渲染发现数字字号不对, 检查 theme.yaml 是否有:
```yaml
styles:
  kpi_number:  {font: sans, size: 56, bold: true, color: primary}
```
不存在时会回退到默认的 12pt, 数字会显示太小。
