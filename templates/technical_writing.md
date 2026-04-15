# 技术文档模版 (Technical Writing Template)

**tags:** documentation, technical-writing, api-docs, readme
**roles:** Technical Writer, Developer, Documentation Manager
**category:** Documentation

## 目标 (Objective)

创建清晰、全面和易于维护的技术文档，支持开发者、用户和运维团队。

## 文档结构 (Documentation Structure)

### 信息架构 (Information Architecture)

```
根目录/docs/
├── README.md                 # 项目概述
├── GETTING_STARTED.md        # 快速开始
├── INSTALLATION.md           # 安装指南
├── USER_GUIDE.md             # 用户手册
├── API/
│   ├── README.md             # API 概述
│   ├── AUTHENTICATION.md      # 认证
│   ├── ENDPOINTS.md           # 端点详情
│   └── EXAMPLES.md            # 代码示例
├── ARCHITECTURE/
│   ├── OVERVIEW.md           # 架构概述
│   ├── DATABASE.md           # 数据库设计
│   └── DEPLOYMENT.md         # 部署说明
├── DEVELOPMENT/
│   ├── SETUP.md              # 开发环境设置
│   ├── CONTRIBUTING.md       # 贡献指南
│   └── TESTING.md            # 测试指南
├── CHANGELOG.md              # 变更日志
└── TROUBLESHOOTING.md        # 故障排查
```

## README 模版 (README Template)

### 结构 (Structure)

```markdown
# 项目名称

简短的一句话描述

## 目录 (Table of Contents)

- [关于](#关于)
- [功能](#功能)
- [快速开始](#快速开始)
- [安装](#安装)
- [使用](#使用)
- [API](#api)
- [贡献](#贡献)
- [许可证](#许可证)

## 关于 (About)

1-2 段说明项目是什么，解决什么问题。

## 功能 (Features)

- [ ] 核心功能 1
- [ ] 核心功能 2
- [ ] 核心功能 3

## 快速开始 (Quick Start)

### 前置条件 (Prerequisites)

- Node.js >= 16.0.0
- npm >= 8.0.0
- PostgreSQL >= 13

### 安装 (Installation)

\`\`\`bash
# 克隆仓库
git clone https://github.com/username/project.git
cd project

# 安装依赖
npm install

# 配置环境
cp .env.example .env
# 编辑 .env 文件

# 运行数据库迁移
npm run migrate

# 启动开发服务器
npm run dev
\`\`\`

## 使用 (Usage)

### 基本用法 (Basic Usage)

\`\`\`javascript
const { API } = require('project');

const api = new API({
  token: 'your-api-key'
});

// 获取数据
const data = await api.getData();
\`\`\`

### 更多示例 (More Examples)

详见 [EXAMPLES.md](./EXAMPLES.md)

## API 文档 (API Documentation)

详见 [API](./docs/API/README.md)

## 贡献 (Contributing)

我们欢迎贡献！详见 [CONTRIBUTING.md](./CONTRIBUTING.md)

## 许可证 (License)

MIT License - 详见 [LICENSE](./LICENSE) 文件
```

## API 文档模版 (API Documentation Template)

### API 概述 (API Overview)

```markdown
# API 文档

## 简介 (Introduction)

这是项目 API 的完整文档。

- **基础 URL**: `https://api.example.com/v1`
- **协议**: REST
- **格式**: JSON
- **认证**: Bearer Token (JWT)

## 认证 (Authentication)

所有请求必须包含认证令牌：

\`\`\`bash
Authorization: Bearer {access_token}
\`\`\`

## 基础概念 (Core Concepts)

### 速率限制

- 默认限制: 1000 请求/小时
- 可在响应头查看: `X-RateLimit-Remaining`

### 错误处理

所有错误返回统一格式：

\`\`\`json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "错误描述"
  }
}
\`\`\`

## 端点列表 (Endpoint Reference)

详见 [ENDPOINTS.md](./ENDPOINTS.md)
```

### 端点文档 (Endpoint Documentation)

