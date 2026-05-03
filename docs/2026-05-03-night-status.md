# 2026-05-03 晚 — 状态记录

> 给明天早上接手用。当前 session 在 multi-node 端到端测试时发现新 bug，刚 commit 一个修复，但完整链路还没跑通。

---

## 用户明确的优先级（今晚最后说的）

1. **Master/Node 协同**（核心）
   - master 要能管理 node
   - 编排 / meeting / project 等多 agent 协同**跨 node 也要通**（不只是本地）
2. **RAG 全流程验证**（效果 + 质量）

> "今天主要这 2 个核心功能问题"

---

## Multi-Node 当前状态

### ✅ 已验证可工作

| 项目 | 验证证据 |
|---|---|
| Worker 启动 boot-time register（带 X-Hub-Secret） | 真双机做过：master 看到 worker 已注册 |
| Heartbeat 兜底 / 自动 upsert | 单元测试 `tests/test_node_registration.py` 8/8 |
| `proxy_create_agent` 后端逻辑 | 单元测试 `tests/test_multi_node_create.py` 10/10 |
| SSE 透传 prefix 路由 | 单元测试 `tests/test_multi_node_chat.py` 7/7 |
| **本机双进程实测：master 创建 agent on worker** | curl 返回了正确 agent dict（id/node_id/working_dir 都在 worker 那边）✅ |

### 🔴 本机实测发现的真 bug + 修复

| Bug | 修复 |
|---|---|
| `init_hub()` 没读 `TUDOU_NODE_ID` env，所有 worker 都用默认 "local"，互相覆盖 | **commit `bd6fe1b`** 已 ship — 加了 env 读取 + worker-mode hostname fallback |
| `TUDOU_ADMIN_SECRET` 被同时用作 inter-node shared secret（`api/main.py:171`） | 没改，记下 — 这是历史 design choice，现在能 work，但语义不清晰 |

### 🔴 还没诊断完的问题（明天首先看）

**症状**：在本机双进程跑 chat 测试时
- ✅ POST `/agent/create` body=`{"node_id":"worker-test-9095",...}` → 200，agent 在 worker 创建（working_dir=/tmp/tudou_worker_test/...）
- ⏳ 等 18s 后 heartbeat sync — master 那边显示 worker `agent_count=7`（不对！应该是 1）
- ❌ POST `/agent/{remote_id}/chat` → 404 "Agent not found"

**直接查询发现矛盾**：
```bash
# Worker 自己说没 agent
curl http://127.0.0.1:9095/api/portal/agents → "0 agents"
curl http://127.0.0.1:9095/api/hub/agents → "0 agents"

# Worker 磁盘上没 agents.json
ls /tmp/tudou_worker_test/agents.json → No such file

# 但 create 返回时确实给了 agent dict
```

**两个假说要验证**：
1. Worker 上 `hub.create_agent()` 没调 `_save_agents()` → 重启就丢，但是 in-memory 仍在
2. Worker 上 `hub.list_agents()` 过滤了 — 比如 `_can_see` 把 `owner_id="hub_proxy"` 的 agent 当成"非 owner 看不见"过滤掉了
3. 测试时多个 worker 进程并存，create 和后续 list 命中不同 PID

**最可能是 #2**（hub_proxy 这个 synthetic owner 在 list_agents 的 filter 路径被过滤）。

需要 audit：
- `app/hub/agent_manager.py:create_agent` — 创建后是否 `_save_agents()`
- `app/api/routers/agents.py:list_agents` — `_can_see()` 过滤逻辑
- `app/hub/_core.py:get_agent(agent_id)` — 单查 agent 是否也走 owner 过滤

### 🟡 设计上要补的（用户提的"协同场景"）

当前 multi-node MVP 只覆盖 1v1：master → worker create + chat。

**用户要求的"多 agent 协同跨 node"**还没做：

| 场景 | 现状 | 跨 node 需要做 |
|---|---|---|
| Orchestrate（hub.orchestrate / `/api/hub/orchestrate`） | 只在 hub 本地遍历 hub.agents | 也要 dispatch 给 remote_nodes 上的 agent |
| Meeting（多 agent 圆桌对话） | 假设所有 agent 都在 self.agents | 跨 node 的 agent 加入会话需要 proxy_chat_sync 支持 |
| Project（任务分配） | task.assigned_to 假设 agent 在本地 | assign 给 remote agent 时调用 proxy 链路 |
| Canvas Workflow | step 执行时 `agent_chat_fn` 走本地 | step.target_agent 是 remote 时 → proxy_chat_sync |

