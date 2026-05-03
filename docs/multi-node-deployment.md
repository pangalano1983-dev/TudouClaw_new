# Multi-Node 部署指南（Master ↔ Worker）

> 完整操作手册：单 master + N worker 的部署、启动、验证、排错。
> 配套阅读：[`docs/data-dir-config.md`](data-dir-config.md) — 数据目录与 env var 全表。

---

## TL;DR

```bash
# Master（一台）
export TUDOU_SECRET=cluster-shared-secret-xyz
export TUDOU_CLAW_DATA_DIR=/var/lib/tudou_claw
uvicorn app.api.main:app --host 0.0.0.0 --port 9090

# Worker（N 台）
export TUDOU_UPSTREAM_HUB=http://master.example.com:9090
export TUDOU_UPSTREAM_SECRET=cluster-shared-secret-xyz   # ≡ master TUDOU_SECRET
export TUDOU_NODE_ID=node-shanghai-01
export TUDOU_NODE_URL=http://shanghai.example.com:9090   # 反向代理后必填
export TUDOU_CLAW_DATA_DIR=/var/lib/tudou_claw_worker
uvicorn app.api.main:app --host 0.0.0.0 --port 9090
```

启动顺序：先 master，再 worker。Worker 的 boot-time register 失败也没事，heartbeat 兜底。

---

## 1. 概念

| 概念 | 含义 |
|---|---|
| **Master**（也叫 Hub） | canonical 状态仓库。superAdmin 只在这里。所有 user/admin 数据、cluster-wide 策略、跨 node 编排都在 master。 |
| **Worker Node** | 下游执行节点。设了 `TUDOU_UPSTREAM_HUB` 就是 worker。superAdmin 角色被降级为 admin，**没有集群级管理权限**。 |
| **共享密钥** | `TUDOU_SECRET`（master 侧）≡ `TUDOU_UPSTREAM_SECRET`（worker 侧）。用于 worker→master 节点级调用的认证（`X-Hub-Secret` header）。**不是** JWT。 |
| **boot-time register** | Worker 启动时一次性 POST `/api/hub/register` 给 master，带 node_id / name / endpoint / agents。 |
| **heartbeat** | Worker 每 15s POST `/api/hub/heartbeat`。Master 用它 bump `last_seen`，并在「node 不在内存」时自动重建条目（兜底）。 |

---

## 2. Master 启动

### 2.1 最小命令

```bash
export TUDOU_SECRET=cluster-shared-secret-xyz
uvicorn app.api.main:app --host 0.0.0.0 --port 9090
```

⚠ `--host 0.0.0.0` 是必须的（worker 要能从外部连进来）。如果 master 只在内网，可以指定具体的内网 IP。

### 2.2 推荐 env vars

| Env | 推荐值 | 说明 |
|---|---|---|
| `TUDOU_SECRET` | 32+ 字节随机串 | **必填**。所有 worker 用同一个。 |
| `TUDOU_CLAW_DATA_DIR` | `/var/lib/tudou_claw` 或独立 NAS 子目录 | 数据根目录，避免 `~/.tudou_claw` |
| `TUDOU_HF_CACHE` | `/local/ssd/hf_cache` | HF 模型缓存放本地 SSD（IO 大） |
| `TUDOU_HEARTBEAT_INTERVAL` | `15`（默认） | 心跳间隔秒数 |
| `TUDOU_HEARTBEAT_TIMEOUT` | `60`（默认） | 多久没心跳判 stale |

### 2.3 生成 secret

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
# 输出：例如 fJ8mP9-xK2vL...（48 字符）
# 或：
openssl rand -hex 32
```

把这个值同时贴到 master 的 `TUDOU_SECRET` 和所有 worker 的 `TUDOU_UPSTREAM_SECRET`。

### 2.4 验证 master 起来了

```bash
curl http://localhost:9090/healthz                    # 应该 200
curl http://master.example.com:9090/api/hub/agents \
     -H "X-Hub-Secret: $TUDOU_SECRET"                  # 应该 200，返回 {"agents": []}
```

---

## 3. Worker Node 启动

### 3.1 完整命令

```bash
# 1) 必须 — 让自己变成 worker
export TUDOU_UPSTREAM_HUB=http://master.example.com:9090
export TUDOU_UPSTREAM_SECRET=cluster-shared-secret-xyz   # ≡ master TUDOU_SECRET

# 2) 强烈建议 — 标识自己
export TUDOU_NODE_ID=node-shanghai-01                    # 不设默认 hostname
export TUDOU_NODE_URL=http://shanghai.example.com:9090   # master 回调用

# 3) 数据目录 — 多 worker 必须各自独立
export TUDOU_CLAW_DATA_DIR=/var/lib/tudou_claw_node1

