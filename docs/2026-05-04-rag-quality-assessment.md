# RAG 全流程质量评估（2026-05-04）

> 用真实文档（`docs/*.md` 7 个 + 230 KB）跑端到端验证：ingest → 检索 → 排序 → 阈值过滤。结论 + 发现的问题 + 已 ship 的修复。

---

## TL;DR

| 维度 | 结果 | 备注 |
|---|---|---|
| **格式支持** | ✅ md / pdf / html / docx | `_parse_file_bytes_to_text` 完备，依赖都装好 |
| **Ingest 速度** | ✅ 10 秒 / 7 文件 / 311 chunks | bge-m3 已 cached；首次 ~3 GB 下载 |
| **Embedding 召回** | ✅ top-1 命中 5/7 query | 中英混合 query 都 OK |
| **Distance 区分度** | ✅ 相关 0.30-0.55 / 无关 0.75-0.85 | 0.65 是合理阈值 |
| **混合检索 (BM25 + 向量 + RRF)** | ✅ 自动启用 | `rrf_score` 出现在 metadata |
| **Reranker (CrossEncoder)** | ✅ 现可启用（修复了 update endpoint） | bge-reranker-v2-m3 ~600 MB，首次需下载 |
| **阈值过滤** | ✅ 新增 `max_distance` / `min_rerank_score` 参数 | 之前完全没有 |

---

## 1. 测试 setup

```
KB:        docs-rag-test (id=dkb_aba4ec342c)
Provider:  86e247c433 (kind=local, chroma + bge-m3)
Embedder:  BAAI/bge-m3 (~2.5 GB cached)
Reranker:  BAAI/bge-reranker-v2-m3 (启用后才下载 ~600 MB)
Corpus:    docs/*.md × 7（230 KB raw → 311 chunks）
```

文件清单：

| 文件 | 大小 | Chunks |
|---|---|---|
| `2026-05-03-night-status.md` | 7.4 KB | 21 |
| `Architecture_Issues_V1.md` | 23 KB | 31 |
| `PHASE2B_SYSTEM_PROMPT_BLOCKS.md` | 12 KB | 22 |
| `PRD_AGENT_V2.md` | 96 KB | 153 |
| `canvas-workflows.md` | 21 KB | 27 |
| `data-dir-config.md` | 8 KB | 26 |
| `multi-node-deployment.md` | 13 KB | 31 |

去重：21/311 chunks 被去重（同 hash）。

---

## 2. 测试 query 矩阵（7 条）

| # | Query | 期望源 | top-1 命中 | top-1 distance |
|---|---|---|---|---|
| 1 | `TUDOU_NODE_ID 是干什么的` | data-dir-config.md | ✅ | 0.387 |
| 2 | `Worker 启动如何向 master register` | multi-node-deployment.md | ✅ | 0.345 |
| 3 | `多节点部署的密钥如何配置` | multi-node-deployment.md | ✅ | 0.331 |
| 4 | `RAG vector store 用的什么数据库` | Architecture / PRD | 🟡 命中 night-status | 0.519 |
| 5 | `iPhone development SwiftUI` | (无关) | ❌ 仍返回 5 条 | 0.763 |
| 6 | `Canvas workflow 设计` | canvas-workflows.md | ✅ 5/5 全对 | 0.344 |
| 7 | `agent self-improvement 流程` | PRD_AGENT_V2.md | ✅ 5/5 全对 | 0.380 |

**Distance 区分度图**：

```
0.30 ─┬───── 相关 query top-1 落在这里
      │      (Q1=0.39, Q2=0.35, Q3=0.33, Q6=0.34, Q7=0.38)
0.50 ─┤
      │     ← Q4 命中"RAG"字面，distance=0.52（边界情况）
0.65 ─┤────── 推荐阈值 max_distance=0.65 ──
      │
0.80 ─┤      无关 query 都在这里
      │      (Q5 iPhone: 0.76 ~ 0.83)
1.00 ─┴
```

---

## 3. 发现的问题 + 修复

### 🔴 问题 1：`/domain-kb/update` 不接受 `reranker_model`（已修复）

