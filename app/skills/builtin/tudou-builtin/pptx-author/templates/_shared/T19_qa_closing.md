---
id: T19_qa_closing
name: Q&A / Closing
name_zh: 收尾 / Q&A 页
category: closing
summary: "Centered closing page: big Q&A or thank-you headline + slogan + contact line."
summary_zh: "报告收尾页: 居中大标题 + slogan + 联系方式。"
when_to_use: |
  - 报告最后一页
  - 可选择 'Q&A' / 'Thank You' / 'Discussion' 作为大标题
  - 不要放任何实质内容 — 是收尾礼仪页

params_schema:
  type: object
  required: [title]
  properties:
    title:
      type: string
      max_len: 20
      desc: "大标题, 如 'Q & A' / 'Thank You' / '下一步讨论'。"
    cta:
      type: string
      max_len: 60
      desc: "slogan / 核心主张, 可选。建议 ≤25 字。"
    contact:
      type: string
      max_len: 60
      desc: "联系方式 / 署名, 可选。"

layout:
  # 满屏底
  - shape: rect
    x: 0
    y: 0
    w: sw
    h: sh
    fill: bg

  # 顶部色块装饰带
  - shape: rect
    x: 0
    y: 0
    w: sw
    h: 0.15
    fill: accent

  # 大标题 (居中)
  - shape: text
    x: 0.5
    y: 2.6
    w: 12.3
    h: 1.4
    text: "{title}"
    style: cover_title
    align: center
    color: primary

  # 橙色分隔横线
  - shape: rect
    x: 5.665
    y: 4.2
    w: 2.0
    h: 0.06
    fill: accent

  # CTA slogan
  - if: "cta"
    shape: text
    x: 1.0
    y: 4.5
    w: 11.33
    h: 0.8
    text: "{cta}"
    style: cta
    align: center

  # 联系方式 (底部)
  - if: "contact"
    shape: text
    x: 1.0
    y: 6.6
    w: 11.33
    h: 0.4
    text: "{contact}"
    style: contact
    align: center

  # 底部色块装饰带
  - shape: rect
    x: 0
    y: 7.35
    w: sw
    h: 0.15
    fill: accent
---

# T19 Q&A / Closing — 收尾页

## 预览

```
╔══════════════════════════════════════════╗
║─── accent bar ───────────────────────────║
║                                          ║
║                                          ║
║              {title}                     ║
║              ──────                      ║
║              {cta}                       ║
║                                          ║
║              {contact}                   ║
║─── accent bar ───────────────────────────║
╚══════════════════════════════════════════╝
```

## 调用示例

```python
render_from_md(prs, "corporate/T19_qa_closing", params={
    "title": "Q & A",
    "cta": "主动构建 — 赢得确定性",
    "contact": "2026 Q2 | contact@example.com",
})
```

## 设计说明

- 顶/底两条 0.15" 高的 accent 色条框住页面。
- 大标题居中 40pt primary 色, 下方 2" 宽 accent 短线。
- CTA + contact 居中排列; 都是可选的。
