---
name: pptx_advanced
description: '高级PPTX制作技能。当需要制作精美、专业的演示文稿时使用此技能。
  支持信息图表、图表、多栏布局、流程图、时间轴等高级元素。
  包含完整的制作流程：结构规划→内容填充→审美优化→生成输出。'
license: MIT
metadata:
  source: tudou
  tags:
    - pptx
    - presentation
    - infographic
    - chart
    - report
---
# PPTX Advanced Maker — 高级演示文稿制作技能

## 制作流程（必须严格遵守）

```
Phase 1: 结构规划  →  确定页面数、每页布局类型、信息架构
Phase 2: 内容填充  →  将文字/数据/图表嵌入各页对应位置
Phase 3: 审美优化  →  配色主题、字体层级、间距对齐、视觉一致性
Phase 4: 生成输出  →  调用 create_pptx_advanced 工具 + QA校验
```

---

## Phase 1: 结构规划

### 1.1 确定页面类型

每页必须选定一个布局模式：

| 布局代号 | 适用场景 | 要素 |
|----------|----------|------|
| `cover` | 封面页 | 大标题 + 副标题 + 日期/作者 |
| `toc` | 目录页 | 编号列表 + 页码引用 |
| `section` | 章节分隔页 | 章节号 + 章节名 + 图标 |
| `title_content` | 标题+正文 | 标题栏 + 正文区域 |
| `two_column` | 双栏对比 | 左右两栏内容 |
| `three_column` | 三栏并列 | 三等分内容区 |
| `grid_2x2` | 四宫格 | 2x2 卡片网格 |
| `grid_2x3` | 六宫格 | 2x3 卡片网格 |
| `chart` | 图表页 | 标题 + 图表（柱/饼/环/折线）|
| `process` | 流程图 | 步骤箭头/圆形流程 |
| `timeline` | 时间轴 | 横向/纵向时间线 |
| `comparison` | 对比页 | 左右对比（优劣/前后）|
| `kpi` | 数据看板 | 大数字KPI + 说明文字 |
| `infographic` | 信息图表 | 自定义图形组合 |
| `closing` | 结束页 | 致谢 + 联系方式 |

### 1.2 结构规划输出格式

在制作前，先输出结构大纲：

```
演示文稿结构:
  主题: [演示主题]
  配色: [主色/辅色/强调色]
  总页数: N

  P1: cover — 封面
  P2: toc — 目录
  P3: section — 第一章节
  P4: two_column — 核心对比分析
  P5: chart — 销售数据图表
  P6: process — 实施流程
  P7: kpi — 关键指标
  P8: closing — 结束
```

---

## Phase 2: 内容填充

### ⭐ 2.0 智能布局模式（强烈推荐）

**优先使用 `layout` 字段，让工具自动计算坐标！** 不需要手动填 x/y/w/h，不会溢出。

每页 slide 设置 `"layout": {"type": "布局类型", "title": "标题", "items": [...]}` 即可。

**可用布局类型：**

| 布局类型 | 说明 | items 格式 |
|----------|------|------------|
| `cover` | 封面页（左侧色块+标题） | 无需items，用 title/subtitle/date/author |
| `toc` | 目录页（2列网格） | `[{"num":"01","text":"概述"}, ...]` |
| `section` | 章节分隔页 | 无需items，用 num/title/subtitle |
| `cards` | N卡片自动排列(1-9个) | `[{"title":"..","detail":"..","icon":"01"}, ...]` |
| `process` | 流程步骤+箭头连接 | `[{"title":"步骤1","detail":"说明"}, ...]` |
| `kpi` | 数据看板（大数字） | `[{"value":"99%","label":"准确率","icon":"★"}, ...]` |
| `comparison` | 左右对比 | 用 left/right: `{"title":"..","items":["..",".."]}`  |
| `timeline` | 时间轴 | `[{"date":"2024-Q1","text":"里程碑"}, ...]` |
| `chart` | 图表页框架 | 用 description，chart 在 elements 中手动添加 |
| `table` | 表格页 | 用 headers/rows/summary |
| `closing` | 结束页 | 无需items，用 title/subtitle/contact |

