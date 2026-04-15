# API 设计模版 (API Design Template)

**tags:** api-design, rest, api-documentation, versioning
**roles:** API Designer, Backend Developer, Technical Architect
**category:** Technical Design

## 目标 (Objective)

设计易于使用、一致、可维护和可扩展的 RESTful API。

## RESTful 设计原则 (RESTful Design Principles)

### 资源导向设计 (Resource-Oriented Design)

```
关键概念: 一切都是资源，使用名词而不是动词

正确做法:
GET    /api/v1/users                    # 获取用户列表
POST   /api/v1/users                    # 创建用户
GET    /api/v1/users/{id}               # 获取单个用户
PUT    /api/v1/users/{id}               # 更新用户
DELETE /api/v1/users/{id}               # 删除用户

错误做法:
GET    /api/v1/getUsers                 # 动词
POST   /api/v1/createUser
GET    /api/v1/getUserById/{id}
```

### 无状态设计 (Stateless Design)

- [ ] 每个请求都包含完整信息
- [ ] 服务器不维持客户端状态
- [ ] 使用 token 进行身份验证
- [ ] 支持水平扩展

### 使用 HTTP 方法 (HTTP Methods)

| 方法 | 操作 | 幂等 | 安全 | 请求体 | 响应体 |
|------|------|------|------|--------|--------|
| GET | 获取资源 | 是 | 是 | 否 | 是 |
| POST | 创建资源 | 否 | 否 | 是 | 是 |
| PUT | 替换资源 | 是 | 否 | 是 | 是/否 |
| PATCH | 部分更新 | 否 | 否 | 是 | 是 |
| DELETE | 删除资源 | 是 | 否 | 否 | 否 |
| OPTIONS | 方法选项 | 是 | 是 | 否 | 否 |
| HEAD | 获取元数据 | 是 | 是 | 否 | 否 |

### HTTP 状态码 (HTTP Status Codes)

```
2xx 成功:
[ ] 200 OK - 请求成功
[ ] 201 Created - 创建成功，返回资源
[ ] 202 Accepted - 异步操作已接受
[ ] 204 No Content - 成功但无返回内容

3xx 重定向:
[ ] 301 Moved Permanently - 永久重定向
[ ] 302 Found - 临时重定向
[ ] 304 Not Modified - 资源未修改

4xx 客户端错误:
[ ] 400 Bad Request - 请求格式错误
[ ] 401 Unauthorized - 未认证
[ ] 403 Forbidden - 无权限
[ ] 404 Not Found - 资源不存在
[ ] 409 Conflict - 冲突（如重复）
[ ] 422 Unprocessable Entity - 验证失败
[ ] 429 Too Many Requests - 限流

5xx 服务器错误:
[ ] 500 Internal Server Error
[ ] 502 Bad Gateway
[ ] 503 Service Unavailable
[ ] 504 Gateway Timeout
```

## 端点命名规范 (Endpoint Naming Convention)

### 集合资源 (Collection Resources)

```
基础:
GET    /api/v1/users               # 列表，支持分页和过滤

查询参数:
?page=1&limit=20
?sort=created_at:desc
?filter[status]=active
?search=john

响应示例:
{
  "data": [ {...}, {...} ],
  "pagination": {
    "page": 1,
    "limit": 20,
    "total": 100,
    "pages": 5
  }
}
```

### 单个资源 (Singular Resources)

```
获取:
GET /api/v1/users/{id}

更新:
PUT /api/v1/users/{id}              # 完整替换
PATCH /api/v1/users/{id}            # 部分更新

删除:
DELETE /api/v1/users/{id}

示例:
GET /api/v1/users/123
PATCH /api/v1/users/123
  {
    "email": "new@example.com"
  }
```

### 嵌套资源 (Nested Resources)

