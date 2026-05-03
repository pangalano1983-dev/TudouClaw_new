# 数据目录与环境变量配置

> 目的：解释 TudouClaw 运行时所有数据写在哪里、用哪些环境变量切换路径，以及多 node / NAS 部署时需要注意的边界条件。
>
> Audience：部署/运维、做 multi-node 拓扑的工程。

---

## 1. 主变量

### `TUDOU_CLAW_DATA_DIR` — 主数据根目录

**优先级**：CLI flag `--data-dir` > `TUDOU_CLAW_DATA_DIR` env var > 默认 `~/.tudou_claw/`

定义在 [`app/__init__.py:24,40`](../app/__init__.py)：

```python
USER_HOME = _os.path.expanduser("~")
DEFAULT_DATA_DIR = _os.path.join(USER_HOME, ".tudou_claw")
data_root = os.environ.get("TUDOU_CLAW_DATA_DIR") or DEFAULT_DATA_DIR
```

启动方式：

```bash
# 方式 A：环境变量
export TUDOU_CLAW_DATA_DIR=/mnt/nas/tudou_claw
uvicorn app.api.main:app --host 0.0.0.0 --port 9090

# 方式 B：CLI flag
python -m app --data-dir /mnt/nas/tudou_claw
```

### 目录布局（root 下）

```
${TUDOU_CLAW_DATA_DIR}/
├── agents.json                    # agent 持久化（每次保存覆盖写）
├── projects.json                  # 项目持久化
├── workflows.json                 # canvas workflow 定义
├── meetings.json                  # 会议记录
├── role_presets.json              # 角色预设
├── llm_tiers.json                 # LLM tier 路由配置
├── rag_providers.json             # RAG provider 配置
├── tool_denylist.json             # 全局禁用工具清单
├── tool_approvals.json            # 工具审批历史
├── scheduled_jobs.json            # 定时任务
├── branding.json                  # UI 品牌配置
├── tudou_claw.db                  # V1 SQLite（兼容用）
├── tudou.db                       # V2 SQLite（task_store 等）
├── inbox.db                       # 收件箱 SQLite
│
├── workspaces/
│   ├── agents/{agent_id}/         # 每个 agent 的私有目录
│   │   ├── workspace/             # 工作文件、Scheduled.md、Tasks.md
│   │   ├── session/               # 会话快照
│   │   ├── memory/                # 记忆快照
│   │   └── logs/                  # 日志
│   └── shared/{project_id}/       # 项目共享工作区（成员都看得到）
│
├── skills/                        # 全局技能定义文件（Markdown + YAML frontmatter）
├── experience/                    # 经验库（chroma collection 文件）
├── chroma/                        # 主向量库目录（如未单独配置）
├── roles/                         # 用户自定义 role preset
├── checkpoints/                   # canvas/agent 任务断点
├── hf_cache/                      # HuggingFace 模型缓存（默认在主目录下；见下面 TUDOU_HF_CACHE）
├── sessions/                      # 手动导出的 agent 会话
└── Orchestration_workflows/       # workflow run artifacts
```

---

## 2. 周边变量

| 变量 | 用途 | 默认 | 多 node 建议 |
|---|---|---|---|
| **`TUDOU_CLAW_DATA_DIR`** | 主数据根目录 | `~/.tudou_claw/` | **NAS 共享** |
| `TUDOU_HF_CACHE` | HuggingFace 模型缓存（bge-m3 / bge-reranker 各 ~2.5 GB） | `${DATA_DIR}/hf_cache` | **本地 SSD**（IO 大、不适合 NAS） |
| `TUDOU_CLAW_HOME` | **遗留兼容**别名 | 无 | 与主变量值保持一致 |
| `TUDOU_DATA_DIR` | `security.py` 白名单中出现，未实际接到读取路径 | 无 | **不要依赖**，不会生效 |
| `TUDOU_TQDM` | `=1` 启用 tqdm 进度条（默认抑制） | `0` | 调试时再开 |
| `TUDOU_AGENT_ISOLATION` | `=1` 启用 agent 进程隔离 | `0` | 视部署而定 |
| `TUDOU_UID_ISOLATION` | `=1` 启用每 agent 独立 UID（POSIX） | `0` | 视部署而定 |
| `TUDOU_SECRET` | 集群间共享密钥 | 无 | **必填**（multi-node） |
| `TUDOU_UPSTREAM_HUB` | Node 模式下指向上游 Hub | 无 | 仅 node 模式 |
| `TUDOU_UPSTREAM_SECRET` | 上游 Hub 的认证密钥 | 无 | 仅 node 模式 |
| `TUDOU_NODE_ID` | 当前 node 标识（默认用 hostname） | `$HOSTNAME` | 建议显式设 |
| `TUDOU_NODE_URL` | Master 回调本 worker 的公开 URL | socket-探测 IP | 走反向代理时**必填** |
| `TUDOU_ADMIN_SECRET` | 首次启动的超管 token | 随机生成 | 受控环境可固定 |