**示例 — 一个完整的 4 页 PPTX：**
```json
{
  "output_path": "report.pptx",
  "theme": {"primary":"1E40AF","secondary":"1E293B","accent":"3B82F6","background":"FFFFFF"},
  "slides": [
    {"layout": {"type":"cover","title":"项目报告","subtitle":"2026年Q1","author":"张三"}},
    {"layout": {"type":"process","title":"实施流程","page_num":2,
                "items":[{"title":"调研","detail":"需求分析"},{"title":"设计","detail":"架构评审"},{"title":"开发","detail":"编码测试"}]}},
    {"layout": {"type":"kpi","title":"关键指标","page_num":3,
                "items":[{"value":"128","label":"完成任务","icon":"✓"},{"value":"96%","label":"达标率","icon":"★"}]}},
    {"layout": {"type":"closing","title":"Thank You","subtitle":"期待合作"}}
  ]
}
```

> **layout + elements 可以组合使用**：layout 生成基础排版，elements 追加额外元素（如手动加一个 chart 或 image）。

### 2.0b 手动坐标模式（备用）

当 layout 不能满足特殊需求时，使用 `elements` 手动控制。注意安全区域：

```
幻灯片尺寸: 10.0 x 5.625 英寸 (16:9 宽屏)
坐标规则: x + w ≤ 9.8，y + h ≤ 5.5（工具会自动修正溢出，但仍应注意）
```

### 2.1 调用 create_pptx_advanced 工具

优先用 layout 模式，复杂/自定义页面用 elements 手动控制。两者可混用。

### 2.2 元素类型速查

每个 element 必须包含 `type` 和定位参数 `x, y, w, h`（单位: 英寸）：

#### 文本元素 `text`
```json
{
  "type": "text",
  "content": "标题文字",
  "x": 0.5, "y": 0.3, "w": 9, "h": 0.8,
  "font_size": 36, "font_name": "Microsoft YaHei",
  "bold": true, "color": "FFFFFF",
  "align": "center", "valign": "middle",
  "bg_color": "E8590C"
}
```

#### 形状元素 `shape`
```json
{
  "type": "shape",
  "shape_type": "rectangle",
  "x": 0, "y": 0, "w": 10, "h": 1.2,
  "fill_color": "E8590C",
  "line_color": "",
  "line_width": 0
}
```
shape_type 可选: `rectangle`, `rounded_rect`, `oval`, `triangle`, `arrow_right`, `arrow_left`, `chevron`, `diamond`, `pentagon`, `hexagon`, `star`

#### 图表元素 `chart`
```json
{
  "type": "chart",
  "chart_type": "pie",
  "x": 1, "y": 1.5, "w": 4.5, "h": 3.5,
  "categories": ["产品A", "产品B", "产品C"],
  "series": [
    {"name": "占比", "values": [45, 35, 20]}
  ],
  "colors": ["E8590C", "2B2B2B", "F4A261"],
  "show_labels": true,
  "show_percent": true
}
```
chart_type 可选: `bar`, `column`, `line`, `pie`, `doughnut`, `radar`, `area`

#### 表格元素 `table`
```json
{
  "type": "table",
  "x": 0.5, "y": 1.5, "w": 9, "h": 3,
  "headers": ["指标", "Q1", "Q2", "Q3", "Q4"],
  "rows": [
    ["营收(万)", "120", "145", "160", "190"],
    ["利润率", "15%", "18%", "20%", "22%"]
  ],
  "header_color": "E8590C",
  "header_font_color": "FFFFFF",
  "stripe_color": "FFF0E6"
}
```