`proxy_chat_sync` 已经在 `app/hub/_core.py` 改用 X-Hub-Secret + 正确 URL，理论可以接入。但**现在卡在基础 chat 不通**，等修完才能往上层打通。

---

## RAG 全流程（用户第 2 优先级）

今天**没动 RAG**，状态保持 commit `1929bc3` 之后的样子（paths 重构 + chromadb 在 requirements）。

### 用户原话："验证 RAG 的全流程，效果和质量"

要做：
1. **数据导入流程**：`/api/portal/rag/upload` → chunking → embedding (bge-m3) → 存 chroma
2. **检索流程**：query → embedding → top-k → reranking (bge-reranker-v2-m3) → 拼 context
3. **效果验证**：跑 1-2 个真实 query，看 retrieved chunks 是否相关
4. **质量验证**：reranker 排序合理？top-k 阈值合理？hybrid search（embedding + bm25）真的提升精度？
5. **失败模式**：query 太短、查询的中文里混英文、文档没相关内容时 fallback 行为

预存在的失败测试（`test_rag_hybrid_search.py` 4 个失败 + `test_rag_ingest_dedup_metadata.py` 7 个）可能是 RAG 现状的 leading indicator — 明天拿真实数据跑之前先 audit 这些 mock 失败的根因（之前 audit 过是 `_FakeMM._get_chroma_collection` mock signature 老了）。

---

## 明早接手 checklist

### 步骤 1（30 min）— 修今晚 multi-node 卡住的点

```bash
# 1. 启动 master（如果还在跑就跳过）
TUDOU_ADMIN_SECRET=admin123 \
TUDOU_NODE_ID=master-1 \
uvicorn app.api.main:app --host 0.0.0.0 --port 9090 &

# 2. 启动 test worker
mkdir -p /tmp/tudou_worker_test
TUDOU_CLAW_DATA_DIR=/tmp/tudou_worker_test \
TUDOU_UPSTREAM_HUB=http://127.0.0.1:9090 \
TUDOU_UPSTREAM_SECRET=admin123 \
TUDOU_NODE_ID=worker-test-9095 \
TUDOU_NODE_URL=http://127.0.0.1:9095 \
TUDOU_DISABLE_DREAM=1 \
TUDOU_ADMIN_SECRET=admin123 \
uvicorn app.api.main:app --host 127.0.0.1 --port 9095 &

# 3. 拿 JWT
JWT=$(curl -s -X POST http://127.0.0.1:9090/api/auth/login \
       -H 'Content-Type: application/json' -d '{"token":"admin123"}' \
       | python3 -c "import json,sys;print(json.load(sys.stdin)['access_token'])")

# 4. Create agent on worker
curl -s -X POST http://127.0.0.1:9090/api/portal/agent/create \
     -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
     -d '{"node_id":"worker-test-9095","name":"test-1","role":"general"}'
# Expect: agent dict with node_id="worker-test-9095" working_dir on worker ✓

# 5. 验证 worker 内部真的存了
curl -s -H "X-Hub-Secret: admin123" http://127.0.0.1:9095/api/portal/agents
# Expect: 1 agent. 实际今晚返回 0. ← 这里是 bug 起点
```

定位 bug 后修复，跑通完整 1v1 链路。

### 步骤 2（1-2h）— 多 agent 协同跨 node

修完 1v1 后，挑一个最简单场景先做（推荐 **Project task assignment**）：
- master 创建 project，task 分给 worker 上的 agent
- 验证 master 能看到任务进度，worker 真在跑 LLM call
- 这跑通后 meeting / orchestrate 是同样模式

### 步骤 3（2-3h）— RAG 全流程

- 准备 5-10 个真实文档（比如 docs/ 目录下的 .md）
- 走 ingest → search 流程
- 跑 5-10 个 query 看效果
- 写一份 RAG 质量评估报告

---

## 今晚 commit 串

```
bd6fe1b  fix(multi-node): init_hub now reads TUDOU_NODE_ID  ← 今晚 ship
8934751  feat(multi-node): SSE pass-through for cross-node chat
9a8dda5  feat(multi-node): master can create agents on workers
b7b598f  docs(multi-node): full Master/Worker deployment guide
a92bad0  feat(multi-node): worker boot-time registration + role cap
```

GitHub: https://github.com/panda-bobo/TudouClaw_new/commits/main

晚安 ✨