# 4) 启动
uvicorn app.api.main:app --host 0.0.0.0 --port 9090
```

### 3.2 启动后预期日志

```
INFO  Heartbeat loop started (interval=15.0s, timeout=60.0s)
INFO  Registered with upstream master at http://master.example.com:9090 as node node-shanghai-01 (http://shanghai.example.com:9090)
```

如果看到：

```
WARNING  upstream register failed (will retry via heartbeat): ...
```

不阻塞启动，heartbeat 每 15s 会再试。等 30s 看看是否在 master 出现。

### 3.3 关于 `TUDOU_NODE_URL`

Master 收到 register 后会用这个 URL 来回调 worker（例如分发 agent 配置、跨 node 消息）。**没设时**，代码会按这个顺序探测：

1. socket 探测：连一下 `8.8.8.8:80`，拿到的本机 IP（外网可达机器一般 OK）
2. fallback：`http://<hostname>:9090`（仅 DNS 网络内有效）

**反向代理 / NAT / Docker 容器**情况下必须显式设：

```bash
# 反向代理后
export TUDOU_NODE_URL=https://shanghai.example.com   # 注意 https + 公开域名

# Docker 容器（host 模式）
export TUDOU_NODE_URL=http://10.0.1.42:9090         # 宿主机 IP

# K8s Pod
export TUDOU_NODE_URL=http://${POD_NAME}.${SVC_NAME}.${NAMESPACE}.svc.cluster.local:9090
```

---

## 4. 验证 worker 已连上

### 4.1 在 master 那边

```bash
# 查所有已注册节点
curl -H "X-Hub-Secret: $TUDOU_SECRET" \
     http://master.example.com:9090/api/hub/agents | jq

# 或者打开 portal UI → 左侧 "Nodes" 面板，应该看到 worker 名字 + 在线状态
```

### 4.2 看 master 日志

worker 注册成功时，master 会打：

```
HUB register_node: id=node-shanghai-01 name=node-shanghai-01 url=http://shanghai.example.com:9090 agents=0 has_secret=False
HUB register_node OK: node-shanghai-01 now has 1 remote nodes
Hub register: node=node-shanghai-01 name=node-shanghai-01 url=http://shanghai.example.com:9090 agents=0 auth=hub_node
```

heartbeat 成功时（每 15s）：

```
DEBUG  ...   # 默默 bump last_seen，不打 INFO
```

如果 heartbeat 触发了自动恢复（master 重启后丢内存）：

```
INFO  Heartbeat from unknown node node-shanghai-01 — auto-registered (auth=hub_node)
```

---

## 5. 本地开发：一台机器跑两份

```bash
# Terminal 1 — master
export TUDOU_SECRET=test-secret
export TUDOU_CLAW_DATA_DIR=/tmp/master_data
uvicorn app.api.main:app --host 127.0.0.1 --port 9090

# Terminal 2 — worker（同一台 mac）
export TUDOU_UPSTREAM_HUB=http://127.0.0.1:9090
export TUDOU_UPSTREAM_SECRET=test-secret
export TUDOU_NODE_ID=local-worker
export TUDOU_NODE_URL=http://127.0.0.1:9095
export TUDOU_CLAW_DATA_DIR=/tmp/worker_data
uvicorn app.api.main:app --host 127.0.0.1 --port 9095
```

> 数据目录**必须分开** — 两个进程同时往一个 agents.json / SQLite 写会损坏数据。

验证：
```bash
curl -H "X-Hub-Secret: test-secret" http://127.0.0.1:9090/api/hub/agents | jq
```

---

## 6. Env Vars 速查

| Env var | Master | Worker | 必填 |
|---|---|---|---|
| `TUDOU_SECRET` | ✅ 设值 | ❌ 不设 | master 必填 |
| `TUDOU_UPSTREAM_HUB` | ❌ 不设 | ✅ master 地址 | worker 必填 |
| `TUDOU_UPSTREAM_SECRET` | ❌ 不设 | ✅ ≡ master TUDOU_SECRET | worker 必填 |
| `TUDOU_NODE_ID` | 默认 hostname | 默认 hostname | 推荐显式 |
| `TUDOU_NODE_URL` | 不需要 | master 回调地址 | 反向代理 / NAT 必填 |
| `TUDOU_CLAW_DATA_DIR` | 推荐设 | 推荐设（避免冲突） | 推荐 |
| `TUDOU_HEARTBEAT_INTERVAL` | 默认 15 | 默认 15 | 调试时可调 |
| `TUDOU_HEARTBEAT_TIMEOUT` | 默认 60 | 默认 60 | 调试时可调 |

---

## 7. 权限边界

### Worker 上 superAdmin 自动降级 admin