```
获取用户的订单:
GET /api/v1/users/{id}/orders

创建用户的订单:
POST /api/v1/users/{id}/orders
  {
    "amount": 100,
    "items": [...]
  }

获取特定订单:
GET /api/v1/users/{id}/orders/{order_id}

最大嵌套深度: 2-3 级
```

### 操作端点 (Action Endpoints)

```
当没有对应资源时使用：

POST /api/v1/users/{id}/verify       # 发送验证邮件
POST /api/v1/users/{id}/reset-password
POST /api/v1/orders/{id}/cancel      # 取消订单
POST /api/v1/batch/process           # 批量处理

命名规范:
- 使用冒号或连字符分隔
- 使用动词形式
- 不超过一个操作
```

## 版本控制策略 (Versioning Strategy)

### 选项 1: URL 路径版本 (URL Path)

```
推荐: 明确，易于路由

/api/v1/users
/api/v2/users
/api/v3/users

优点: 清晰、便于调试、缓存友好
缺点: URL 污染、代码重复
```

### 选项 2: 查询参数版本 (Query Parameter)

```
/api/users?version=1
/api/users?version=2

优点: 清洁 URL
缺点: 易忽视、缓存问题
```

### 选项 3: 请求头版本 (Header)

```
Accept: application/vnd.myapi.v1+json
Accept: application/vnd.myapi.v2+json

优点: 资源 URL 统一
缺点: 不可见、难以调试
```

### 版本控制策略 (Versioning Policy)

- [ ] 新主版本支持: [X] 年或 [N] 年后废弃
- [ ] 版本过渡期: [X] 个月通知期
- [ ] 文档：维护所有活跃版本文档
- [ ] 测试：每个版本独立测试
- [ ] 部署：支持多版本共存

## 错误处理 (Error Handling)

### 错误响应格式 (Error Response Format)

```json
{
  "error": {
    "code": "INVALID_REQUEST",
    "message": "The request is invalid",
    "status": 400,
    "details": {
      "field": "email",
      "issue": "Invalid email format"
    },
    "timestamp": "2024-01-01T12:00:00Z",
    "request_id": "req_123456"
  }
}
```

### 错误代码 (Error Codes)

```
认证类:
[ ] AUTH_REQUIRED - 未提供认证
[ ] AUTH_INVALID - 认证信息无效
[ ] AUTH_EXPIRED - 令牌过期
[ ] PERMISSION_DENIED - 权限不足

验证类:
[ ] INVALID_REQUEST - 请求格式错误
[ ] MISSING_FIELD - 缺少必填字段
[ ] INVALID_FIELD - 字段值无效
[ ] CONSTRAINT_VIOLATION - 违反约束

资源类:
[ ] RESOURCE_NOT_FOUND - 资源不存在
[ ] RESOURCE_EXISTS - 资源已存在
[ ] CONFLICT - 冲突

系统类:
[ ] INTERNAL_ERROR - 内部错误
[ ] SERVICE_UNAVAILABLE - 服务不可用
[ ] RATE_LIMITED - 超过限流
```

### 验证错误详情 (Validation Error Details)

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Validation failed",
    "status": 422,
    "errors": [
      {
        "field": "email",
        "message": "Invalid email format",
        "code": "INVALID_FORMAT"
      },
      {
        "field": "age",
        "message": "Must be >= 18",
        "code": "INVALID_RANGE"
      }
    ]
  }
}
```

## 速率限制 (Rate Limiting)

### 实施方法 (Implementation)

```
限流方案: Token Bucket 算法

配置:
- [ ] 默认限制: [X] req/秒
- [ ] 突发容量: [Y] 个请求
- [ ] 重置周期: 1 小时

用户等级:
[ ] 免费: 100 req/小时
[ ] 专业: 10,000 req/小时
[ ] 企业: 无限制
```

### 限流响应头 (Rate Limit Headers)

```
HTTP/1.1 200 OK
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1372700873
X-RateLimit-Retry-After: 3600

