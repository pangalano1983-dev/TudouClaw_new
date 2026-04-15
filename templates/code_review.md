# 代码审查模版 (Code Review Template)

**tags:** code-review, quality-assurance, testing, best-practices
**roles:** Code Reviewer, QA Engineer, Senior Developer
**category:** Quality Assurance

## 目标 (Objective)

对代码进行系统性审查，确保安全性、性能、质量和可维护性符合标准。

## 安全检查 (Security Checks)

### 身份验证与授权 (Authentication & Authorization)

- [ ] 所有受限端点都需要身份验证
- [ ] 使用强密码策略
- [ ] 实现正确的会话管理
- [ ] 验证授权逻辑（用户只能访问自己的数据）
- [ ] RBAC（基于角色的访问控制）正确实现
- [ ] 没有硬编码的凭证或 API 密钥
- [ ] 敏感操作需要额外验证
- [ ] 密码存储使用行业标准（bcrypt、Argon2）

### 输入验证 (Input Validation)

- [ ] 所有用户输入都被验证
- [ ] 实现类型检查
- [ ] 长度和格式验证
- [ ] SQL 注入防护（参数化查询）
- [ ] XSS 防护（输出编码）
- [ ] 命令注入防护
- [ ] 路径遍历防护
- [ ] 文件上传验证（类型、大小、扫描）

### 数据保护 (Data Protection)

- [ ] 敏感数据加密（传输中和存储中）
- [ ] 使用 HTTPS/TLS
- [ ] 数据库连接加密
- [ ] API 密钥安全存储
- [ ] 个人信息去标识化
- [ ] 日志不包含敏感信息
- [ ] 安全的数据删除机制
- [ ] GDPR/隐私合规性检查

### OWASP Top 10 核查 (OWASP Top 10 Checklist)

- [ ] A01:2021 – Broken Access Control（访问控制）
- [ ] A02:2021 – Cryptographic Failures（密码学失败）
- [ ] A03:2021 – Injection（注入漏洞）
- [ ] A04:2021 – Insecure Design（不安全设计）
- [ ] A05:2021 – Security Misconfiguration（安全配置错误）
- [ ] A06:2021 – Vulnerable Components（易受攻击的组件）
- [ ] A07:2021 – Authentication Failures（身份验证失败）
- [ ] A08:2021 – Data Integrity Failures（数据完整性失败）
- [ ] A09:2021 – Logging & Monitoring（日志和监控）
- [ ] A10:2021 – SSRF（服务器端请求伪造）

## 性能分析 (Performance Analysis)

### 算法效率 (Algorithm Efficiency)

- [ ] 时间复杂度分析
  ```
  最差情况: O(?)
  平均情况: O(?)
  最好情况: O(?)
  ```
- [ ] 空间复杂度分析
- [ ] 是否使用了合适的数据结构
- [ ] 避免不必要的嵌套循环（N²算法）
- [ ] 缓存机制是否实现
- [ ] 递归深度是否超限

### 资源使用 (Resource Usage)

- [ ] 内存泄漏检查
- [ ] 连接池管理正确
- [ ] 文件句柄正确关闭
- [ ] 没有无限循环
- [ ] CPU 密集操作是否异步化
- [ ] 批量操作是否分批处理
- [ ] 缓存命中率是否合理

### 数据库性能 (Database Performance)

- [ ] N+1 查询问题
- [ ] 查询是否使用索引
- [ ] JOIN 操作是否优化
- [ ] 事务作用域是否合理
- [ ] 批量插入/更新是否优化
- [ ] 查询执行计划是否检查

### 前端性能 (Frontend Performance)

- [ ] 包大小是否优化（gzip, minification）
- [ ] 图片是否压缩和懒加载
- [ ] CSS/JS 是否分离和优化
- [ ] 关键路径渲染是否优化
- [ ] 是否避免阻塞性操作
- [ ] 缓存策略是否合理

## 代码质量指标 (Code Quality Metrics)

### 可读性 (Readability)

- [ ] 变量名有意义且符合命名规范
- [ ] 函数名清晰表达意图
- [ ] 代码长度合理（函数 < 50 行）
- [ ] 缩进和格式一致
- [ ] 魔法数字被转换为命名常量
- [ ] 注释清晰简洁
- [ ] 避免过度注释

### 代码复杂度 (Code Complexity)

- [ ] 圈复杂度 (Cyclomatic Complexity) < 10
- [ ] 认知复杂度合理
- [ ] 函数参数个数 < 4
- [ ] 嵌套深度 < 3 层
- [ ] 代码中没有明显的复制粘贴

