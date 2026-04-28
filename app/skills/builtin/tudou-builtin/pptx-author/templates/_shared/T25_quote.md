---
id: T25_quote
name: Quote / Pull Quote
name_zh: 引言页
category: rhetorical
summary: "Centered large pull-quote with attribution. Empty space around it."
summary_zh: "居中大引号 + 一段名言/引述 + 署名;留白突出文字本身,适合分节过渡或 punchline 页。"
when_to_use: |
  - 章节过渡页, 用一句话点题
  - 客户证言 / 行业大佬观点引用
  - 团队价值观 / 标语 punchline
  - 不要塞数据 (用 T24) 或要点列表 (用 T02/T06)

params_schema:
  type: object
  required: [quote]
  properties:
    quote:
      type: string
      max_len: 200
      desc: "引述正文,建议 30-80 字。"
    author:
      type: string
      max_len: 30
      desc: "署名 (人名 / 公司 / 来源)。可选。"
    author_title:
      type: string
      max_len: 60
      desc: "署名后的头衔/角色, 如 'CEO @ Acme'。可选。"

layout:
  - shape: rect
    x: 0
    y: 0
    w: sw
    h: sh
    fill: bg
  # 大左引号 (装饰)
  - shape: text
    x: 0.5
    y: 0.5
    w: 2.0
    h: 2.0
    text: "❝"
    style: quote_mark
    align: left
    color: accent
  # 引文居中
  - shape: text
    x: 1.5
    y: 2.5
    w: 10.3
    h: 2.5
    text: "{quote}"
    style: quote_text
    align: center
    valign: middle
  # 短分隔线
  - shape: rect
    x: 5.665
    y: 5.4
    w: 2.0
    h: 0.04
    fill: accent
  - if: "author"
    shape: text
    x: 1.5
    y: 5.6
    w: 10.3
    h: 0.5
    text: "— {author}"
    style: card_heading
    align: center
  - if: "author_title"
    shape: text
    x: 1.5
    y: 6.15
    w: 10.3
    h: 0.4
    text: "{author_title}"
    style: subtitle
    align: center
  # 大右引号
  - shape: text
    x: 10.83
    y: 5.0
    w: 2.0
    h: 2.0
    text: "❞"
    style: quote_mark
    align: right
    color: accent
---

# T25 Quote — 引言页

## 预览

```
┌────────────────────────────────────────────┐
│ ❝                                          │
│                                            │
│       "Quoted text — usually 1-2           │
│        sentences. Center, large font.      │
│        Lots of breathing room."            │
│                                            │
│              ──                            │
│                                            │
│              — Author Name                 │
│              CEO @ Acme                    │
│                                            │
│                                       ❞   │
└────────────────────────────────────────────┘
```

## 调用示例

```python
render_from_md(prs, "corporate/T25_quote", params={
    "quote": "未来不属于做事最快的公司, 而属于学习最快的公司。",
    "author": "Reid Hoffman",
    "author_title": "联合创始人, LinkedIn",
})
```

## 设计说明

- ❝/❞ 引号使用 quote_mark 样式 (建议 100pt+ accent 色),装饰用,不必读出。
- 引文使用 quote_text 样式 (建议 28-32pt italic 或 light weight)。
- 整页只有引文一件主要事物,留白超过 50%,这是预期效果。
- 章节过渡页放这个,后面紧跟 T04_section_divider 或正文页。

## theme.yaml 需要的样式

```yaml
styles:
  quote_mark:  {font: sans, size: 120, bold: false, color: accent}
  quote_text:  {font: sans, size: 28,  bold: false, color: text}
```