- 触发条件：`Hub.is_worker_node == True`（即 `TUDOU_UPSTREAM_HUB` 已设）
- 实现位置：`app/api/deps/auth.py:_cap_role_for_worker_node()`
- 影响：JWT / session / token 三条 auth 路径全覆盖

### 设计理由

| 操作 | Master | Worker |
|---|---|---|
| 管理其他 admin | ✅ superAdmin 可做 | ❌ 角色已降，403 |
| 集群级策略修改 | ✅ | ❌ |
| 修改自己 agent | ✅ admin 可做 | ✅ admin 可做 |
| 跑 agent / 接收任务 | ✅ | ✅ |
| user 普通操作 | ✅ | ✅ |

worker 上即便有人偷到 master 签发的 superAdmin JWT，token 落到 worker 的 `get_current_user` 时也会被静默降级，无法做 superAdmin 操作。这是**纵深防御**层。

---

## 8. 故障排查

### 8.1 Worker 启动后 master 看不到

```bash
# Step 1: secret 一致么？必须完全相同（含大小写、空格）
echo "$TUDOU_SECRET" | md5sum         # master 这边
echo "$TUDOU_UPSTREAM_SECRET" | md5sum # worker 这边
# 两个 md5 必须一样

# Step 2: master 可达么？
curl -v http://master.example.com:9090/healthz   # worker 这台机器执行

# Step 3: worker 日志
grep "upstream register" /var/log/tudou/worker.log
# 看到具体错误 message
```

### 8.2 Master 看到 node 但跨 node 调用失败

```bash
# 多半是 TUDOU_NODE_URL 没设或值不对
# 在 master 那台执行：
curl -v $WORKER_URL_MASTER_THINKS/healthz
# 不通 → worker 的 TUDOU_NODE_URL 是错的（探测到内网/127.0.0.1）
# → 显式设 worker 的 TUDOU_NODE_URL 为 master 能访问到的地址
```

### 8.3 Heartbeat 401

```bash
# worker 日志：upstream heartbeat failed: ... 401
# → secret 不一致
# → 或者 master 的 _shared_secret 没初始化（master 没设 TUDOU_SECRET）
```

### 8.4 Worker UI 显示 superAdmin 功能

- 后端 JWT 已被降级（已在所有 auth 路径生效）
- 但前端 portal_bundle.js 可能缓存了 role 字段
- **解决**：刷新页面 → 重新登录 → 检查 `localStorage.role` 是否为 `admin`

### 8.5 多个 worker 共用一个数据目录 → 数据损坏

**症状**：agents.json 偶尔 corrupted、SQLite "database is locked"

**原因**：两个进程同时写
**解决**：每个 worker 设独立的 `TUDOU_CLAW_DATA_DIR`

---

## 9. 关闭 / 移除 worker

### 临时下线（计划维护）

```bash
# 在 worker 那边
Ctrl+C 关掉 uvicorn
# Master 端会在 TUDOU_HEARTBEAT_TIMEOUT * 2 = 120s 后把它标 stale
```

### 永久移除

```bash
# 在 master 那边
curl -X DELETE \
     -H "Authorization: Bearer $YOUR_JWT" \
     http://master.example.com:9090/api/hub/node/node-shanghai-01
```

---

## 10. 升级流程（worker fleet）

```bash
# 1) Master 先升级
ssh master.example.com
cd ~/AIProjects/TudouClaw_new
git pull
systemctl restart tudou-master   # 或者你的启动方式

# 2) 验证 master 起来
curl http://master.example.com:9090/healthz

# 3) Workers 一台一台升级（rolling）
for w in node-shanghai-01 node-shanghai-02 node-beijing-01; do
    ssh $w "cd ~/TudouClaw_new && git pull && systemctl restart tudou-worker"
    sleep 60   # 等 worker 起来 + register
    curl -H "X-Hub-Secret: $TUDOU_SECRET" \
         http://master.example.com:9090/api/hub/agents | jq ".agents[] | select(.node_id==\"$w\")"
    # 确认在线再升下一台
done
```

---

## 11. 当前限制（需要时再做）

| 限制 | 现状 | TODO |
|---|---|---|
| HTTPS / TLS | 没强制，明文 secret | 加 reverse proxy（caddy / nginx）做 TLS termination |
| Secret 轮换 | 重启所有 node | 设计两 secret 并存 + 平滑过渡 |
| 多 master HA | 单 master | 远期 — 需要分布式 state（Redis / etcd） |
| 节点 health UI | portal 看 last_seen 时间 | 加可视化 traffic light |
| Worker 自我修复 | 仅 boot-time + heartbeat 兜底 | exponential backoff retry |

---

## 12. 历史

- **2026-05-03** — Multi-node MVP commit `a92bad0`：boot-time register、heartbeat 自动 upsert、X-Hub-Secret 认证、worker 上 superAdmin 降级。