#### 图片元素 `image`
```json
{
  "type": "image",
  "path": "/path/to/image.png",
  "x": 6, "y": 1, "w": 3.5, "h": 3.5
}
```

#### 图标圆形 `icon_circle`
```json
{
  "type": "icon_circle",
  "text": "01",
  "x": 1, "y": 2, "w": 0.8, "h": 0.8,
  "fill_color": "E8590C",
  "font_color": "FFFFFF",
  "font_size": 16
}
```

#### 线条/分隔线 `line`
```json
{
  "type": "line",
  "x": 0.5, "y": 1.2, "w": 9, "h": 0,
  "line_color": "CCCCCC",
  "line_width": 1
}
```

### 2.3 预置布局模板

以下是常用布局的元素组合参考：

#### 封面页 Cover
```
背景色块 (shape: 0,0 → 10,5.63)
标题 (text: 居中, 36pt, 白色, 粗体)
副标题 (text: 居中, 18pt, 白色/半透明)
日期 (text: 底部居中, 12pt)
装饰线 (line: 标题下方)
```

#### 双栏页 Two Column
```
标题栏 (shape背景 + text标题)
左栏标题 (text: x=0.5, w=4.2, 粗体)
左栏内容 (text: x=0.5, w=4.2)
右栏标题 (text: x=5.3, w=4.2, 粗体)
右栏内容 (text: x=5.3, w=4.2)
分隔线 (line: x=5, 垂直)
```

#### 四宫格 Grid 2x2
```
标题栏
卡片1 (shape背景 + icon_circle + text) — x=0.3, y=1.3, w=4.5, h=2.0
卡片2 (shape背景 + icon_circle + text) — x=5.2, y=1.3, w=4.5, h=2.0
卡片3 (shape背景 + icon_circle + text) — x=0.3, y=3.5, w=4.5, h=2.0
卡片4 (shape背景 + icon_circle + text) — x=5.2, y=3.5, w=4.5, h=2.0
```

#### 流程页 Process (横向3步，带卡片)
```
标题栏 (shape背景 + text标题)
卡片1 (rounded_rect: x=0.5, w=2.8, h=2.0, 浅色填充)
  icon_circle (x=0.7, w=0.7) + 标题text + 说明text
箭头1 (arrow_right: x=3.4, w=0.3)
卡片2 (rounded_rect: x=3.8, w=2.8)
  icon_circle + 标题 + 说明
箭头2 (arrow_right: x=6.7, w=0.3)
卡片3 (rounded_rect: x=7.1, w=2.8)  ← 7.1+2.8=9.9 ✓ 不溢出
  icon_circle + 标题 + 说明
```

#### 流程页 Process (横向4步，紧凑)
```
标题栏
步骤1圆 (icon_circle: x=0.8, w=0.7)  → 箭头 (shape:arrow_right: x=1.7) → 
步骤2圆 (icon_circle: x=3.1)  → 箭头 → 
步骤3圆 (icon_circle: x=5.4)  → 箭头 → 
步骤4圆 (icon_circle: x=7.7)
每步下方 (text: 步骤名 + 说明, w=2.0)
```

#### KPI数据看板 (3列)
```
标题栏
KPI1: 大数字 (text: 48pt, 主色) + 标签 (text: 14pt, 灰色) — x=0.5, w=2.8
KPI2: 大数字 + 标签 — x=3.6, w=2.8
KPI3: 大数字 + 标签 — x=6.7, w=2.8
```

---

## Phase 3: 审美优化

### 3.1 配色方案

必须在 Phase 1 确定配色，整个演示文稿严格执行。