### 可维护性 (Maintainability)

- [ ] DRY 原则（不重复代码）
- [ ] SOLID 原则遵循
- [ ] 清晰的模块化设计
- [ ] 依赖注入使用
- [ ] 易于测试的代码结构
- [ ] 文档完整度

## SOLID 原则检查 (SOLID Principles)

### 单一职责原则 (Single Responsibility)

- [ ] 每个类只有一个改变原因
- [ ] 方法职责单一
- [ ] 没有"超级类"
- [ ] 关注点分离清晰

### 开闭原则 (Open/Closed Principle)

- [ ] 对扩展开放
- [ ] 对修改关闭
- [ ] 使用抽象和继承
- [ ] 避免修改现有代码来添加新功能

### 里氏替换原则 (Liskov Substitution)

- [ ] 子类可以替换父类
- [ ] 不违反预期的行为契约
- [ ] 异常处理一致
- [ ] 返回类型兼容

### 接口隔离原则 (Interface Segregation)

- [ ] 接口不过于庞大
- [ ] 客户端不依赖不需要的方法
- [ ] 接口职责清晰
- [ ] 避免"胖接口"

### 依赖倒置原则 (Dependency Inversion)

- [ ] 高层模块不依赖低层模块
- [ ] 都依赖于抽象
- [ ] 实现依赖注入
- [ ] 配置不硬编码

## 错误处理 (Error Handling)

### 异常处理 (Exception Handling)

- [ ] 没有空的 catch 块
- [ ] 异常信息清晰有用
- [ ] 不捕获过宽的异常（如 Exception）
- [ ] 不吞没异常信息
- [ ] 异常链保留了原始信息
- [ ] 自定义异常类使用恰当

### 错误恢复 (Error Recovery)

- [ ] 重试逻辑有指数退避
- [ ] 降级方案存在
- [ ] 超时设置合理
- [ ] 断路器模式使用（如果需要）
- [ ] 没有孤立资源

### 日志和诊断 (Logging & Diagnostics)

- [ ] 关键路径有适当的日志
- [ ] 日志级别使用正确
- [ ] 包含足够的上下文信息
- [ ] 敏感信息不记录
- [ ] 日志不过度（性能影响）
- [ ] 错误栈跟踪完整

## 测试覆盖 (Test Coverage)

### 单元测试 (Unit Tests)

- [ ] 所有公共方法都有测试
- [ ] 覆盖正常路径
- [ ] 覆盖边界条件
- [ ] 覆盖错误情况
- [ ] 测试独立且可重复
- [ ] 使用有意义的断言
- [ ] 测试隔离（没有依赖）

### 集成测试 (Integration Tests)

- [ ] 组件间交互测试
- [ ] 数据库集成测试
- [ ] 外部服务 mock/stub
- [ ] 事务回滚测试

### 代码覆盖目标 (Coverage Targets)

```
类型                | 目标覆盖率
-------------------|----------
语句覆盖 (Line)     | >= 80%
分支覆盖 (Branch)   | >= 75%
函数覆盖 (Function) | >= 90%
```

## 审查评分矩阵 (Review Score Matrix)

| 检查项目 | 权重 | 得分 | 权重得分 | 状态 |
|---------|------|------|--------|------|
| 安全性 | 40% | /10 | TBD | PASS/FAIL |
| 性能 | 20% | /10 | TBD | PASS/FAIL |
| 代码质量 | 25% | /10 | TBD | PASS/FAIL |
| 测试 | 15% | /10 | TBD | PASS/FAIL |
| **总体** | **100%** | **/10** | **TBD** | **PASS/FAIL** |

## 审查意见 (Review Comments)

### 必须修复 (Must Fix)

- [ ] 问题 1: [描述] (优先级: P0)
- [ ] 问题 2: [描述] (优先级: P0)
- [ ] 问题 3: [描述] (优先级: P0)

### 应该修复 (Should Fix)

- [ ] 问题 1: [描述] (优先级: P1)
- [ ] 问题 2: [描述] (优先级: P1)

### 可以改进 (Nice to Have)

- [ ] 建议 1: [描述]
- [ ] 建议 2: [描述]

## 审查决定 (Review Decision)

- [ ] **批准** - 代码符合所有标准
- [ ] **条件批准** - 需要修复标记的问题后批准
- [ ] **拒绝** - 需要重大修改或重新审查
- [ ] **重新审查** - 修复后需要再次审查

**审查人**: [姓名]
**审查日期**: [日期]
**预期完成**: [日期]