超限响应:
HTTP/1.1 429 Too Many Requests
Retry-After: 3600
```

## 分页 (Pagination)

### 偏移分页 (Offset Pagination)

```
查询:
GET /api/v1/users?page=2&limit=20

响应:
{
  "data": [...],
  "pagination": {
    "page": 2,
    "limit": 20,
    "total": 500,
    "pages": 25,
    "has_more": true
  }
}

特点: 简单、易用
问题: 并发插入时不准确
```

### 游标分页 (Cursor Pagination)

```
查询:
GET /api/v1/users?cursor=abc123&limit=20

响应:
{
  "data": [...],
  "pagination": {
    "next_cursor": "xyz789",
    "has_more": true
  }
}

特点: 高效、准确
使用场景: 大数据集、流式数据
```

## 数据格式 (Data Format)

### 请求体 (Request Body)

```
POST /api/v1/users
Content-Type: application/json

{
  "name": "John Doe",
  "email": "john@example.com",
  "age": 30,
  "metadata": {
    "source": "web",
    "referrer": "google"
  }
}
```

### 响应体 (Response Body)

```
单资源:
{
  "data": {
    "id": "user_123",
    "name": "John Doe",
    "email": "john@example.com",
    "created_at": "2024-01-01T00:00:00Z"
  }
}

集合:
{
  "data": [
    {...},
    {...}
  ],
  "pagination": {...}
}
```

### 数据类型 (Data Types)

- [ ] 字符串: "value"
- [ ] 数字: 42, 3.14
- [ ] 布尔值: true/false
- [ ] 空值: null
- [ ] 数组: [1, 2, 3]
- [ ] 对象: {"key": "value"}
- [ ] 日期: "2024-01-01T00:00:00Z" (ISO 8601)

## 认证和授权 (Authentication & Authorization)

### 认证方法 (Authentication Methods)

```
选项 1: Bearer Token (JWT)
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

选项 2: API Key
X-API-Key: sk_live_abc123def456

选项 3: OAuth 2.0
Authorization: Bearer [access_token]

选项 4: Basic Auth
Authorization: Basic base64(username:password)

推荐: JWT Bearer Token
```

### 授权检查 (Authorization)

- [ ] 用户只能访问自己的资源
- [ ] 管理员可以访问所有资源
- [ ] 检查所有修改操作的权限
- [ ] 实现基于角色的访问控制 (RBAC)

## 文档要求 (Documentation Requirements)

### API 规范文件 (API Specification)

- [ ] 使用 OpenAPI 3.0 格式
- [ ] 所有端点文档化
- [ ] 所有参数描述
- [ ] 所有响应示例
- [ ] 错误场景文档化
- [ ] 认证方法说明
- [ ] 速率限制文档化

### 示例规范 (Example OpenAPI)

```yaml
openapi: 3.0.0
info:
  title: User API
  version: 1.0.0

paths:
  /api/v1/users:
    get:
      summary: List users
      parameters:
        - name: page
          in: query
          required: false
          schema:
            type: integer
      responses:
        200:
          description: Success
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/UserList'

components:
  schemas:
    User:
      type: object
      properties:
        id:
          type: string
        name:
          type: string
```

## 向后兼容性 (Backward Compatibility)

- [ ] 添加可选字段是安全的
- [ ] 删除字段需要版本变更
- [ ] 更改字段类型需要新版本
- [ ] 新的枚举值应向后兼容
- [ ] 弃用字段时提前 6 个月通知
- [ ] 维护旧版本支持期

## API 审查清单 (API Review Checklist)

- [ ] 所有端点命名一致
- [ ] HTTP 方法使用正确
- [ ] 状态码一致
- [ ] 错误格式统一
- [ ] 版本控制策略清晰
- [ ] 认证和授权完整
- [ ] 输入验证充分
- [ ] 性能优化（缓存、分页）
- [ ] 速率限制实施
- [ ] 文档完整准确
- [ ] 安全审核通过
- [ ] 向后兼容性检查
