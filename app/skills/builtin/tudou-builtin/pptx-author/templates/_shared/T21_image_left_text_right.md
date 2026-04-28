---
id: T21_image_left_text_right
name: Image Left, Text Right
name_zh: 左图右文
category: media
summary: "Big image on left (~45%), heading + bullets on right (~55%)."
summary_zh: "左侧大图(45%) + 右侧标题与要点(55%); 用于产品截图、案例展示、数据可视化解读。"
when_to_use: |
  - 一张图(产品截图 / 架构图 / 数据图) 是主角,旁边解读
  - 同样的内容反过来 (左文右图) 也可,把 image_left=false 即可
  - 只有文字 → 用 T02 / T06; 只有图 → 用 T15

params_schema:
  type: object
  required: [title, image_path]
  properties:
    title:
      type: string
      max_len: 40
    image_path:
      type: string
      desc: "图片绝对路径或相对 workspace 路径 (.png/.jpg)。"
    image_caption:
      type: string
      max_len: 60
      desc: "图片下方说明,可选。"
    heading:
      type: string
      max_len: 30
      desc: "右侧文字区主标题,可选 (默认为空)。"
    bullets:
      type: array
      min_items: 1
      max_items: 6
      items:
        type: string
        max_len: 100
      desc: "右侧要点列表 (1-6 条最佳)。"

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
  # 左侧图片框 (45%)
  - shape: rect
    x: 0.5
    y: 1.4
    w: 5.5
    h: 5.5
    fill: panel
  - shape: image
    path: "{image_path}"
    x: 0.5
    y: 1.4
    w: 5.5
    h: 5.5
    fit: contain
  - if: "image_caption"
    shape: text
    x: 0.5
    y: 6.95
    w: 5.5
    h: 0.4
    text: "{image_caption}"
    style: subtitle
    align: center
  # 右侧文字 (55%)
  - if: "heading"
    shape: text
    x: 6.4
    y: 1.5
    w: 6.4
    h: 0.6
    text: "{heading}"
    style: card_heading
  - shape: rect
    x: 6.4
    y: 2.15
    w: 0.6
    h: 0.04
    fill: accent
  - for_each: "bullet in bullets[:6]"
    index_as: i
    vars:
      by: "2.4 + i * 0.8"
    children:
      - shape: oval
        x: 6.4
        y: "{by + 0.18}"
        w: 0.18
        h: 0.18
        fill: primary
      - shape: text
        x: 6.7
        y: "{by}"
        w: 6.1
        h: 0.7
        text: "{bullet}"
        style: card_body
---

# T21 Image Left, Text Right — 左图右文

## 预览

```
┌──────────────────────────────────────────┐
│ {title}                                  │
├──── orange line ────────────────────────┤
│ ┌────────────┐  {heading}                │
│ │            │  ──                       │
│ │            │  • bullet 1               │
│ │  [image]   │  • bullet 2               │
│ │            │  • bullet 3               │
│ └────────────┘  • ...                    │
│ {caption}                                │
└──────────────────────────────────────────┘
```

## 调用示例

```python
render_from_md(prs, "corporate/T21_image_left_text_right", params={
    "title": "新版产品截图与亮点",
    "image_path": "/workspace/screenshots/dashboard.png",
    "image_caption": "管理员仪表盘 v2.0",
    "heading": "三大改进",
    "bullets": [
        "数据加载速度提升 3 倍",
        "新增多维筛选与导出功能",
        "支持主题切换 (亮 / 暗 / 自动)",
        "全面适配移动端与平板",
    ],
})
```

## 设计说明

- 图片区按 fit=contain 缩放,不变形不裁剪。图片不存在时显示 panel 灰底兜底。
- 右侧文字区竖排小圆点列表,每条占一行,最多 6 条。
- 如需图右文左,可调换 x 坐标或新增 T21_text_left_image_right。