```markdown
## GET /users

获取用户列表

### 请求

\`\`\`bash
GET /api/v1/users?page=1&limit=20
Authorization: Bearer token
\`\`\`

### 查询参数 (Query Parameters)

| 参数 | 类型 | 必需 | 描述 |
|------|------|------|------|
| page | integer | 否 | 页码，默认 1 |
| limit | integer | 否 | 每页记录数，默认 20 |
| sort | string | 否 | 排序字段：created_at:asc |

### 响应

**状态码**: 200 OK

\`\`\`json
{
  "data": [
    {
      "id": "user_123",
      "email": "user@example.com",
      "name": "John Doe",
      "created_at": "2024-01-01T00:00:00Z"
    }
  ],
  "pagination": {
    "page": 1,
    "limit": 20,
    "total": 100
  }
}
\`\`\`

### 错误响应

**状态码**: 401 Unauthorized

\`\`\`json
{
  "error": {
    "code": "UNAUTHORIZED",
    "message": "Invalid or missing token"
  }
}
\`\`\`

### 示例 (Examples)

#### cURL

\`\`\`bash
curl -X GET "https://api.example.com/v1/users?page=1" \\
  -H "Authorization: Bearer token"
\`\`\`

#### JavaScript

\`\`\`javascript
fetch('https://api.example.com/v1/users?page=1', {
  headers: {
    'Authorization': 'Bearer token'
  }
})
  .then(res => res.json())
  .then(data => console.log(data));
\`\`\`

#### Python

\`\`\`python
import requests

headers = {
  'Authorization': 'Bearer token'
}

response = requests.get(
  'https://api.example.com/v1/users',
  headers=headers,
  params={'page': 1}
)

print(response.json())
\`\`\`
```

## 变更日志模版 (CHANGELOG Template)

```markdown
# 变更日志 (Changelog)

所有值得注意的项目变化都在此文件记录。

## [2.0.0] - 2024-01-15

### 添加 (Added)

- [ ] 新的用户认证系统
- [ ] 支持多租户
- [ ] WebSocket 实时更新

### 更改 (Changed)

- [ ] 数据库模式更新（需要迁移）
- [ ] API 端点重组织
- [ ] 性能优化

### 弃用 (Deprecated)

- [ ] `/api/v1/users/old` 端点（已通知用户）
- [ ] 旧的认证方法（将在 3.0 移除）

### 移除 (Removed)

- [ ] 对 Node.js 12 的支持
- [ ] 旧的 Flash API

### 修复 (Fixed)

- [ ] 用户注册边界情况
- [ ] 数据库连接池泄漏
- [ ] 缓存失效逻辑

### 安全 (Security)

- [ ] 更新了 JWT 算法
- [ ] 强制使用 HTTPS

### 迁移指南 (Migration Guide)

详见 [MIGRATIONS.md](./MIGRATIONS.md)

## [1.5.0] - 2023-12-01

### 添加

- [ ] 导出为 CSV 功能
- [ ] 批量操作 API

### 修复

- [ ] 报告日期过滤器

---

## 版本管理 (Versioning)

本项目使用 [语义化版本](https://semver.org/)
- MAJOR: 不兼容的 API 变化
- MINOR: 向后兼容的新功能
- PATCH: 向后兼容的修复
```

## 架构决策记录 (Architecture Decision Record - ADR)

```markdown
# ADR-001: 数据库技术选择

## 状态

已批准

## 背景

我们需要为新项目选择关系型数据库

## 考虑的选项

1. **PostgreSQL**
   - 优点: 功能丰富、ACID 合规、开源
   - 缺点: 复杂性高

2. **MySQL**
   - 优点: 简单、性能好
   - 缺点: 功能较少

3. **MongoDB**
   - 优点: 灵活的模式
   - 缺点: 不 ACID、数据一致性问题

## 决策

选择 **PostgreSQL**

## 原因

- 数据一致性是关键需求
- JSON 支持满足灵活性需求
- 较好的行业支持和文档
- 团队熟悉

## 后果

- 需要学习 PostgreSQL 具体语法
- 某些简单操作可能更复杂
- 成本合理
- 性能满足预期

## 相关链接

- [PostgreSQL 文档](https://www.postgresql.org/docs/)
- [性能基准](./performance-benchmark.md)
```