### 老变量名 `TUDOU_CLAW_HOME` 的坑

下面两个文件**只读老变量**，不会跟随 `TUDOU_CLAW_DATA_DIR`：

- [`app/auth.py:1766`](../app/auth.py)
- [`app/experience_library.py:274`](../app/experience_library.py)

切换 NAS 时**两个变量都设**：

```bash
export TUDOU_CLAW_DATA_DIR=/mnt/nas/tudou_claw
export TUDOU_CLAW_HOME=/mnt/nas/tudou_claw
```

> TODO（清理项）：把这两个文件改成读 `TUDOU_CLAW_DATA_DIR`，统一命名。

---

## 3. 已知问题：硬编码 `~/.tudou_claw` 的模块（**多 node 前必修**）

下面这些模块**写死本地家目录**，不读 env var。即使设了 `TUDOU_CLAW_DATA_DIR=/mnt/nas/tudou_claw`，它们仍会往本地 `~/.tudou_claw` 写：

| 文件 | 行 | 内容 |
|---|---|---|
| `app/llm_tier_routing.py` | 245 | `os.path.join(os.path.expanduser("~"), ".tudou_claw", "llm_tiers.json")` |
| `app/role_preset_registry.py` | 177 | `Path(os.path.expanduser("~")) / ".tudou_claw" / "roles"` |
| `app/rag_provider.py` | 38 | `_DATA_DIR = Path.home() / ".tudou_claw"` （模块级常量） |
| `app/agent_server.py` | 62, 588 | `~/.tudou_claw/workspaces/{agent_id}/` |
| `app/inbox.py` | 386 | 有读 env var，但 fallback 写死 `~/.tudou_claw` |
| `app/cleanup.py` | 213 | `~/.tudou_claw/tudou.db` |

### 正确读 env var 的（这些是对的）

- `app/__init__.py`（HF cache，路径计算用）
- `app/checkpoint.py:403`（读 `TUDOU_CLAW_DATA_DIR`）
- `app/auth.py:1766`（读 `TUDOU_CLAW_HOME`）
- `app/experience_library.py:274`（读 `TUDOU_CLAW_HOME`）

---

## 4. 多 node / NAS 部署 checklist

### Phase 1 — 立刻可做（无需改代码）

```bash
# 主数据目录（agents.json / projects.json / skills / experience…）
export TUDOU_CLAW_DATA_DIR=/mnt/nas/tudou_claw

# 老名字一起设上（auth + experience_library 还在读它）
export TUDOU_CLAW_HOME=/mnt/nas/tudou_claw

# HF 模型缓存留本地 SSD（NAS 上 2.5 GB 模型 mmap 会很慢）
export TUDOU_HF_CACHE=/local/ssd/hf_cache

# Multi-node 必填
export TUDOU_SECRET=<32+ 字节随机串>
export TUDOU_NODE_ID=node-001  # 每 node 显式区分
```

**这样设之后立刻生效的**：HF cache、checkpoint、auth、experience。
**仍会写本地的**：agents.json、role_presets、rag_providers、workspaces、llm_tiers — 见 §3 表格。

### Phase 2 — 修硬编码（独立 PR，~1–2 小时）

把 §3 表格里那些模块的硬编码替换成统一函数 `app.paths.data_dir()`，内部读一次 env var。

建议落地步骤（要走 superpowers 流程）：
1. `app/paths.py` 新增 `data_dir()` 单一入口
2. §3 表格 6 个文件全部改用它
3. 加一个 pytest：`monkeypatch TUDOU_CLAW_DATA_DIR` 后所有路径都跟着切

### Phase 3 — 真正 multi-node 时

| 路径 | 是否能放 NAS | 注意事项 |
|---|---|---|
| `agents.json` | ✅ 可以 | **必须加文件锁**（多 node 同时写 → race condition） |
| `projects.json` | ✅ 可以 | 同上，加锁 |
| `tudou_claw.db` / `tudou.db` (SQLite) | ⚠️ 风险 | NFS 上的 SQLite 锁不可靠，会丢数据。建议改 PostgreSQL |
| `chroma/` (向量库) | ❌ 不建议 | SQLite + 大量 mmap，NAS 性能差。每 node 本地 + 用 RAG provider 路由 |
| `workspaces/agents/{id}/` | ✅ 可以 | NFS `lock=NONE` 验证一下 fsync 顺序 |
| `experience/` (chroma) | ❌ 同 chroma | 单独用 chroma server 或 PG 替代 |
| `skills/` (Markdown) | ✅ 可以 | 只读为主，没有锁竞争 |
| `hf_cache/` | ❌ 不建议 | 见上 |
| `checkpoints/` | ✅ 可以 | append-only, 安全 |

---

## 5. 一行验证

```bash
# 启动前看一眼当前会用的根目录
python3 -c "import app; import os; print('data_dir:', os.environ.get('TUDOU_CLAW_DATA_DIR') or app.DEFAULT_DATA_DIR)"

# 验证多变量都对齐
env | grep -E "^TUDOU_"
```

