# 数据分析模版 (Data Analysis Template)

**tags:** data-analysis, analytics, a-b-testing, insights
**roles:** Data Analyst, Product Analyst, Business Analyst
**category:** Analytics

## 目标 (Objective)

收集、分析和解释数据，提供可操作的洞察和业务建议。

## 数据收集方法 (Data Collection Methodology)

### 数据源识别 (Data Source Identification)

```
主要数据源:
[ ] 应用分析 (Google Analytics, Mixpanel)
[ ] 用户行为追踪 (事件数据)
[ ] 产品指标 (内部日志)
[ ] 数据库 (SQL 查询)
[ ] 调查问卷 (问卷系统)
[ ] 用户访谈 (定性反馈)
[ ] 竞争对手数据 (市场研究)
[ ] 外部数据源 (API, 数据供应商)

数据质量检查:
[ ] 数据完整性: [X]% 完整
[ ] 数据准确性: [描述验证方法]
[ ] 数据一致性: [检查冲突]
[ ] 数据及时性: [更新频率]
```

### 事件追踪设计 (Event Tracking Design)

```
事件命名规范: {category}_{action}_{object}

用户行为事件:
[ ] user_sign_up - 用户注册
[ ] user_login - 用户登录
[ ] user_logout - 用户登出

功能事件:
[ ] feature_view - 查看特性
[ ] feature_click - 点击按钮
[ ] feature_submit - 提交表单

事务事件:
[ ] order_created - 创建订单
[ ] order_completed - 订单完成
[ ] order_cancelled - 订单取消

每个事件包含:
{
  "event_name": "user_purchase",
  "timestamp": "2024-01-01T12:00:00Z",
  "user_id": "user_123",
  "session_id": "session_456",
  "properties": {
    "product_id": "prod_789",
    "amount": 99.99,
    "currency": "USD"
  }
}
```

### 调查问卷设计 (Survey Design)

#### 问卷类型 (Survey Types)

```
NPS (净推荐值):
[ ] "您有多大可能向朋友推荐我们?"
    评分: 1-10
    分类: 批评者 (1-6), 中立 (7-8), 推荐者 (9-10)
    计算: (推荐者% - 批评者%) × 100

CES (客户工作量评分):
[ ] "与我们交互的难度?"
    评分: 1-7 (非常简单-非常困难)

CSAT (客户满意度):
[ ] "您对我们的服务满意吗?"
    评分: 1-5 (非常不满意-非常满意)
```

#### 问卷设计最佳实践

- [ ] 问题简洁清晰
- [ ] 避免引导性问题
- [ ] 混合定量和定性
- [ ] 问题排序合理
- [ ] 答案选项互斥
- [ ] 不超过 10 个问题
- [ ] 包含跳过逻辑

## 统计分析 (Statistical Analysis)

### 描述性统计 (Descriptive Statistics)

```
基本指标:

中心趋势:
[ ] 平均值 (Mean): Σx / n
[ ] 中位数 (Median): 中间值
[ ] 众数 (Mode): 最频繁值

分散度:
[ ] 范围 (Range): 最大 - 最小
[ ] 方差 (Variance): σ²
[ ] 标准差 (Std Dev): σ
[ ] 四分位间距 (IQR): Q3 - Q1

示例 Python 代码:

import pandas as pd
import numpy as np

data = pd.read_csv('data.csv')

# 描述性统计
print(data.describe())

# 更详细的统计
print(f"均值: {data['price'].mean()}")
print(f"中位数: {data['price'].median()}")
print(f"标准差: {data['price'].std()}")
```

### 假设检验 (Hypothesis Testing)

```
流程:

1. 建立假设
   H0 (零假设): 无差异
   H1 (备择假设): 存在差异

2. 选择显著性水平
   α = 0.05 (5% 显著性)

3. 选择统计检验
   [ ] t-test - 比较两个均值
   [ ] χ² test - 分类数据
   [ ] ANOVA - 多组比较
   [ ] Mann-Whitney U - 非参数测试

4. 计算 p 值
   如果 p < α: 拒绝 H0 (显著)
   如果 p ≥ α: 无法拒绝 H0

示例: A/B 测试
H0: 版本 A 和 B 的转换率相同
H1: 版本 A 和 B 的转换率不同

结果解释:
- p < 0.05: 差异显著，选择更好的版本
- p ≥ 0.05: 无显著差异，需要更多数据
```

### 相关性分析 (Correlation Analysis)

```
皮尔逊相关系数 (Pearson Correlation):
范围: -1 到 +1

r > 0.7: 强正相关
0.3 < r < 0.7: 中等相关
r < 0.3: 弱相关

示例:
import pandas as pd

correlation = df[['price', 'rating', 'reviews']].corr()

print(correlation)

# 输出:
#        price  rating  reviews
# price    1.00    0.45    0.62
# rating   0.45    1.00    0.58
# reviews  0.62    0.58    1.00

关键点:
[ ] 相关性 ≠ 因果性
[ ] 检查离群值影响
[ ] 考虑时间序列效应
```

## 数据可视化最佳实践 (Data Visualization Best Practices)

### 图表选择 (Chart Selection)

```
场景                  推荐图表
─────────────────────────────────────
比较数值              条形图、柱形图
显示趋势              折线图
显示组成              饼图、堆积图
显示分布              直方图、箱线图
显示相关性            散点图
地理数据              地图
时间序列              折线图
多维数据              热力图

避免:
[ ] 三维图表（难以阅读）
[ ] 太多颜色（超过 5 种）
[ ] 装饰性图表（只展示数据）
```

