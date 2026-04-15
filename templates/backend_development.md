# 后端开发模版 (Backend Development Template)

**tags:** backend, database, api-implementation, caching
**roles:** Backend Developer, Database Engineer, System Designer
**category:** Development

## 目标 (Objective)

指导后端开发最佳实践，确保可扩展、安全和高效的服务。

## 数据库设计 (Database Design)

### 数据库选择标准 (Database Selection Criteria)

```
选择评估矩阵:

                    关系型     NoSQL      搜索    时间序列
                    (PostgreSQL) (MongoDB) (ES)   (InfluxDB)
数据结构            结构化      灵活       文本    时间点
事务支持            强          弱         否      否
查询灵活性          高          中         特定    低
扩展性              水平困难    水平易     水平    水平
一致性保证          强          弱         最终    强
学习曲线            中          低         高      中

选择标准:
[ ] 关系型: 结构化、强一致性、复杂查询（用户、订单）
[ ] NoSQL: 灵活、水平扩展、高吞吐（日志、事件）
[ ] 搜索: 全文搜索、分析（产品、文章）
[ ] 时间序列: 指标、监控（性能、传感器）
```

### 数据库架构 (Database Architecture)

```
主从复制 (Master-Slave):
        ┌─────────────┐
        │   Master    │ ← 写入
        │ (PostgreSQL)│
        └──────┬──────┘
               │ 复制
        ┌──────┴────────┬──────────┐
        │               │          │
    ┌───▼──┐        ┌──▼──┐    ┌──▼──┐
    │Slave1│        │Slave2│   │Slave3│ ← 读取
    └──────┘        └──────┘   └──────┘

配置:
- [ ] 主服务器写入日志
- [ ] 从服务器异步复制
- [ ] 故障转移自动化
- [ ] 读取负载平衡
```

### 规范化设计 (Normalization)

```
1NF (第一范式):
[ ] 没有重复列
[ ] 每个列只包含原子值

2NF (第二范式):
[ ] 满足 1NF
[ ] 非键列完全依赖于主键

3NF (第三范式):
[ ] 满足 2NF
[ ] 非键列不依赖于其他非键列

反规范化 (Denormalization):
[ ] 用于性能优化
[ ] 冗余数据换取查询速度
[ ] 维护数据一致性
```

### 数据库索引 (Indexing Strategy)

```
索引类型:

单列索引:
CREATE INDEX idx_users_email ON users(email);

复合索引:
CREATE INDEX idx_orders_user_date ON orders(user_id, created_at);

唯一索引:
CREATE UNIQUE INDEX idx_users_email ON users(email);

全文索引:
CREATE INDEX idx_products_search ON products USING GIN(to_tsvector(name));

索引选择标准:
[ ] WHERE 子句中的列
[ ] 高基数列（很多不同值）
[ ] JOIN 条件中的外键
[ ] 排序和分组列

避免:
[ ] 低基数列（性别、状态）
[ ] 频繁更新的列
[ ] 大型文本列（除非全文搜索）
[ ] 太多索引（写入性能影响）
```

## API 实现 (API Implementation)

### REST 控制器实现 (REST Controller Implementation)

```python
# FastAPI 示例

from fastapi import FastAPI, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime

app = FastAPI()

@app.get("/api/v1/users")
async def list_users(
    db: Session,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    sort: str = Query("created_at:desc")
):
    """
    获取用户列表

    - **page**: 页码 (默认 1)
    - **limit**: 每页记录数 (1-100，默认 20)
    - **sort**: 排序字段:方向
    """
    # 验证
    offset = (page - 1) * limit

    # 查询
    users = db.query(User)\
        .offset(offset)\
        .limit(limit)\
        .all()

    total = db.query(User).count()

    # 响应
    return {
        "data": users,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "pages": (total + limit - 1) // limit
        }
    }

@app.post("/api/v1/users")
async def create_user(req: CreateUserRequest, db: Session):
    """创建用户"""
    # 验证
    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(status_code=409, detail="User already exists")

    # 创建
    user = User(
        email=req.email,
        name=req.name,
        created_at=datetime.utcnow()
    )
    db.add(user)
    db.commit()

    return {"data": user}

@app.get("/api/v1/users/{user_id}")
async def get_user(user_id: str, db: Session):
    """获取单个用户"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"data": user}

@app.patch("/api/v1/users/{user_id}")
async def update_user(user_id: str, req: UpdateUserRequest, db: Session):
    """更新用户"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if req.name:
        user.name = req.name
    if req.email:
        user.email = req.email

    db.commit()
    return {"data": user}

@app.delete("/api/v1/users/{user_id}")
async def delete_user(user_id: str, db: Session):
    """删除用户"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    db.delete(user)
    db.commit()

    return {"status": "success"}
```

