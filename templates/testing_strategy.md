# 测试策略模版 (Testing Strategy Template)

**tags:** testing, qa, test-automation, quality-assurance
**roles:** QA Engineer, Test Automation Engineer, Quality Lead
**category:** Quality Assurance

## 目标 (Objective)

建立全面的测试策略和执行计划，确保软件质量、可靠性和用户体验。

## 测试金字塔 (Test Pyramid)

```
        /\
       /  \         E2E 测试 (10%)
      /────\        用户流程、集成测试
     /  E2E \
    /────────\
   /          \      集成测试 (20%)
  /  Integration\    组件交互、API
 /──────────────\
/                \   单元测试 (70%)
 ────────────────   类和函数
    Unit Tests

总覆盖率目标: >= 80%
```

## 单元测试策略 (Unit Test Strategy)

### 覆盖率目标 (Coverage Targets)

```
覆盖率类型:
[ ] 语句覆盖率 (Line Coverage): >= 85%
[ ] 分支覆盖率 (Branch Coverage): >= 80%
[ ] 函数覆盖率 (Function Coverage): >= 90%
[ ] 路径覆盖率 (Path Coverage): >= 75%

计算方式:
覆盖率 = 覆盖的代码行 / 总代码行 × 100%
```

### 测试框架 (Testing Framework)

```
Java:
[ ] JUnit 5 - 标准测试框架
[ ] Mockito - Mock 对象库
[ ] AssertJ - 流畅的断言库

Python:
[ ] pytest - 测试框架
[ ] unittest.mock - Mock 库

JavaScript/Node.js:
[ ] Jest - 测试框架和运行器
[ ] Mocha - 测试框架
[ ] Sinon - Mock/Stub 库
```

### 测试用例设计 (Test Case Design)

#### 正常路径测试 (Happy Path)

```
测试: 成功创建用户
Given: 有效的用户数据
When: 调用 createUser()
Then: 返回新用户的 ID

代码示例:
@Test
public void testCreateUserSuccess() {
  // Arrange
  UserRequest request = new UserRequest("john@example.com", "password");

  // Act
  User user = userService.createUser(request);

  // Assert
  assertThat(user).isNotNull();
  assertThat(user.getEmail()).isEqualTo("john@example.com");
}
```

#### 边界值测试 (Boundary Values)

```
测试变量: 年龄字段，有效范围 [18, 100]

边界值:
[ ] 最小值-1: 17 (应拒绝)
[ ] 最小值: 18 (应接受)
[ ] 最小值+1: 19 (应接受)
[ ] 最大值-1: 99 (应接受)
[ ] 最大值: 100 (应接受)
[ ] 最大值+1: 101 (应拒绝)

// 测试示例
@ParameterizedTest
@ValueSource(ints = {17, 18, 19, 99, 100, 101})
public void testAgeValidation(int age) {
  // 验证逻辑
}
```

#### 异常情况测试 (Exception Cases)

```
测试: 创建重复用户
When: 邮箱已存在
Then: 抛出 DuplicateUserException

@Test
public void testCreateUserDuplicate() {
  // Arrange
  UserRequest request = new UserRequest("exists@example.com");

  // Act & Assert
  assertThrows(DuplicateUserException.class, () -> {
    userService.createUser(request);
  });
}
```

#### 数据驱动测试 (Data-Driven Testing)

```
@ParameterizedTest
@CsvSource({
  "valid@email.com, true",
  "invalid.email, false",
  "user@domain.co.uk, true",
  "user@domain, false"
})
public void testEmailValidation(String email, boolean expected) {
  boolean result = validator.isValidEmail(email);
  assertThat(result).isEqualTo(expected);
}
```

## 集成测试策略 (Integration Testing)

### 测试范围 (Test Scope)

```
测试组件交互:

[ ] 控制器 → 服务
  - 请求映射
  - 参数传递
  - 响应格式

[ ] 服务 → 数据库
  - 数据持久化
  - 事务处理
  - 级联删除

[ ] 服务 → 外部 API
  - 请求/响应正确
  - 错误处理
  - 超时处理

[ ] 数据库 → 缓存
  - 缓存命中
  - 缓存失效
```