## 安装指南模版 (Installation Guide)

```markdown
# 安装指南 (Installation Guide)

## 前置条件 (Prerequisites)

| 软件 | 版本 | 必需 |
|------|------|------|
| Node.js | >= 16.0.0 | 是 |
| npm | >= 8.0.0 | 是 |
| PostgreSQL | >= 13 | 是 |
| Redis | >= 6.0 | 否 |

## 安装步骤 (Installation Steps)

### 1. 克隆仓库

\`\`\`bash
git clone https://github.com/company/project.git
cd project
\`\`\`

### 2. 安装依赖

\`\`\`bash
npm install
\`\`\`

### 3. 配置环境

\`\`\`bash
cp .env.example .env
\`\`\`

编辑 `.env` 文件：

\`\`\`env
NODE_ENV=development
DATABASE_URL=postgresql://user:pass@localhost:5432/dbname
REDIS_URL=redis://localhost:6379
API_KEY=your-api-key
\`\`\`

### 4. 数据库迁移

\`\`\`bash
npm run migrate
\`\`\`

### 5. 启动服务

**开发环境**:

\`\`\`bash
npm run dev
\`\`\`

**生产环境**:

\`\`\`bash
npm run build
npm run start
\`\`\`

## 验证安装 (Verification)

访问 http://localhost:3000，应该看到应用程序首页。

## 故障排查 (Troubleshooting)

### 数据库连接失败

检查 PostgreSQL 是否正在运行：

\`\`\`bash
psql -U user -d dbname -c "SELECT 1"
\`\`\`

### 端口已被占用

更改 `.env` 中的 PORT：

\`\`\`env
PORT=3001
\`\`\`

## 卸载 (Uninstallation)

\`\`\`bash
npm uninstall
rm -rf node_modules
\`\`\`

## 获取帮助 (Getting Help)

- 查看 [FAQ](./FAQ.md)
- 提交 [GitHub Issue](https://github.com/company/project/issues)
- 联系 [support@example.com](mailto:support@example.com)
```

## 文档维护检查清单 (Documentation Maintenance)

### 文档完整性 (Completeness)

- [ ] 所有公共 API 都有文档
- [ ] 所有配置选项都有说明
- [ ] 所有命令都有示例
- [ ] 所有错误都有解释
- [ ] 所有功能都有教程

### 准确性 (Accuracy)

- [ ] 代码示例都能运行
- [ ] 截图是最新的
- [ ] 版本号是准确的
- [ ] 链接都是有效的
- [ ] 命令都是正确的

### 可维护性 (Maintainability)

- [ ] 文档使用一致的格式
- [ ] 文档组织清晰
- [ ] 没有重复内容
- [ ] 使用有意义的标题
- [ ] 有目录

### 更新流程 (Update Process)

- [ ] 每个 PR 都更新相关文档
- [ ] 发布前审查所有文档
- [ ] 定期检查文档新鲜度
- [ ] 归档过时的文档
- [ ] 维护版本历史

## 文档风格指南 (Style Guide)

### 语言风格

- 使用现在时和主动语态
- 使用清晰、直接的语言
- 避免行话和术语（除非必要）
- 一致的术语使用
- 简短的句子和段落

### 格式规范

- 使用 Markdown 格式
- 代码块使用语法高亮
- 表格用于比较
- 列表用于序列
- 粗体用于强调关键词

### 示例代码

- 代码应该能直接运行
- 包括完整的导入和初始化
- 使用现实的示例
- 包括预期输出
- 注释解释复杂部分

### 图表和可视化

- 使用图表解释架构
- 使用流程图显示工作流
- 使用表格比较选项
- 包括屏幕截图和标注
- 所有图表都应该有标题