### 可视化原则 (Visualization Principles)

- [ ] 清晰标题（回答"是什么"）
- [ ] 轴标签清晰（包括单位）
- [ ] 图例位置适当
- [ ] 配色辅助理解
- [ ] 避免数据扭曲
- [ ] 移除无关元素
- [ ] 一个图表一个主要信息

### 工具 (Tools)

```
Excel/Google Sheets:
- 简单图表
- 快速分析

Tableau/Power BI:
- 交互式仪表板
- 大数据量

Python (Matplotlib/Seaborn/Plotly):
- 自定义可视化
- 可重现分析

JavaScript (D3.js, Plotly.js):
- Web 交互式图表
```

## 洞察报告 (Insight Reporting)

### 报告结构 (Report Structure)

```
1. 执行摘要 (Executive Summary)
   - 关键发现（3-5 个）
   - 主要建议
   - 业务影响

2. 背景 (Background)
   - 分析目标
   - 时间周期
   - 数据范围

3. 方法论 (Methodology)
   - 数据源
   - 分析方法
   - 局限性

4. 发现 (Findings)
   - 关键指标
   - 趋势分析
   - 用户群体分析
   - 支持性可视化

5. 结论 (Conclusions)
   - 主要洞察
   - 假设确认/驳回

6. 建议 (Recommendations)
   - 优先级排序
   - 预期影响
   - 实施步骤

7. 附录 (Appendix)
   - 详细数据表
   - 方法细节
```

### KPI 仪表板 (KPI Dashboard)

```
关键业务指标:

增长指标:
[ ] 月活跃用户 (MAU): [X]
   - 环比: [+Y]%
   - 同比: [+Z]%

[ ] 新增用户: [X]
   - 留存率 (Day 1): [Y]%
   - 留存率 (Day 7): [Z]%

收入指标:
[ ] 总收入: $[X]
   - ARPU (人均): $[Y]
   - MRR (月重复): $[Z]

[ ] 转换率:
   - 注册 → 首次购买: [X]%
   - 访问 → 注册: [Y]%

参与度:
[ ] 日活跃率: [X]%
[ ] 会话长度: [X] 分钟
[ ] 功能采用率: [X]%

客户健康:
[ ] NPS 评分: [X]
[ ] 流失率: [X]%
[ ] 支持工单: [X]
```

## A/B 测试设计 (A/B Testing Design)

### 测试计划 (Test Plan)

```
测试名称: [名称]
目标: [具体目标]

受众: [用户群体]
样本量: [计算 N]
持续时间: [X 周]
显著性水平 (α): 0.05
统计功效 (β): 0.20

对照组 (A): 现有版本
测试组 (B): 新版本

主要指标: [KPI]
次要指标: [支持指标]

假设:
- 当前转换率: 5%
- 预期提升: +10% (5.5%)
- 所需样本量: [N]
```

### 样本量计算 (Sample Size Calculation)

```
公式: n = 2σ² × (Z_α/2 + Z_β)² / (Δ)²

其中:
- σ² = 方差
- Z_α/2 = 1.96 (95% 置信度)
- Z_β = 0.84 (80% 功效)
- Δ = 效应大小

在线计算器:
https://www.evanmiller.org/ab-testing/sample-size.html

示例:
转换率: 5% → 5.5% (10% 相对提升)
所需样本数: 每组约 38,000 用户
总样本数: 76,000
持续时间: ~2 周 (假设日活 5,000)
```

### 测试执行 (Test Execution)

```
实施阶段:
[ ] 实现两个版本
[ ] 设置随机分配
[ ] 集成追踪事件
[ ] 设置基准指标

监控阶段:
[ ] 每日检查数据
[ ] 检查样本平衡
[ ] 监控数据质量
[ ] 记录异常

禁止行为:
[ ] 根据早期结果停止测试
[ ] 调整显著性阈值
[ ] 选择性报告指标
[ ] 测试多个变量
```

### 分析和报告 (Analysis & Reporting)

```
结果判断:
1. 如果 p < 0.05: 显著差异
   - 选择性能更好的版本
   - 记录学习

2. 如果 p ≥ 0.05: 无显著差异
   - 不能声称差异
   - 考虑效应大小
   - 可能需要更多样本

报告模板:
- 测试名称和日期
- 结果汇总（表格）
- p 值和置信区间
- 建议行动
- 学习要点

示例结果:

指标          版本 A    版本 B    改进    p 值    显著性
─────────────────────────────────────────────────
转换率        5.0%      5.5%      +10%   0.032   ✓
跳出率        25%       24%       -4%    0.157   ✗
平均订单值    $50       $51       +2%    0.234   ✗
```

## 分析报告检查清单 (Report Checklist)

### 内容 (Content)

- [ ] 问题清晰定义
- [ ] 方法论透明
- [ ] 数据代表性强
- [ ] 发现有证据支持
- [ ] 建议可操作

### 可视化 (Visualization)

- [ ] 图表准确
- [ ] 标签清晰
- [ ] 配色适当
- [ ] 适合媒介
- [ ] 无数据扭曲

### 沟通 (Communication)

- [ ] 目标受众明确
- [ ] 语言适当
- [ ] 故事线连贯
- [ ] 关键点突出
- [ ] 建议明确

### 准确性 (Accuracy)

- [ ] 数据验证完整
- [ ] 统计方法正确
- [ ] 计算无误
- [ ] 假设明确
- [ ] 局限性说明