### 集成测试示例 (Integration Test Example)

```java
@SpringBootTest
public class UserServiceIntegrationTest {

  @Autowired
  private UserService userService;

  @Autowired
  private UserRepository userRepository;

  @BeforeEach
  public void cleanup() {
    userRepository.deleteAll();
  }

  @Test
  public void testCreateAndRetrieveUser() {
    // Arrange
    UserRequest request = new UserRequest("john@example.com");

    // Act
    User created = userService.createUser(request);
    User retrieved = userService.getUser(created.getId());

    // Assert
    assertThat(retrieved.getEmail()).isEqualTo("john@example.com");
  }

  @Test
  public void testDatabaseTransactionRollback() {
    // 测试事务回滚
  }
}
```

## E2E 测试策略 (End-to-End Testing)

### 测试范围 (Test Scenarios)

```
用户注册流程:
[ ] 导航到注册页面
[ ] 填充用户信息
[ ] 提交表单
[ ] 验证确认邮件
[ ] 点击邮件中的链接
[ ] 验证账户激活
[ ] 登录
[ ] 验证登陆后屏幕

关键购物流程:
[ ] 浏览产品列表
[ ] 搜索产品
[ ] 查看产品详情
[ ] 添加到购物车
[ ] 查看购物车
[ ] 结账
[ ] 支付处理
[ ] 订单确认
```

### 工具和框架 (Tools & Frameworks)

```
Web UI:
[ ] Selenium WebDriver
[ ] Cypress (推荐现代应用)
[ ] Playwright

API E2E:
[ ] Postman
[ ] REST Assured

移动应用:
[ ] Appium
[ ] XCUITest (iOS)
[ ] Espresso (Android)
```

### E2E 测试示例 (E2E Test Example)

```javascript
describe('User Registration Flow', () => {
  it('should register a new user successfully', async () => {
    // 导航到注册页面
    await page.goto('http://localhost:3000/register');

    // 填充表单
    await page.fill('input[name="email"]', 'test@example.com');
    await page.fill('input[name="password"]', 'SecurePass123!');
    await page.fill('input[name="confirm"]', 'SecurePass123!');

    // 提交表单
    await page.click('button[type="submit"]');

    // 验证成功消息
    const message = await page.textContent('.success-message');
    expect(message).toContain('Registration successful');

    // 验证重定向
    expect(page.url()).toBe('http://localhost:3000/login');
  });
});
```

## 测试用例设计 (Test Case Design)

### 边界值分析 (Boundary Value Analysis)

```
函数: validateAge(age)
有效范围: [18, 100]

测试用例:
┌─────────────┬────────┬─────────┬──────────┐
│ 用例        │ 输入值 │ 预期结果 │ 类别    │
├─────────────┼────────┼─────────┼──────────┤
│ BV1         │ 17     │ 无效    │ 边界外  │
│ BV2         │ 18     │ 有效    │ 边界内  │
│ BV3         │ 59     │ 有效    │ 中值    │
│ BV4         │ 100    │ 有效    │ 边界内  │
│ BV5         │ 101    │ 无效    │ 边界外  │
│ BV6         │ -1     │ 无效    │ 异常    │
│ BV7         │ 999    │ 无效    │ 异常    │
└─────────────┴────────┴─────────┴──────────┘
```

### 等价类分割 (Equivalence Partitioning)

```
功能: processOrder(orderId)

有效等价类:
EC1: 存在且未处理的订单
EC2: 存在且已处理的订单

无效等价类:
EC3: 不存在的订单 ID
EC4: 无效格式的订单 ID
EC5: 空值

选择的测试用例:
[ ] EC1: processOrder("ORD-001") - 成功
[ ] EC2: processOrder("ORD-002") - 失败（已处理）
[ ] EC3: processOrder("NON-EXIST") - 异常
[ ] EC4: processOrder("ABC") - 异常
[ ] EC5: processOrder(null) - 异常
```

## 性能测试 (Performance Testing)

### 负载测试 (Load Testing)