| 方案名 | 主色 | 辅色 | 强调色 | 背景色 | 适用场景 |
|--------|------|------|--------|--------|----------|
| 商务橙 | `E8590C` | `2B2B2B` | `F4A261` | `FFF8F0` | 年度报告、工作总结 |
| 科技蓝 | `1E40AF` | `1E293B` | `3B82F6` | `F0F4FF` | 技术方案、产品介绍 |
| 极简灰 | `374151` | `6B7280` | `10B981` | `F9FAFB` | 数据分析、研究报告 |
| 活力绿 | `059669` | `1F2937` | `34D399` | `F0FDF4` | 环保、健康、增长 |
| 优雅紫 | `7C3AED` | `1E1B4B` | `A78BFA` | `FAF5FF` | 创意、教育、文化 |
| 热情红 | `DC2626` | `1C1917` | `F87171` | `FFF1F2` | 营销、庆典、激励 |
| 沉稳靛 | `1E3A5F` | `0F172A` | `60A5FA` | `EFF6FF` | 金融、政务、法律 |

### 3.2 字体层级

| 层级 | 字号 | 字重 | 用途 |
|------|------|------|------|
| H1 | 36-44pt | Bold | 封面标题 |
| H2 | 24-28pt | Bold | 页面标题 |
| H3 | 18-20pt | Bold | 区块标题/小标题 |
| Body | 14-16pt | Regular | 正文内容 |
| Caption | 10-12pt | Regular | 注释、来源、页码 |
| KPI | 42-60pt | Bold | 大数字/统计值 |

中文推荐字体: `Microsoft YaHei`, `SimHei`（标题）, `SimSun`（正文）
英文推荐字体: `Arial`（正文）, `Impact`（标题）, `Calibri`（通用）

### 3.3 间距规范

- 页面边距: ≥ 0.5 英寸
- 元素间距: 0.15 - 0.3 英寸
- 标题与内容间: 0.2 - 0.4 英寸
- 卡片内边距: 0.15 - 0.2 英寸
- 底部留白: ≥ 0.3 英寸

### 3.4 视觉装饰技巧（提升专业感）

没有真实图片时，用以下纯图形手法让幻灯片更专业：

**装饰色块**
- 封面/结束页: 左侧 30% 放一个主色竖条 (shape: x=0,y=0,w=3,h=5.63) 作为视觉锚点
- 标题栏: 顶部放一个主色横条 (shape: x=0,y=0,w=10,h=1) + 白色标题文字
- 底部装饰线: 每页底部放一条细线 (line: x=0.5,y=5.3,w=9,h=0,line_color=accent)

**图标圆形（代替图片）**
- 编号圆: 每个要点/步骤前放 icon_circle (w=0.7,h=0.7) 带编号 01/02/03
- 特征图标: 用彩色圆形 + 文字符号代替图标，例如 "✓", "★", "→", "◆", "$", "📊"
- KPI 前缀: 大数字上方放一个小的 icon_circle 作为类别标识

**形状组合**
- 卡片背景: 用浅色 rounded_rect (fill_color=背景色变体, 如 F0F4FF) 衬托内容
- 对比箭头: 两栏对比用 arrow_right 连接
- 分组框: 用无填充 rounded_rect + 浅色边框 (line_color) 将相关内容框在一起

**视觉层次原则**
- 每页至少 2 种元素类型（不要只有 text）
- 装饰色块在 elements 数组最前面（z-order 最底层）
- icon_circle 用主色/强调色，文字用白色，形成视觉焦点
- 色块面积不超过页面 30%，留足呼吸空间

### 3.5 视觉一致性检查清单

- [ ] 所有页面使用同一配色方案
- [ ] 标题位置、字号、颜色全部统一
- [ ] 相同类型的元素大小、间距一致
- [ ] 强调色只用于关键信息（不超过20%面积）
- [ ] 每页至少一个视觉元素（不能纯文字）
- [ ] 没有元素溢出页面边界（每个元素: x+w ≤ 9.8, y+h ≤ 5.5）
- [ ] 三栏布局每列 w ≤ 2.8（不要用 4.5！）
- [ ] 中英文字体匹配

---

## Phase 4: 生成输出