## 身份验证和授权 (Authentication & Authorization)

### JWT 实现 (JWT Implementation)

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthCredentials
import jwt
from datetime import datetime, timedelta

security = HTTPBearer()

def create_access_token(data: dict, expires_in: int = 3600):
    """创建 JWT 令牌"""
    payload = data.copy()
    expire = datetime.utcnow() + timedelta(seconds=expires_in)
    payload.update({"exp": expire})

    token = jwt.encode(
        payload,
        "SECRET_KEY",
        algorithm="HS256"
    )
    return token

def verify_token(credentials: HTTPAuthCredentials = Depends(security)):
    """验证 JWT 令牌"""
    try:
        payload = jwt.decode(
            credentials.credentials,
            "SECRET_KEY",
            algorithms=["HS256"]
        )
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# 登录端点
@app.post("/api/v1/auth/login")
async def login(email: str, password: str, db: Session):
    """用户登录"""
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({"sub": str(user.id)})
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 3600
    }

# 受保护的端点
@app.get("/api/v1/profile")
async def get_profile(user_id: str = Depends(verify_token), db: Session = Depends()):
    """获取当前用户信息"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"data": user}
```

### 基于角色的访问控制 (RBAC)

```python
from enum import Enum

class Role(str, Enum):
    ADMIN = "admin"
    MODERATOR = "moderator"
    USER = "user"

def check_role(*allowed_roles: Role):
    """检查用户角色"""
    async def role_checker(user_id: str = Depends(verify_token), db: Session = Depends()):
        user = db.query(User).filter(User.id == user_id).first()
        if not user or user.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return role_checker

# 只允许管理员访问
@app.delete("/api/v1/users/{user_id}")
async def delete_user(
    user_id: str,
    current_user: User = Depends(check_role(Role.ADMIN)),
    db: Session = Depends()
):
    """删除用户（仅管理员）"""
    # ...实现
```

## 缓存策略 (Caching Strategy)

### 缓存层 (Cache Layers)

```
应用级缓存:
┌─────────────────────────────┐
│      应用程序               │
├─────────────────────────────┤
│  本地缓存 (dict/lru_cache)  │ ← L1 (内存，单机)
└─────────────────────────────┘

分布式缓存:
┌─────────────────────────────┐
│      应用程序               │
├─────────────────────────────┤
│  Redis 集群                 │ ← L2 (分布式，共享)
└─────────────────────────────┘

HTTP 缓存:
┌─────────────────────────────┐
│      CDN / 代理              │ ← L3 (边缘)
├─────────────────────────────┤
│      应用程序               │
├─────────────────────────────┤
│      数据库                 │
└─────────────────────────────┘
```

### Redis 缓存实现 (Redis Caching Implementation)

```python
import redis
import json
from functools import wraps

cache = redis.Redis(host='localhost', port=6379, db=0)

def get_user_cache(user_id: str):
    """从缓存获取用户"""
    key = f"user:{user_id}"
    data = cache.get(key)
    if data:
        return json.loads(data)
    return None

def set_user_cache(user_id: str, user: User, ttl: int = 3600):
    """缓存用户"""
    key = f"user:{user_id}"
    cache.setex(key, ttl, json.dumps(user.dict()))

def cache_wrapper(ttl: int = 3600):
    """缓存装饰器"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, user_id=None, **kwargs):
            cache_key = f"{func.__name__}:{user_id}"

            # 尝试从缓存获取
            cached = cache.get(cache_key)
            if cached:
                return json.loads(cached)

            # 执行函数
            result = await func(*args, **kwargs)

            # 存储到缓存
            cache.setex(cache_key, ttl, json.dumps(result))

            return result
        return wrapper
    return decorator