```
目标: 验证系统在预期负载下的性能

测试配置:
- [ ] 并发用户: 100 → 1000
- [ ] 测试持续时间: 30 分钟
- [ ] 坡度增加: 每 5 分钟增加 100 用户
- [ ] 请求类型: 实际用户工作流

性能指标:
[ ] 平均响应时间: < 500 ms
[ ] p95 响应时间: < 1000 ms
[ ] p99 响应时间: < 2000 ms
[ ] 吞吐量: > 200 req/sec
[ ] 错误率: < 0.1%

工具:
[ ] JMeter - Java 负载测试
[ ] LoadRunner - 企业级工具
[ ] Gatling - 高性能
[ ] Locust - Python 脚本
```

### 压力测试 (Stress Testing)

```
目标: 找到系统的极限

测试步骤:
1. [ ] 并发用户: 500
2. [ ] 增加到 1000
3. [ ] 增加到 2000
4. [ ] 继续增加直到系统崩溃

观察指标:
[ ] 何时响应时间开始恶化
[ ] 何时错误率增加
[ ] 何时出现异常
[ ] 恢复能力

目标: 确定最大容量和降级点
```

### JMeter 测试计划 (JMeter Test Plan)

```
测试计划结构:
├── 线程组
│   ├── 100 个用户
│   ├── 5 分钟斜坡时间
│   └── 30 分钟持续时间
├── HTTP 请求
│   ├── GET /api/users
│   ├── POST /api/orders
│   └── GET /api/orders/{id}
├── 响应断言
│   └── 状态码 == 200
└── 监听器
    └── 结果树视图
```

## 性能基准线 (Performance Baseline)

| 操作 | 基线响应时间 | 预警阈值 | 告警阈值 |
|------|----------|---------|----------|
| 列表查询 | 100 ms | 200 ms | 500 ms |
| 详情查询 | 50 ms | 150 ms | 300 ms |
| 创建 | 200 ms | 400 ms | 800 ms |
| 更新 | 150 ms | 300 ms | 600 ms |
| 删除 | 100 ms | 200 ms | 400 ms |

## 测试执行计划 (Test Execution Plan)

### 每日测试 (Daily Testing)

- [ ] 运行单元测试 (所有)
- [ ] 运行集成测试 (所有)
- [ ] 运行冒烟测试 (关键功能)
- [ ] 检查代码覆盖率

### 每周测试 (Weekly Testing)

- [ ] 回归测试 (所有功能)
- [ ] 性能基准测试
- [ ] 安全扫描
- [ ] 浏览器兼容性测试

### 发布前测试 (Pre-Release Testing)

- [ ] 完整 E2E 测试套件
- [ ] 性能测试
- [ ] 用户验收测试 (UAT)
- [ ] 安全审计
- [ ] 负载测试

## 测试报告 (Test Report)

```
执行日期: [日期]
环境: [开发/测试/预发布]

测试摘要:
├── 总测试数: 1000
├── 通过: 950 (95%)
├── 失败: 40 (4%)
├── 跳过: 10 (1%)
└── 代码覆盖率: 85%

失败原因分析:
├── Bug: 25 个
├── 环境问题: 10 个
├── 测试数据: 5 个
└── 其他: 0 个

优先级分布:
├── P0 (严重): 5
├── P1 (高): 15
├── P2 (中): 15
└── P3 (低): 5

建议:
- [ ] 修复所有 P0 问题
- [ ] 改进 X 功能的测试覆盖
- [ ] 优化性能
```

## 持续集成中的测试 (Testing in CI/CD)

```
Pipeline 检查门:

Pre-Commit Hook:
[ ] 格式检查 (2 分钟)
[ ] 快速 Lint (1 分钟)

Commit 时:
[ ] 单元测试 (5 分钟)
[ ] 代码覆盖率 >= 80% (2 分钟)
[ ] 构建 (3 分钟)

PR 验证:
[ ] 集成测试 (10 分钟)
[ ] 代码审查 (手动)
[ ] 安全扫描 (5 分钟)

合并前:
[ ] E2E 烟雾测试 (15 分钟)
[ ] 性能对比 (10 分钟)

部署后:
[ ] 部署健康检查 (5 分钟)
[ ] 日志监控 (实时)
[ ] 错误率监控 (30 分钟)
```