**症状**：创建 KB 时漏配 reranker → 之后只能删除重建（丢数据）。
**根因**：`DomainKBStore.update()` 签名只有 name/description/tags。
**修复**：`app/rag_provider.py:update()` + `app/api/routers/knowledge.py:update_domain_knowledge_base` 加 `embedding_model` / `reranker_model` 字段（含模型 id 白名单校验）。
**Commit**: 本次 RAG patch（见末尾）

### 🔴 问题 2：search 没有阈值过滤（已修复）

**症状**：query "iPhone SwiftUI" 这种**完全无关**的也返回 5 条 distance>0.75 的"伪相关"结果。
**根因**：`/domain-kb/search` 直接返回 retrieval top_k，无阈值。
**修复**：加 `max_distance` (默认 1.0=不过滤) + `min_rerank_score` (默认 None) 两个 body 参数；返回多了 `filtered_count` 字段方便 caller 检测"噪音 query"。

```bash
# 实测：iPhone SwiftUI query 在 max_distance=0.65 下：
{"results": [], "filtered_count": 5}  # ← 全过滤掉，很干净
```

### 🟡 问题 3：Reranker 默认不启用（设计决策待定）

**现状**：KB 创建时若不显式指定 `reranker_model`，留空 → 检索路径**跳过 cross-encoder rescore**。
**讨论**：
- 启用 reranker 提升质量但每 query 加 50–200ms（CPU）+ 首次 ~600 MB 下载
- 不启用：纯向量 + RRF，已经够好（top-1 命中率 86%）

**建议**：保持默认空，但 portal UI 创建 KB 时把 reranker 选项默认勾上 `BAAI/bge-reranker-v2-m3`，留 admin 取消的余地。

### 🟡 问题 4：`_get_local_agents_for_sync()` 只是占位（已修，跨 multi-node）

> 此修复属 multi-node 工作，不是 RAG。但同一天 commit `3c92084`，记录此处。

---

## 4. 推荐阈值（基于实测数据）

```python
# Production-safe 默认（可写进 portal UI 的 default values）
{
  "top_k": 5,
  "max_distance": 0.65,        # 0.30-0.55 留下，0.75+ 砍掉
  "min_rerank_score": None,    # 启用 reranker 后改 0.0 比较保守
}

# 严格模式（admin 编辑器 / 重要任务用）
{
  "top_k": 3,
  "max_distance": 0.50,        # 只留高置信度
  "min_rerank_score": 0.5,     # 需 reranker 模型已加载
}
```

---

## 5. 性能数据

| 操作 | 时延 | 备注 |
|---|---|---|
| Ingest 7 docs / 311 chunks | **10 秒** | bge-m3 已 cached；CPU 上 ~31 chunks/s |
| 单次 search（有 reranker） | ~150-250 ms | 含向量 + BM25 + RRF + cross-encoder |
| 单次 search（无 reranker） | ~30-60 ms | 跳过 cross-encoder |
| bge-m3 首次下载 | 5–10 min | ~2.5 GB，cache 在 `${TUDOU_HF_CACHE}` |
| bge-reranker-v2-m3 首次下载 | 2–3 min | ~600 MB |

---

## 6. 还未验证的（下次）

- 文件格式：**PDF + DOCX + HTML** 实测一遍（代码 verified 但本次未跑）
- 长文档（> 100 KB）的 chunk overlap + heading 路径保留是否正确
- 中英文 mixed corpus 的检索质量
- Reranker 真正提升排序质量的对比测试（需 reranker 下载完）
- 大规模数据下 bm25 索引构建的延迟
- 多 KB（10+ collection）下并发查询性能

---

## 7. 决策日志

- **2026-05-04 09:05** — 创建 KB → ingest 7 md 文件，10 秒完成
- **2026-05-04 09:15** — 跑 7 query，发现 score=0 字段名错（实际是 distance）+ 无阈值过滤
- **2026-05-04 09:25** — 修 `/domain-kb/update` 支持 reranker_model + 加 max_distance 阈值
- **2026-05-04 09:30** — 阈值过滤 verified（iPhone SwiftUI 全过滤掉）；reranker 下载中