### 4.1 工具调用示例

完整的 `create_pptx_advanced` 调用:

```json
{
  "output_path": "财务部年度报告.pptx",
  "theme": {
    "primary": "E8590C",
    "secondary": "2B2B2B",
    "accent": "F4A261",
    "background": "FFFFFF",
    "title_font": "Microsoft YaHei",
    "body_font": "Microsoft YaHei"
  },
  "slides": [
    {
      "layout": "blank",
      "background": "2B2B2B",
      "elements": [
        {"type": "shape", "shape_type": "rectangle", "x": 0, "y": 0, "w": 10, "h": 5.63, "fill_color": "2B2B2B"},
        {"type": "shape", "shape_type": "rectangle", "x": 0.3, "y": 2.0, "w": 0.08, "h": 1.5, "fill_color": "E8590C"},
        {"type": "text", "content": "2024-2025年度", "x": 0.6, "y": 1.8, "w": 8, "h": 0.5, "font_size": 16, "color": "F4A261"},
        {"type": "text", "content": "财务部工作总结汇报", "x": 0.6, "y": 2.3, "w": 8, "h": 1.0, "font_size": 40, "bold": true, "color": "FFFFFF"},
        {"type": "text", "content": "汇报人: 张三 | 2025年1月", "x": 0.6, "y": 4.8, "w": 5, "h": 0.4, "font_size": 12, "color": "999999"}
      ]
    },
    {
      "layout": "blank",
      "elements": [
        {"type": "shape", "shape_type": "rectangle", "x": 0, "y": 0, "w": 10, "h": 1.0, "fill_color": "E8590C"},
        {"type": "text", "content": "005 | 市场营销组合分析", "x": 0.5, "y": 0.15, "w": 9, "h": 0.7, "font_size": 22, "bold": true, "color": "FFFFFF"},
        {"type": "chart", "chart_type": "doughnut", "x": 0.5, "y": 1.3, "w": 4.5, "h": 3.8, "categories": ["产品", "价格", "渠道", "促销"], "series": [{"name": "占比", "values": [30, 25, 25, 20]}], "colors": ["E8590C", "F4A261", "2B2B2B", "888888"]},
        {"type": "text", "content": "4P营销分析", "x": 5.5, "y": 1.3, "w": 4, "h": 0.5, "font_size": 20, "bold": true, "color": "2B2B2B"},
        {"type": "text", "content": "Product: 产品策略优化升级\nPrice: 差异化定价策略\nPlace: 全渠道覆盖布局\nPromotion: 数字化营销转型", "x": 5.5, "y": 2.0, "w": 4, "h": 3.0, "font_size": 14, "color": "555555", "line_spacing": 1.5}
      ]
    }
  ]
}
```

### 4.2 QA 校验

生成后必须检查:
1. 文件可正常打开
2. 所有文字无截断/溢出
3. 图表数据正确
4. 配色一致
5. 间距合理

---

## 常见信息图表配方

### SWOT分析 (四宫格)
```
左上(绿): Strengths   右上(蓝): Weaknesses
左下(橙): Opportunities  右下(红): Threats
每格: shape背景 + 标题text + 内容text
```

### PDCA循环 (四圆环)
```
Plan(蓝) → Do(绿) → Check(橙) → Act(红)
四个icon_circle + 四个箭头shape + 说明text
```

### 漏斗图 (4层)
```
层1: shape(宽9, 高0.8, 主色)   — "认知"
层2: shape(宽7, 高0.8, 浅主色) — "兴趣"
层3: shape(宽5, 高0.8, 更浅)   — "决策"
层4: shape(宽3, 高0.8, 强调色) — "行动"
居中排列，每层递减
```

### 3C分析 (三角形布局)
```
顶部: icon_circle "Company"
左下: icon_circle "Customer"  
右下: icon_circle "Competitor"
三者之间: line连接 + 关系说明text
```