---

## 6. Multi-Node 注册流程（Master ↔ Worker）

### 启动 Master

```bash
# Master：什么都不用变，照常启动 portal
export TUDOU_SECRET=cluster-shared-secret-xyz   # 与下游 worker 必须一致
uvicorn app.api.main:app --host 0.0.0.0 --port 9090
```

### 启动 Worker Node

```bash
# Worker：3 个 env var 决定行为
export TUDOU_UPSTREAM_HUB=http://master.example.com:9090
export TUDOU_UPSTREAM_SECRET=cluster-shared-secret-xyz   # 同 master TUDOU_SECRET
export TUDOU_NODE_ID=node-shanghai-01                    # 不设默认 hostname
export TUDOU_NODE_URL=http://shanghai.example.com:9090   # 走代理时必填，否则自动探测内网 IP
uvicorn app.api.main:app --host 0.0.0.0 --port 9090
```

### Worker 启动后自动发生的事

1. **Boot-time register** — `app/hub/_core.py:_register_with_upstream()` 在后台线程跑一次，
   POST `http://master/api/hub/register` 带 `X-Hub-Secret: cluster-shared-secret-xyz`，body 含 node_id / name / endpoint / agents。
   失败 → 不阻塞启动，Heartbeat 兜底。
2. **Heartbeat loop** — 每 `TUDOU_HEARTBEAT_INTERVAL`（默认 15s）POST `/api/hub/heartbeat`，
   bumps master 端 `last_seen`。
3. **Heartbeat 自动恢复** — Master 重启后丢失内存态？下一次 heartbeat 命中
   "node 不在 remote_nodes" 路径，触发自动 register（用 heartbeat body 里的 url/name 重建条目）。

### 权限边界（重要）

Worker Node **不能授予 superAdmin 权限**：

- `Hub.is_worker_node = bool(TUDOU_UPSTREAM_HUB)` 是判定信号
- `app/api/deps/auth.py:_cap_role_for_worker_node()` 在所有 JWT/session/token 路径上把 `superAdmin → admin`
- 设计理由：superAdmin 操作（管理其他 admin / 集群级策略）只在拥有 canonical store 的 master 上有意义。Worker 上的 superAdmin token 即使签发了也会被静默降级。

允许的角色：`admin` / `user`。

### 认证

| 路由 | 认证方式 | 用谁 |
|---|---|---|
| `/api/hub/register` | `X-Hub-Secret` header | worker 启动 |
| `/api/hub/heartbeat` | `X-Hub-Secret` header | worker 心跳 |
| `/api/hub/sync` | JWT user | UI 触发 sync |
| `/api/hub/orchestrate` | JWT user | UI 触发 cross-node 任务 |
| `/api/portal/*` | JWT user | UI / 用户脚本 |

`X-Hub-Secret` 与 `TUDOU_SECRET` 比对（master 侧），用 `hmac.compare_digest`。
**Dev 模式**：master 没设 `TUDOU_SECRET` → `/register`、`/heartbeat` 不验签直接放行（但记 warning）。
单机本地开发不需要任何 setup。

### 故障排查

| 现象 | 检查 |
|---|---|
| Worker 启动后 master 看不到 | `TUDOU_UPSTREAM_HUB` 是否设了？master 那台 9090 是否可达？看 worker 日志 `upstream register failed` 提示。 |
| Master 看到 node 但无法回调 | worker 的 `TUDOU_NODE_URL` 没设、socket 探测拿到 127.0.0.1 / 内网 IP。在反向代理后**必须**显式设 `TUDOU_NODE_URL`。 |
| Heartbeat 401 | master/worker 的密钥不一致。Master 看 `TUDOU_SECRET`，worker 看 `TUDOU_UPSTREAM_SECRET`，必须相同。 |
| Worker UI 显示 superAdmin 功能 | 这是 UI 层 bug — JWT 已被降级，但 UI 可能用了缓存 role。强刷或重新 login。 |

---

## 7. 历史 / 决策日志

- **2026-05-03** 文档创建。源头是发现 9090 backend 重启后 `to_dict` 漏字段导致的 Desktop Floater 持久化 bug，顺便审计数据目录配置。发现 §3 表格列出的硬编码问题。
- 旧变量名 `TUDOU_CLAW_HOME` 早期版本遗留，新代码统一用 `TUDOU_CLAW_DATA_DIR`，但还有两处没迁移完。
- 单一部署模型（"一个 TudouClaw 安装 = 一个公司"）是设计前提，所以原本不强求 multi-node。NAS 切换是新需求。
- **2026-05-03 (晚)** 加 multi-node MVP：worker 启动时 boot-time register + heartbeat 自动 upsert 兜底 + `X-Hub-Secret` 认证 + worker 上 superAdmin 角色降级 admin。`TUDOU_NODE_URL` 是新 env var，给 master 回调用。详见 §6。