# 使用
@cache_wrapper(ttl=1800)
async def get_user_profile(user_id: str, db: Session):
    """获取用户信息（带缓存）"""
    user = db.query(User).filter(User.id == user_id).first()
    return user.dict()

# 缓存失效
def invalidate_user_cache(user_id: str):
    """失效用户缓存"""
    cache.delete(f"user:{user_id}")
    cache.delete(f"get_user_profile:{user_id}")
```

### 缓存策略 (Caching Policies)

```
缓存策略选择:

Cache-Aside (旁路缓存):
1. 检查缓存
2. 如果缺失，获取数据
3. 写入缓存
4. 返回数据

Write-Through (写穿):
1. 写入缓存
2. 写入数据库
3. 返回确认

Write-Behind (写回):
1. 写入缓存
2. 异步写入数据库
3. 立即返回

TTL 策略:
[ ] 静态内容: 24 小时
[ ] 用户数据: 1 小时
[ ] 列表数据: 5 分钟
[ ] 实时数据: 不缓存或 30 秒
```

## 错误处理 (Error Handling)

### 异常策略 (Exception Strategy)

```python
class ApplicationError(Exception):
    """应用程序基础异常"""
    def __init__(self, code: str, message: str, status_code: int = 500):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)

class ValidationError(ApplicationError):
    def __init__(self, message: str):
        super().__init__("VALIDATION_ERROR", message, 422)

class NotFoundError(ApplicationError):
    def __init__(self, resource: str):
        super().__init__(
            "NOT_FOUND",
            f"{resource} not found",
            404
        )

class AuthenticationError(ApplicationError):
    def __init__(self):
        super().__init__(
            "AUTH_REQUIRED",
            "Authentication required",
            401
        )

# 异常处理器
@app.exception_handler(ApplicationError)
async def application_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message
            }
        }
    )

# 使用
@app.get("/api/v1/users/{user_id}")
async def get_user(user_id: str, db: Session):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise NotFoundError("User")
    return {"data": user}
```

### 日志策略 (Logging Strategy)

```python
import logging

logger = logging.getLogger(__name__)

logger.info("User created", extra={"user_id": user.id})
logger.warning("High memory usage", extra={"memory": 85})
logger.error("Database connection failed", exc_info=True)

# 日志级别:
[ ] DEBUG: 开发调试
[ ] INFO: 关键业务事件
[ ] WARNING: 可恢复的问题
[ ] ERROR: 错误，可能需要处理
[ ] CRITICAL: 系统危险
```

## 后端检查清单 (Backend Checklist)

### 设计 (Design)

- [ ] 数据库架构文档化
- [ ] API 规范完整
- [ ] 认证和授权方案清晰
- [ ] 缓存策略定义
- [ ] 错误处理方案

### 性能 (Performance)

- [ ] N+1 查询检查
- [ ] 索引已优化
- [ ] 缓存已实施
- [ ] 数据库连接池配置
- [ ] 响应时间 < 200ms (p95)

### 安全 (Security)

- [ ] 输入验证完整
- [ ] SQL 注入防护
- [ ] 认证和授权检查
- [ ] 敏感数据加密
- [ ] API 速率限制

### 可靠性 (Reliability)

- [ ] 错误处理完整
- [ ] 重试逻辑实施
- [ ] 断路器模式（外部调用）
- [ ] 日志记录充分
- [ ] 监控告警配置

### 测试 (Testing)

- [ ] 单元测试 >= 80%
- [ ] 集成测试覆盖
- [ ] E2E 测试关键流程
- [ ] 性能测试完成
- [ ] 负载测试通过

### 文档 (Documentation)

- [ ] API 文档完整
- [ ] 数据库架构文档
- [ ] 部署说明
- [ ] 故障排查指南
- [ ] 代码注释清晰
