"""
database.py — 统一 SQLite 持久化层。

将所有原先散落在各模块中的 JSON 文件合并为一个 SQLite 数据库，
同时保持与现有代码相同的 dict 读写接口，实现无缝迁移。

数据库文件: ~/.tudou_claw/tudou_claw.db

设计原则:
  1. 每个原 JSON 文件对应一张表
  2. 核心索引字段为真实列，业务字段存 JSON (`data` 列)
  3. 提供 CRUD + 批量操作接口
  4. 线程安全 (connection-per-thread via check_same_thread=False + RLock)
  5. 内置迁移：首次运行自动从 JSON 文件导入
"""

import json
import logging
import os
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("tudou.database")

# ---------------------------------------------------------------------------
# Globals
# ---------------------------------------------------------------------------
_db: Optional["TudouDatabase"] = None
_lock = threading.Lock()


def get_database() -> "TudouDatabase":
    """获取全局数据库单例。"""
    global _db
    if _db is None:
        with _lock:
            if _db is None:
                _db = TudouDatabase()
    return _db


def init_database(data_dir: str = "") -> "TudouDatabase":
    """显式初始化数据库（可指定数据目录）。"""
    global _db
    with _lock:
        _db = TudouDatabase(data_dir=data_dir)
    return _db


# ---------------------------------------------------------------------------
# Database class
# ---------------------------------------------------------------------------

class TudouDatabase:
    """统一 SQLite 持久化层。"""

    # 数据库版本号，用于 schema 迁移
    SCHEMA_VERSION = 1

    def __init__(self, data_dir: str = ""):
        if not data_dir:
            data_dir = os.path.join(os.path.expanduser("~"), ".tudou_claw")
        os.makedirs(data_dir, exist_ok=True)

        self._data_dir = data_dir
        self._db_path = os.path.join(data_dir, "tudou_claw.db")
        self._rlock = threading.RLock()

        # SQLite 连接 — check_same_thread=False 让多线程共享连接
        # 搭配 RLock 保护写操作安全
        self._conn = sqlite3.connect(
            self._db_path,
            check_same_thread=False,
            timeout=30,
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.row_factory = sqlite3.Row

        self._create_tables()
        self._check_migration()

        logger.info("SQLite database ready: %s", self._db_path)

    # ------------------------------------------------------------------
    # Context manager for write transactions
    # ------------------------------------------------------------------
    @contextmanager
    def _tx(self):
        """线程安全的写事务。"""
        with self._rlock:
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    # ------------------------------------------------------------------
    # Schema creation
    # ------------------------------------------------------------------
    def _create_tables(self):
        c = self._conn
        c.executescript("""
        -- 版本追踪
        CREATE TABLE IF NOT EXISTS _meta (
            key   TEXT PRIMARY KEY,
            value TEXT
        );

        -- agents.json
        CREATE TABLE IF NOT EXISTS agents (
            agent_id   TEXT PRIMARY KEY,
            name       TEXT NOT NULL DEFAULT '',
            role       TEXT NOT NULL DEFAULT '',
            status     TEXT NOT NULL DEFAULT 'idle',
            node_id    TEXT NOT NULL DEFAULT 'local',
            data       TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL DEFAULT 0,
            updated_at REAL NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_agents_node ON agents(node_id);
        CREATE INDEX IF NOT EXISTS idx_agents_role ON agents(role);

        -- nodes.json (remote nodes)
        CREATE TABLE IF NOT EXISTS nodes (
            node_id    TEXT PRIMARY KEY,
            name       TEXT NOT NULL DEFAULT '',
            url        TEXT NOT NULL DEFAULT '',
            status     TEXT NOT NULL DEFAULT 'unknown',
            data       TEXT NOT NULL DEFAULT '{}',
            last_seen  REAL NOT NULL DEFAULT 0,
            created_at REAL NOT NULL DEFAULT 0
        );

        -- node_configs.json
        CREATE TABLE IF NOT EXISTS node_configs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id    TEXT NOT NULL DEFAULT '',
            key        TEXT NOT NULL DEFAULT '',
            value      TEXT NOT NULL DEFAULT '',
            category   TEXT NOT NULL DEFAULT '',
            is_secret  INTEGER NOT NULL DEFAULT 0,
            data       TEXT NOT NULL DEFAULT '{}',
            UNIQUE(node_id, key)
        );
        CREATE INDEX IF NOT EXISTS idx_nc_node ON node_configs(node_id);

        -- projects.json
        CREATE TABLE IF NOT EXISTS projects (
            project_id TEXT PRIMARY KEY,
            name       TEXT NOT NULL DEFAULT '',
            status     TEXT NOT NULL DEFAULT 'active',
            data       TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL DEFAULT 0,
            updated_at REAL NOT NULL DEFAULT 0
        );

        -- channels.json
        CREATE TABLE IF NOT EXISTS channels (
            channel_id TEXT PRIMARY KEY,
            name       TEXT NOT NULL DEFAULT '',
            type       TEXT NOT NULL DEFAULT '',
            data       TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL DEFAULT 0
        );

        -- workflows.json — templates
        CREATE TABLE IF NOT EXISTS workflow_templates (
            template_id TEXT PRIMARY KEY,
            name        TEXT NOT NULL DEFAULT '',
            data        TEXT NOT NULL DEFAULT '{}',
            created_at  REAL NOT NULL DEFAULT 0
        );

        -- workflows.json — instances
        CREATE TABLE IF NOT EXISTS workflow_instances (
            instance_id TEXT PRIMARY KEY,
            template_id TEXT NOT NULL DEFAULT '',
            status      TEXT NOT NULL DEFAULT 'pending',
            data        TEXT NOT NULL DEFAULT '{}',
            created_at  REAL NOT NULL DEFAULT 0,
            updated_at  REAL NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_wi_tpl ON workflow_instances(template_id);
        CREATE INDEX IF NOT EXISTS idx_wi_status ON workflow_instances(status);

        -- .tudou_admins.json
        CREATE TABLE IF NOT EXISTS admins (
            username   TEXT PRIMARY KEY,
            role       TEXT NOT NULL DEFAULT 'admin',
            data       TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL DEFAULT 0
        );

        -- .tudou_tokens.json
        CREATE TABLE IF NOT EXISTS tokens (
            token_id   TEXT PRIMARY KEY,
            name       TEXT NOT NULL DEFAULT '',
            admin      TEXT NOT NULL DEFAULT '',
            role       TEXT NOT NULL DEFAULT '',
            active     INTEGER NOT NULL DEFAULT 1,
            data       TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_tokens_admin ON tokens(admin);

        -- providers.json
        CREATE TABLE IF NOT EXISTS providers (
            provider_id TEXT PRIMARY KEY,
            name        TEXT NOT NULL DEFAULT '',
            data        TEXT NOT NULL DEFAULT '{}',
            created_at  REAL NOT NULL DEFAULT 0
        );

        -- scheduled_jobs.json
        CREATE TABLE IF NOT EXISTS scheduled_jobs (
            job_id     TEXT PRIMARY KEY,
            name       TEXT NOT NULL DEFAULT '',
            type       TEXT NOT NULL DEFAULT '',
            cron       TEXT NOT NULL DEFAULT '',
            enabled    INTEGER NOT NULL DEFAULT 1,
            data       TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL DEFAULT 0
        );

        -- execution_history (per-job records)
        CREATE TABLE IF NOT EXISTS execution_history (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id     TEXT NOT NULL DEFAULT '',
            status     TEXT NOT NULL DEFAULT '',
            started_at REAL NOT NULL DEFAULT 0,
            ended_at   REAL NOT NULL DEFAULT 0,
            data       TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_eh_job ON execution_history(job_id);
        CREATE INDEX IF NOT EXISTS idx_eh_started ON execution_history(started_at);

        -- mcp_configs.json
        CREATE TABLE IF NOT EXISTS mcp_configs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id    TEXT NOT NULL DEFAULT '',
            mcp_id     TEXT NOT NULL DEFAULT '',
            data       TEXT NOT NULL DEFAULT '{}',
            UNIQUE(node_id, mcp_id)
        );
        CREATE INDEX IF NOT EXISTS idx_mcp_node ON mcp_configs(node_id);

        -- template_library _index.json
        CREATE TABLE IF NOT EXISTS template_library (
            template_id TEXT PRIMARY KEY,
            name        TEXT NOT NULL DEFAULT '',
            role        TEXT NOT NULL DEFAULT '',
            category    TEXT NOT NULL DEFAULT '',
            enabled     INTEGER NOT NULL DEFAULT 1,
            data        TEXT NOT NULL DEFAULT '{}',
            created_at  REAL NOT NULL DEFAULT 0
        );

        -- experience_library entries
        CREATE TABLE IF NOT EXISTS experiences (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            role        TEXT NOT NULL DEFAULT '',
            type        TEXT NOT NULL DEFAULT '',
            period      TEXT NOT NULL DEFAULT '',
            priority    INTEGER NOT NULL DEFAULT 0,
            data        TEXT NOT NULL DEFAULT '{}',
            created_at  REAL NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_exp_role ON experiences(role);
        CREATE INDEX IF NOT EXISTS idx_exp_period ON experiences(period);
        CREATE INDEX IF NOT EXISTS idx_exp_priority ON experiences(priority);

        -- delegation requests (P1-2)
        CREATE TABLE IF NOT EXISTS delegations (
            request_id  TEXT PRIMARY KEY,
            from_agent  TEXT NOT NULL DEFAULT '',
            to_agent    TEXT NOT NULL DEFAULT '',
            status      TEXT NOT NULL DEFAULT 'pending',
            priority    INTEGER NOT NULL DEFAULT 5,
            data        TEXT NOT NULL DEFAULT '{}',
            created_at  REAL NOT NULL DEFAULT 0,
            updated_at  REAL NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_del_status ON delegations(status);

        -- approval requests (P1-3)
        CREATE TABLE IF NOT EXISTS approvals (
            request_id  TEXT PRIMARY KEY,
            type        TEXT NOT NULL DEFAULT '',
            status      TEXT NOT NULL DEFAULT 'pending',
            agent_id    TEXT NOT NULL DEFAULT '',
            data        TEXT NOT NULL DEFAULT '{}',
            created_at  REAL NOT NULL DEFAULT 0,
            decided_at  REAL NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_appr_status ON approvals(status);
        CREATE INDEX IF NOT EXISTS idx_appr_type ON approvals(type);

        -- agent_messages (Agent 间消息持久化)
        CREATE TABLE IF NOT EXISTS agent_messages (
            id          TEXT PRIMARY KEY,
            from_agent  TEXT NOT NULL DEFAULT '',
            to_agent    TEXT NOT NULL DEFAULT '',
            content     TEXT NOT NULL DEFAULT '',
            msg_type    TEXT NOT NULL DEFAULT 'task',
            timestamp   REAL NOT NULL DEFAULT 0,
            status      TEXT NOT NULL DEFAULT 'pending'
        );
        CREATE INDEX IF NOT EXISTS idx_amsg_ts ON agent_messages(timestamp);
        CREATE INDEX IF NOT EXISTS idx_amsg_from ON agent_messages(from_agent);
        CREATE INDEX IF NOT EXISTS idx_amsg_to ON agent_messages(to_agent);
        CREATE INDEX IF NOT EXISTS idx_amsg_status ON agent_messages(status);

        -- audit_log (原 audit.log 行式 JSON → 结构化表)
        CREATE TABLE IF NOT EXISTS audit_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   REAL NOT NULL DEFAULT 0,
            actor       TEXT NOT NULL DEFAULT '',
            action      TEXT NOT NULL DEFAULT '',
            target      TEXT NOT NULL DEFAULT '',
            data        TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(timestamp);
        CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_log(actor);

        -- ============================================================
        -- 三层记忆架构 (Three-Layer Memory)
        -- ============================================================

        -- L2: Episodic Memory — 对话摘要
        CREATE TABLE IF NOT EXISTS memory_episodic (
            id          TEXT PRIMARY KEY,
            agent_id    TEXT NOT NULL DEFAULT '',
            summary     TEXT NOT NULL DEFAULT '',
            keywords    TEXT NOT NULL DEFAULT '',
            turn_start  INTEGER NOT NULL DEFAULT 0,
            turn_end    INTEGER NOT NULL DEFAULT 0,
            message_count INTEGER NOT NULL DEFAULT 0,
            created_at  REAL NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_me_agent ON memory_episodic(agent_id);
        CREATE INDEX IF NOT EXISTS idx_me_created ON memory_episodic(created_at);

        -- L3: Semantic Memory — 长期事实
        CREATE TABLE IF NOT EXISTS memory_semantic (
            id          TEXT PRIMARY KEY,
            agent_id    TEXT NOT NULL DEFAULT '',
            category    TEXT NOT NULL DEFAULT 'general',
            content     TEXT NOT NULL DEFAULT '',
            source      TEXT NOT NULL DEFAULT '',
            confidence  REAL NOT NULL DEFAULT 1.0,
            created_at  REAL NOT NULL DEFAULT 0,
            updated_at  REAL NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_ms_agent ON memory_semantic(agent_id);
        CREATE INDEX IF NOT EXISTS idx_ms_cat ON memory_semantic(category);

        -- 记忆配置表
        CREATE TABLE IF NOT EXISTS memory_config (
            agent_id    TEXT PRIMARY KEY,
            data        TEXT NOT NULL DEFAULT '{}'
        );

        -- ============================================================
        -- 分布式架构表 (Distributed Architecture)
        -- ============================================================

        -- node_routes: Node routing table
        CREATE TABLE IF NOT EXISTS node_routes (
            node_id TEXT PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            status TEXT DEFAULT 'offline',
            capabilities TEXT DEFAULT '{}',
            agent_count INTEGER DEFAULT 0,
            last_seen DATETIME,
            ws_connected BOOLEAN DEFAULT 0,
            config_version INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_nr_status ON node_routes(status);
        CREATE INDEX IF NOT EXISTS idx_nr_ws ON node_routes(ws_connected);

        -- agent_routes: Agent-to-Node routing
        CREATE TABLE IF NOT EXISTS agent_routes (
            agent_id TEXT PRIMARY KEY,
            node_id TEXT NOT NULL DEFAULT 'local',
            status TEXT DEFAULT 'idle',
            model TEXT DEFAULT '',
            provider TEXT DEFAULT '',
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_ar_node ON agent_routes(node_id);
        CREATE INDEX IF NOT EXISTS idx_ar_status ON agent_routes(status);

        -- config_changelog: Configuration version tracking
        CREATE TABLE IF NOT EXISTS config_changelog (
            version INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            action TEXT NOT NULL,
            data TEXT DEFAULT '{}',
            admin TEXT DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_cc_scope ON config_changelog(scope);
        CREATE INDEX IF NOT EXISTS idx_cc_created ON config_changelog(created_at);

        -- file_manifests: Workspace file tracking
        CREATE TABLE IF NOT EXISTS file_manifests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT NOT NULL,
            file_path TEXT NOT NULL,
            hash_sha256 TEXT NOT NULL DEFAULT '',
            size_bytes INTEGER DEFAULT 0,
            node_id TEXT DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(agent_id, file_path)
        );
        CREATE INDEX IF NOT EXISTS idx_fm_agent ON file_manifests(agent_id);
        CREATE INDEX IF NOT EXISTS idx_fm_node ON file_manifests(node_id);
        CREATE INDEX IF NOT EXISTS idx_fm_path ON file_manifests(file_path);
        """)
        # FTS5 虚拟表需单独创建（executescript 不支持 VIRTUAL TABLE 在同一脚本中）
        self._create_fts_tables()
        self._conn.commit()

    def _create_fts_tables(self):
        """创建 FTS5 全文索引表及其自动同步触发器。"""
        c = self._conn
        # L2 FTS5
        try:
            c.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_episodic_fts USING fts5(
                    summary, keywords,
                    content=memory_episodic,
                    content_rowid=rowid
                )
            """)
        except sqlite3.OperationalError:
            pass  # 已存在

        # L2 触发器
        for sql in [
            """CREATE TRIGGER IF NOT EXISTS memory_episodic_ai
               AFTER INSERT ON memory_episodic BEGIN
                 INSERT INTO memory_episodic_fts(rowid, summary, keywords)
                 VALUES (new.rowid, new.summary, new.keywords);
               END""",
            """CREATE TRIGGER IF NOT EXISTS memory_episodic_ad
               AFTER DELETE ON memory_episodic BEGIN
                 INSERT INTO memory_episodic_fts(memory_episodic_fts, rowid, summary, keywords)
                 VALUES ('delete', old.rowid, old.summary, old.keywords);
               END""",
            """CREATE TRIGGER IF NOT EXISTS memory_episodic_au
               AFTER UPDATE ON memory_episodic BEGIN
                 INSERT INTO memory_episodic_fts(memory_episodic_fts, rowid, summary, keywords)
                 VALUES ('delete', old.rowid, old.summary, old.keywords);
                 INSERT INTO memory_episodic_fts(rowid, summary, keywords)
                 VALUES (new.rowid, new.summary, new.keywords);
               END""",
        ]:
            try:
                c.execute(sql)
            except sqlite3.OperationalError:
                pass

        # L3 FTS5
        try:
            c.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_semantic_fts USING fts5(
                    content, category, source,
                    content=memory_semantic,
                    content_rowid=rowid
                )
            """)
        except sqlite3.OperationalError:
            pass

        # L3 触发器
        for sql in [
            """CREATE TRIGGER IF NOT EXISTS memory_semantic_ai
               AFTER INSERT ON memory_semantic BEGIN
                 INSERT INTO memory_semantic_fts(rowid, content, category, source)
                 VALUES (new.rowid, new.content, new.category, new.source);
               END""",
            """CREATE TRIGGER IF NOT EXISTS memory_semantic_ad
               AFTER DELETE ON memory_semantic BEGIN
                 INSERT INTO memory_semantic_fts(memory_semantic_fts, rowid, content, category, source)
                 VALUES ('delete', old.rowid, old.content, old.category, old.source);
               END""",
            """CREATE TRIGGER IF NOT EXISTS memory_semantic_au
               AFTER UPDATE ON memory_semantic BEGIN
                 INSERT INTO memory_semantic_fts(memory_semantic_fts, rowid, content, category, source)
                 VALUES ('delete', old.rowid, old.content, old.category, old.source);
                 INSERT INTO memory_semantic_fts(rowid, content, category, source)
                 VALUES (new.rowid, new.content, new.category, new.source);
               END""",
        ]:
            try:
                c.execute(sql)
            except sqlite3.OperationalError:
                pass

    # ------------------------------------------------------------------
    # Schema migration check
    # ------------------------------------------------------------------
    def _check_migration(self):
        row = self._conn.execute(
            "SELECT value FROM _meta WHERE key='schema_version'"
        ).fetchone()
        current = int(row["value"]) if row else 0

        if current < self.SCHEMA_VERSION:
            # 首次或版本升级 — 执行迁移
            self._conn.execute(
                "INSERT OR REPLACE INTO _meta(key,value) VALUES(?,?)",
                ("schema_version", str(self.SCHEMA_VERSION)),
            )
            self._conn.commit()
            logger.info("Schema version set to %d", self.SCHEMA_VERSION)

    # ==================================================================
    # Generic CRUD helpers
    # ==================================================================

    def upsert(self, table: str, pk_col: str, pk_val: str,
               columns: dict[str, Any] = None, data: dict = None):
        """插入或更新一行。columns 为命名列，data 合并到 data 列。"""
        columns = columns or {}
        now = time.time()
        existing = self._conn.execute(
            f"SELECT data FROM {table} WHERE {pk_col}=?", (pk_val,)
        ).fetchone()

        if existing:
            # UPDATE
            merged = json.loads(existing["data"]) if existing["data"] else {}
            if data:
                merged.update(data)
            sets = [f"{k}=?" for k in columns]
            sets.append("data=?")
            if "updated_at" in self._get_columns(table):
                sets.append("updated_at=?")
            vals = list(columns.values()) + [json.dumps(merged, ensure_ascii=False)]
            if "updated_at" in self._get_columns(table):
                vals.append(now)
            vals.append(pk_val)
            with self._tx():
                self._conn.execute(
                    f"UPDATE {table} SET {','.join(sets)} WHERE {pk_col}=?",
                    vals,
                )
        else:
            # INSERT
            all_cols = {pk_col: pk_val}
            all_cols.update(columns)
            all_cols["data"] = json.dumps(data or {}, ensure_ascii=False)
            if "created_at" in self._get_columns(table):
                all_cols.setdefault("created_at", now)
            if "updated_at" in self._get_columns(table):
                all_cols.setdefault("updated_at", now)
            placeholders = ",".join(["?"] * len(all_cols))
            col_names = ",".join(all_cols.keys())
            with self._tx():
                self._conn.execute(
                    f"INSERT INTO {table}({col_names}) VALUES({placeholders})",
                    list(all_cols.values()),
                )

    def get(self, table: str, pk_col: str, pk_val: str) -> Optional[dict]:
        """按主键取一行，返回合并后的 dict 或 None。"""
        row = self._conn.execute(
            f"SELECT * FROM {table} WHERE {pk_col}=?", (pk_val,)
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def get_all(self, table: str, where: str = "",
                params: tuple = (), order: str = "") -> list[dict]:
        """查询多行。where 使用 ? 占位符，order 使用白名单验证。"""
        sql = f"SELECT * FROM {table}"
        if where:
            sql += f" WHERE {where}"
        if order:
            # ORDER BY 不能使用 ? 占位符，需要白名单验证列名
            valid_order = self._validate_order_by(order)
            if valid_order:
                sql += f" ORDER BY {valid_order}"
        rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def delete(self, table: str, pk_col: str, pk_val: str) -> bool:
        """删除一行。"""
        with self._tx():
            cur = self._conn.execute(
                f"DELETE FROM {table} WHERE {pk_col}=?", (pk_val,)
            )
        return cur.rowcount > 0

    def count(self, table: str, where: str = "", params: tuple = ()) -> int:
        """统计行数。where 使用 ? 占位符进行参数化。"""
        sql = f"SELECT COUNT(*) as cnt FROM {table}"
        if where:
            sql += f" WHERE {where}"
        row = self._conn.execute(sql, params).fetchone()
        return row["cnt"] if row else 0

    def execute(self, sql: str, params: tuple = ()) -> list[dict]:
        """执行自定义 SQL，返回结果列表。"""
        rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def execute_write(self, sql: str, params: tuple = ()) -> int:
        """执行写操作 SQL，返回 rowcount。"""
        with self._tx():
            cur = self._conn.execute(sql, params)
        return cur.rowcount

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    _columns_cache: dict[str, list[str]] = {}

    def _get_columns(self, table: str) -> list[str]:
        if table not in self._columns_cache:
            rows = self._conn.execute(f"PRAGMA table_info({table})").fetchall()
            self._columns_cache[table] = [r["name"] for r in rows]
        return self._columns_cache[table]

    def _validate_order_by(self, order: str) -> str:
        """验证 ORDER BY 子句以防止 SQL 注入。

        允许的格式: 列名, 列名 ASC, 列名 DESC, 列名1, 列名2 DESC 等
        只允许字母、数字、下划线、逗号、空格和 ASC/DESC 关键字。
        """
        if not order or not order.strip():
            return ""

        # 快速检查：只允许字母、数字、下划线、点、逗号、空格和 ASC/DESC
        if not re.match(r'^[\w\s,.()+\-]*$', order):
            return ""

        # 解析 ORDER BY 子句：分割多个排序条件
        parts = []
        for item in order.split(","):
            item = item.strip()
            if not item:
                continue

            # 处理每个排序条件：可能是 "col ASC" 或 "col DESC" 或 "col" 或 "table.col ASC"
            tokens = item.split()
            if not tokens:
                continue

            col_part = tokens[0]

            # 检查是否包含非法字符
            if not re.match(r'^[\w.]+$', col_part):
                continue

            # 支持 table.column 或 column 的形式
            if "." in col_part:
                parts_split = col_part.split(".")
                if len(parts_split) != 2:
                    continue
                table_name, col_name = parts_split
                # 验证列名和表名都只包含字母、数字、下划线
                if not (re.match(r'^[a-zA-Z_]\w*$', col_name) and
                        re.match(r'^[a-zA-Z_]\w*$', table_name)):
                    continue
            else:
                col_name = col_part
                # 验证列名只包含字母、数字、下划线，且不能以数字开头
                if not re.match(r'^[a-zA-Z_]\w*$', col_name):
                    continue

            # 验证排序方向（如果有）
            direction = ""
            if len(tokens) > 1:
                dir_upper = tokens[1].upper()
                if dir_upper in ("ASC", "DESC"):
                    direction = f" {dir_upper}"
                else:
                    # 如果有额外的token，则此项无效
                    continue

            # 最后检查是否只有预期的tokens
            if len(tokens) > 2:
                continue

            parts.append(col_part + direction)

        return ", ".join(parts) if parts else ""

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        """将一行转为 dict，并把 data 列的 JSON 合并进来。"""
        d = dict(row)
        if "data" in d:
            try:
                extra = json.loads(d["data"])
                if isinstance(extra, dict):
                    # extra 中的键不覆盖命名列
                    for k, v in extra.items():
                        if k not in d:
                            d[k] = v
            except (json.JSONDecodeError, TypeError):
                pass
        return d

    # ==================================================================
    # 专用接口 — Agents
    # ==================================================================

    def save_agent(self, agent_dict: dict):
        """保存/更新一个 agent。"""
        aid = agent_dict.get("id", agent_dict.get("agent_id", ""))
        self.upsert("agents", "agent_id", aid, columns={
            "name": agent_dict.get("name", ""),
            "role": agent_dict.get("role", ""),
            "status": agent_dict.get("status", "idle"),
            "node_id": agent_dict.get("node_id", "local"),
        }, data=agent_dict)

    def load_agents(self) -> list[dict]:
        return self.get_all("agents")

    def delete_agent(self, agent_id: str) -> bool:
        return self.delete("agents", "agent_id", agent_id)

    # ==================================================================
    # 专用接口 — Remote Nodes
    # ==================================================================

    def save_node(self, node_dict: dict):
        nid = node_dict.get("node_id", "")
        self.upsert("nodes", "node_id", nid, columns={
            "name": node_dict.get("name", ""),
            "url": node_dict.get("url", ""),
            "status": node_dict.get("status", "unknown"),
            "last_seen": node_dict.get("last_seen", 0),
        }, data=node_dict)

    def load_nodes(self) -> list[dict]:
        return self.get_all("nodes")

    def delete_node(self, node_id: str) -> bool:
        return self.delete("nodes", "node_id", node_id)

    # ==================================================================
    # 专用接口 — Node Configs
    # ==================================================================

    def save_node_config(self, node_id: str, key: str, value: str,
                         category: str = "", is_secret: bool = False,
                         extra: dict = None):
        with self._tx():
            self._conn.execute("""
                INSERT INTO node_configs(node_id, key, value, category, is_secret, data)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(node_id, key) DO UPDATE SET
                    value=excluded.value,
                    category=excluded.category,
                    is_secret=excluded.is_secret,
                    data=excluded.data
            """, (node_id, key, value, category, int(is_secret),
                  json.dumps(extra or {}, ensure_ascii=False)))

    def load_node_configs(self, node_id: str = "") -> list[dict]:
        if node_id:
            return self.get_all("node_configs", "node_id=?", (node_id,))
        return self.get_all("node_configs")

    def delete_node_config(self, node_id: str, key: str) -> bool:
        with self._tx():
            cur = self._conn.execute(
                "DELETE FROM node_configs WHERE node_id=? AND key=?",
                (node_id, key))
        return cur.rowcount > 0

    # ==================================================================
    # 专用接口 — Node Routes (Distributed Architecture)
    # ==================================================================

    def save_node_route(self, node_id: str, name: str = "", status: str = "offline",
                        capabilities: dict = None, agent_count: int = 0,
                        ws_connected: bool = False, config_version: int = 0):
        """Save/update a node route."""
        with self._tx():
            self._conn.execute("""
                INSERT INTO node_routes(node_id, name, status, capabilities, agent_count,
                                       ws_connected, config_version, last_seen)
                VALUES(?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
                ON CONFLICT(node_id) DO UPDATE SET
                    name=excluded.name,
                    status=excluded.status,
                    capabilities=excluded.capabilities,
                    agent_count=excluded.agent_count,
                    ws_connected=excluded.ws_connected,
                    config_version=excluded.config_version,
                    last_seen=CURRENT_TIMESTAMP
            """, (node_id, name, status, json.dumps(capabilities or {}, ensure_ascii=False),
                  agent_count, int(ws_connected), config_version))

    def load_node_routes(self) -> list[dict]:
        """Load all node routes."""
        return self.get_all("node_routes")

    def get_node_route(self, node_id: str) -> Optional[dict]:
        """Get a single node route by ID."""
        return self.get("node_routes", "node_id", node_id)

    def delete_node_route(self, node_id: str) -> bool:
        """Delete a node route."""
        return self.delete("node_routes", "node_id", node_id)

    # ==================================================================
    # 专用接口 — Agent Routes (Distributed Architecture)
    # ==================================================================

    def save_agent_route(self, agent_id: str, node_id: str = "local",
                        status: str = "idle", model: str = "", provider: str = ""):
        """Save/update an agent route."""
        with self._tx():
            self._conn.execute("""
                INSERT INTO agent_routes(agent_id, node_id, status, model, provider, updated_at)
                VALUES(?,?,?,?,?,CURRENT_TIMESTAMP)
                ON CONFLICT(agent_id) DO UPDATE SET
                    node_id=excluded.node_id,
                    status=excluded.status,
                    model=excluded.model,
                    provider=excluded.provider,
                    updated_at=CURRENT_TIMESTAMP
            """, (agent_id, node_id, status, model, provider))

    def load_agent_routes(self) -> list[dict]:
        """Load all agent routes."""
        return self.get_all("agent_routes")

    def get_agent_route(self, agent_id: str) -> Optional[dict]:
        """Get a single agent route by ID."""
        return self.get("agent_routes", "agent_id", agent_id)

    def delete_agent_route(self, agent_id: str) -> bool:
        """Delete an agent route."""
        return self.delete("agent_routes", "agent_id", agent_id)

    # ==================================================================
    # 专用接口 — Config Changelog (Distributed Architecture)
    # ==================================================================

    def save_config_change(self, scope: str, action: str, data: dict = None, admin: str = "") -> int:
        """Save a configuration change and return version."""
        with self._tx():
            cur = self._conn.execute("""
                INSERT INTO config_changelog(scope, action, data, admin, created_at)
                VALUES(?,?,?,?,CURRENT_TIMESTAMP)
            """, (scope, action, json.dumps(data or {}, ensure_ascii=False), admin))
        return cur.lastrowid

    def get_config_changes_since(self, version: int = 0) -> list[dict]:
        """Get config changes after a given version."""
        return self.get_all("config_changelog", "version > ?", (version,), "version ASC")

    def get_config_version(self) -> int:
        """Get the latest config version."""
        row = self._conn.execute(
            "SELECT MAX(version) as latest FROM config_changelog"
        ).fetchone()
        return row["latest"] or 0 if row else 0

    # ==================================================================
    # 专用接口 — File Manifests (Distributed Architecture)
    # ==================================================================

    def save_file_manifest(self, agent_id: str, file_path: str, hash_sha256: str = "",
                          size_bytes: int = 0, node_id: str = ""):
        """Save/update a file manifest entry."""
        with self._tx():
            self._conn.execute("""
                INSERT INTO file_manifests(agent_id, file_path, hash_sha256, size_bytes, node_id, created_at)
                VALUES(?,?,?,?,?,CURRENT_TIMESTAMP)
                ON CONFLICT(agent_id, file_path) DO UPDATE SET
                    hash_sha256=excluded.hash_sha256,
                    size_bytes=excluded.size_bytes,
                    node_id=excluded.node_id,
                    created_at=CURRENT_TIMESTAMP
            """, (agent_id, file_path, hash_sha256, size_bytes, node_id))

    def load_file_manifests(self, agent_id: str = "", node_id: str = "") -> list[dict]:
        """Load file manifests, optionally filtered by agent or node."""
        if agent_id and node_id:
            return self.get_all("file_manifests", "agent_id=? AND node_id=?", (agent_id, node_id))
        elif agent_id:
            return self.get_all("file_manifests", "agent_id=?", (agent_id,))
        elif node_id:
            return self.get_all("file_manifests", "node_id=?", (node_id,))
        return self.get_all("file_manifests")

    def delete_file_manifest(self, agent_id: str, file_path: str) -> bool:
        """Delete a file manifest entry."""
        with self._tx():
            cur = self._conn.execute(
                "DELETE FROM file_manifests WHERE agent_id=? AND file_path=?",
                (agent_id, file_path))
        return cur.rowcount > 0

    # ==================================================================
    # 专用接口 — Projects
    # ==================================================================

    def save_project(self, proj_dict: dict):
        pid = proj_dict.get("id", proj_dict.get("project_id", ""))
        self.upsert("projects", "project_id", pid, columns={
            "name": proj_dict.get("name", ""),
            "status": proj_dict.get("status", "active"),
        }, data=proj_dict)

    def load_projects(self) -> list[dict]:
        return self.get_all("projects")

    def delete_project(self, project_id: str) -> bool:
        return self.delete("projects", "project_id", project_id)

    # ==================================================================
    # 专用接口 — Channels
    # ==================================================================

    def save_channel(self, ch_dict: dict):
        cid = ch_dict.get("id", ch_dict.get("channel_id", ""))
        self.upsert("channels", "channel_id", cid, columns={
            "name": ch_dict.get("name", ""),
            "type": ch_dict.get("type", ""),
        }, data=ch_dict)

    def load_channels(self) -> list[dict]:
        return self.get_all("channels")

    def delete_channel(self, channel_id: str) -> bool:
        return self.delete("channels", "channel_id", channel_id)

    # ==================================================================
    # 专用接口 — Workflow Templates & Instances
    # ==================================================================

    def save_workflow_template(self, tpl_dict: dict):
        tid = tpl_dict.get("id", tpl_dict.get("template_id", ""))
        self.upsert("workflow_templates", "template_id", tid, columns={
            "name": tpl_dict.get("name", ""),
        }, data=tpl_dict)

    def load_workflow_templates(self) -> list[dict]:
        return self.get_all("workflow_templates")

    def delete_workflow_template(self, template_id: str) -> bool:
        return self.delete("workflow_templates", "template_id", template_id)

    def save_workflow_instance(self, inst_dict: dict):
        iid = inst_dict.get("id", inst_dict.get("instance_id", ""))
        self.upsert("workflow_instances", "instance_id", iid, columns={
            "template_id": inst_dict.get("template_id", ""),
            "status": inst_dict.get("status", "pending"),
        }, data=inst_dict)

    def load_workflow_instances(self) -> list[dict]:
        return self.get_all("workflow_instances")

    def delete_workflow_instance(self, instance_id: str) -> bool:
        return self.delete("workflow_instances", "instance_id", instance_id)

    # ==================================================================
    # 专用接口 — Admins
    # ==================================================================

    def save_admin(self, admin_dict: dict):
        username = admin_dict.get("username", "")
        self.upsert("admins", "username", username, columns={
            "role": admin_dict.get("role", "admin"),
        }, data=admin_dict)

    def load_admins(self) -> list[dict]:
        return self.get_all("admins")

    def delete_admin(self, username: str) -> bool:
        return self.delete("admins", "username", username)

    # ==================================================================
    # 专用接口 — Tokens
    # ==================================================================

    def save_token(self, token_dict: dict):
        tid = token_dict.get("id", token_dict.get("token_id", ""))
        self.upsert("tokens", "token_id", tid, columns={
            "name": token_dict.get("name", ""),
            "admin": token_dict.get("admin", ""),
            "role": token_dict.get("role", ""),
            "active": 1 if token_dict.get("active", True) else 0,
        }, data=token_dict)

    def load_tokens(self) -> list[dict]:
        return self.get_all("tokens")

    def delete_token(self, token_id: str) -> bool:
        return self.delete("tokens", "token_id", token_id)

    # ==================================================================
    # 专用接口 — Providers
    # ==================================================================

    def save_provider(self, prov_dict: dict):
        pid = prov_dict.get("id", prov_dict.get("provider_id", ""))
        self.upsert("providers", "provider_id", pid, columns={
            "name": prov_dict.get("name", ""),
        }, data=prov_dict)

    def load_providers(self) -> list[dict]:
        return self.get_all("providers")

    def delete_provider(self, provider_id: str) -> bool:
        return self.delete("providers", "provider_id", provider_id)

    # ==================================================================
    # 专用接口 — Scheduled Jobs
    # ==================================================================

    def save_job(self, job_dict: dict):
        jid = job_dict.get("id", job_dict.get("job_id", ""))
        self.upsert("scheduled_jobs", "job_id", jid, columns={
            "name": job_dict.get("name", ""),
            "type": job_dict.get("type", ""),
            "cron": job_dict.get("cron", job_dict.get("cron_expr", "")),
            "enabled": 1 if job_dict.get("enabled", True) else 0,
        }, data=job_dict)

    def load_jobs(self) -> list[dict]:
        return self.get_all("scheduled_jobs")

    def delete_job(self, job_id: str) -> bool:
        return self.delete("scheduled_jobs", "job_id", job_id)

    def add_execution_record(self, job_id: str, status: str,
                             started_at: float, ended_at: float = 0,
                             data: dict = None):
        with self._tx():
            self._conn.execute("""
                INSERT INTO execution_history(job_id, status, started_at, ended_at, data)
                VALUES(?,?,?,?,?)
            """, (job_id, status, started_at, ended_at,
                  json.dumps(data or {}, ensure_ascii=False)))

    def get_execution_history(self, job_id: str = "", limit: int = 100) -> list[dict]:
        if job_id:
            return self.get_all(
                "execution_history", "job_id=?", (job_id,),
                order="started_at DESC"
            )[:limit]
        return self.get_all(
            "execution_history", order="started_at DESC"
        )[:limit]

    # ==================================================================
    # 专用接口 — MCP Configs
    # ==================================================================

    def save_mcp_config(self, node_id: str, mcp_id: str, config_dict: dict):
        with self._tx():
            self._conn.execute("""
                INSERT INTO mcp_configs(node_id, mcp_id, data)
                VALUES(?,?,?)
                ON CONFLICT(node_id, mcp_id) DO UPDATE SET
                    data=excluded.data
            """, (node_id, mcp_id,
                  json.dumps(config_dict, ensure_ascii=False)))

    def load_mcp_configs(self, node_id: str = "") -> list[dict]:
        if node_id:
            return self.get_all("mcp_configs", "node_id=?", (node_id,))
        return self.get_all("mcp_configs")

    def delete_mcp_config(self, node_id: str, mcp_id: str) -> bool:
        with self._tx():
            cur = self._conn.execute(
                "DELETE FROM mcp_configs WHERE node_id=? AND mcp_id=?",
                (node_id, mcp_id))
        return cur.rowcount > 0

    # ==================================================================
    # 专用接口 — Template Library
    # ==================================================================

    def save_template_entry(self, tpl_dict: dict):
        tid = tpl_dict.get("id", tpl_dict.get("template_id", ""))
        self.upsert("template_library", "template_id", tid, columns={
            "name": tpl_dict.get("name", ""),
            "role": tpl_dict.get("role", ""),
            "category": tpl_dict.get("category", ""),
            "enabled": 1 if tpl_dict.get("enabled", True) else 0,
        }, data=tpl_dict)

    def load_template_entries(self) -> list[dict]:
        return self.get_all("template_library")

    def delete_template_entry(self, template_id: str) -> bool:
        return self.delete("template_library", "template_id", template_id)

    # ==================================================================
    # 专用接口 — Experiences
    # ==================================================================

    def save_experience(self, exp_dict: dict) -> int:
        """保存经验记录，返回 id。"""
        with self._tx():
            cur = self._conn.execute("""
                INSERT INTO experiences(role, type, period, priority, data, created_at)
                VALUES(?,?,?,?,?,?)
            """, (
                exp_dict.get("role", ""),
                exp_dict.get("type", ""),
                exp_dict.get("period", ""),
                exp_dict.get("priority", 0),
                json.dumps(exp_dict, ensure_ascii=False),
                exp_dict.get("created_at", time.time()),
            ))
        return cur.lastrowid

    def load_experiences(self, role: str = "", period: str = "",
                         min_priority: int = 0) -> list[dict]:
        conditions, params = [], []
        if role:
            conditions.append("role=?")
            params.append(role)
        if period:
            conditions.append("period=?")
            params.append(period)
        if min_priority > 0:
            conditions.append("priority>=?")
            params.append(min_priority)
        where = " AND ".join(conditions) if conditions else ""
        return self.get_all("experiences", where, tuple(params),
                            order="priority DESC, created_at DESC")

    def delete_experiences(self, role: str = "", period: str = "") -> int:
        conditions, params = [], []
        if role:
            conditions.append("role=?")
            params.append(role)
        if period:
            conditions.append("period=?")
            params.append(period)
        where = " AND ".join(conditions) if conditions else "1=1"
        return self.execute_write(
            f"DELETE FROM experiences WHERE {where}", tuple(params))

    # ==================================================================
    # 专用接口 — Delegations
    # ==================================================================

    def save_delegation(self, req_dict: dict):
        rid = req_dict.get("id", req_dict.get("request_id", ""))
        self.upsert("delegations", "request_id", rid, columns={
            "from_agent": req_dict.get("from_agent", ""),
            "to_agent": req_dict.get("to_agent", ""),
            "status": req_dict.get("status", "pending"),
            "priority": req_dict.get("priority", 5),
        }, data=req_dict)

    def load_delegations(self, status: str = "") -> list[dict]:
        if status:
            return self.get_all("delegations", "status=?", (status,))
        return self.get_all("delegations")

    # ==================================================================
    # 专用接口 — Approvals
    # ==================================================================

    def save_approval(self, req_dict: dict):
        rid = req_dict.get("id", req_dict.get("request_id", ""))
        self.upsert("approvals", "request_id", rid, columns={
            "type": req_dict.get("type", ""),
            "status": req_dict.get("status", "pending"),
            "agent_id": req_dict.get("agent_id", ""),
        }, data=req_dict)

    def load_approvals(self, status: str = "") -> list[dict]:
        if status:
            return self.get_all("approvals", "status=?", (status,))
        return self.get_all("approvals")

    # ==================================================================
    # 专用接口 — Audit Log
    # ==================================================================

    def add_audit(self, actor: str, action: str, target: str = "",
                  data: dict = None):
        with self._tx():
            self._conn.execute("""
                INSERT INTO audit_log(timestamp, actor, action, target, data)
                VALUES(?,?,?,?,?)
            """, (time.time(), actor, action, target,
                  json.dumps(data or {}, ensure_ascii=False)))

    def get_audit_log(self, limit: int = 200, actor: str = "",
                      action: str = "") -> list[dict]:
        conditions, params = [], []
        if actor:
            conditions.append("actor=?")
            params.append(actor)
        if action:
            conditions.append("action=?")
            params.append(action)
        where = " AND ".join(conditions) if conditions else ""
        results = self.get_all("audit_log", where, tuple(params),
                               order="timestamp DESC")
        return results[:limit]

    # ==================================================================
    # 专用接口 — Agent Messages
    # ==================================================================

    def save_message(self, msg_dict: dict):
        """Save or update an agent message."""
        msg_id = msg_dict.get("id", "")
        with self._tx():
            self._conn.execute("""
                INSERT OR REPLACE INTO agent_messages(
                    id, from_agent, to_agent, content, msg_type, timestamp, status
                ) VALUES(?,?,?,?,?,?,?)
            """, (
                msg_id,
                msg_dict.get("from_agent", ""),
                msg_dict.get("to_agent", ""),
                msg_dict.get("content", ""),
                msg_dict.get("msg_type", "task"),
                msg_dict.get("timestamp", time.time()),
                msg_dict.get("status", "pending"),
            ))

    def load_messages(self, limit: int = 3000) -> list[dict]:
        """Load recent agent messages, newest first."""
        rows = self._conn.execute(
            "SELECT id, from_agent, to_agent, content, msg_type, timestamp, status "
            "FROM agent_messages ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def update_message_status(self, msg_id: str, status: str):
        """Update message status."""
        with self._tx():
            self._conn.execute(
                "UPDATE agent_messages SET status=? WHERE id=?",
                (status, msg_id))

    def cleanup_old_messages(self, max_age_days: int = 30):
        """Delete messages older than max_age_days."""
        cutoff = time.time() - (max_age_days * 86400)
        with self._tx():
            self._conn.execute(
                "DELETE FROM agent_messages WHERE timestamp < ?", (cutoff,))

    # ==================================================================
    # JSON → SQLite 自动迁移
    # ==================================================================

    def migrate_from_json(self):
        """从现有 JSON 文件导入数据到 SQLite（仅在表为空时执行）。"""
        imported = []

        # agents.json
        imported += self._migrate_json_file(
            os.path.join(self._data_dir, "agents.json"),
            "agents", "agent_id",
            list_key="agents",
            pk_field=lambda d: d.get("id", d.get("agent_id", "")),
            columns_fn=lambda d: {
                "name": d.get("name", ""),
                "role": d.get("role", ""),
                "status": d.get("status", "idle"),
                "node_id": d.get("node_id", "local"),
            },
        )

        # nodes.json
        imported += self._migrate_json_file(
            os.path.join(self._data_dir, "nodes.json"),
            "nodes", "node_id",
            list_key="nodes",
            pk_field=lambda d: d.get("node_id", ""),
            columns_fn=lambda d: {
                "name": d.get("name", ""),
                "url": d.get("url", ""),
                "status": d.get("status", "unknown"),
                "last_seen": d.get("last_seen", 0),
            },
        )

        # node_configs.json
        nc_path = os.path.join(self._data_dir, "node_configs.json")
        if os.path.isfile(nc_path) and self.count("node_configs") == 0:
            try:
                with open(nc_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                configs = data.get("configs", []) if isinstance(data, dict) else data
                for c in configs:
                    self.save_node_config(
                        c.get("node_id", ""),
                        c.get("key", ""),
                        c.get("value", ""),
                        c.get("category", ""),
                        c.get("is_secret", False),
                        c,
                    )
                imported.append(f"node_configs: {len(configs)}")
            except Exception as e:
                logger.warning("migrate node_configs failed: %s", e)

        # projects.json
        imported += self._migrate_json_file(
            os.path.join(self._data_dir, "projects.json"),
            "projects", "project_id",
            list_key="projects",
            pk_field=lambda d: d.get("id", d.get("project_id", "")),
            columns_fn=lambda d: {
                "name": d.get("name", ""),
                "status": d.get("status", "active"),
            },
        )

        # channels.json
        imported += self._migrate_json_file(
            os.path.join(self._data_dir, "channels.json"),
            "channels", "channel_id",
            list_key="channels",
            pk_field=lambda d: d.get("id", d.get("channel_id", "")),
            columns_fn=lambda d: {
                "name": d.get("name", ""),
                "type": d.get("type", ""),
            },
        )

        # workflows.json
        wf_path = os.path.join(self._data_dir, "workflows.json")
        if os.path.isfile(wf_path):
            try:
                with open(wf_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # templates
                tpls = data.get("templates", {})
                if isinstance(tpls, dict) and self.count("workflow_templates") == 0:
                    for tid, tdata in tpls.items():
                        tdata.setdefault("template_id", tid)
                        self.save_workflow_template(tdata)
                    imported.append(f"workflow_templates: {len(tpls)}")
                # instances
                insts = data.get("instances", {})
                if isinstance(insts, dict) and self.count("workflow_instances") == 0:
                    for iid, idata in insts.items():
                        idata.setdefault("instance_id", iid)
                        self.save_workflow_instance(idata)
                    imported.append(f"workflow_instances: {len(insts)}")
            except Exception as e:
                logger.warning("migrate workflows failed: %s", e)

        # .tudou_admins.json
        imported += self._migrate_json_file(
            os.path.join(self._data_dir, ".tudou_admins.json"),
            "admins", "username",
            list_key="admins",
            pk_field=lambda d: d.get("username", ""),
            columns_fn=lambda d: {
                "role": d.get("role", "admin"),
            },
        )

        # .tudou_tokens.json
        imported += self._migrate_json_file(
            os.path.join(self._data_dir, ".tudou_tokens.json"),
            "tokens", "token_id",
            list_key="tokens",
            pk_field=lambda d: d.get("id", d.get("token_id", "")),
            columns_fn=lambda d: {
                "name": d.get("name", ""),
                "admin": d.get("admin", ""),
                "role": d.get("role", ""),
                "active": 1 if d.get("active", True) else 0,
            },
        )

        # providers.json
        imported += self._migrate_json_file(
            os.path.join(self._data_dir, "providers.json"),
            "providers", "provider_id",
            list_key="providers",
            pk_field=lambda d: d.get("id", d.get("provider_id", "")),
            columns_fn=lambda d: {
                "name": d.get("name", ""),
            },
        )

        # scheduled_jobs.json
        imported += self._migrate_json_file(
            os.path.join(self._data_dir, "scheduled_jobs.json"),
            "scheduled_jobs", "job_id",
            list_key="jobs",
            pk_field=lambda d: d.get("id", d.get("job_id", "")),
            columns_fn=lambda d: {
                "name": d.get("name", ""),
                "type": d.get("type", ""),
                "cron": d.get("cron", d.get("cron_expr", "")),
                "enabled": 1 if d.get("enabled", True) else 0,
            },
        )

        # mcp_configs.json
        # NOTE: JSON schema is {"node_configs": {node_id: NodeMCPConfig.to_dict()}}.
        # The real MCP server entries live at
        # node_configs[node_id]["available_mcps"][mcp_id]. An earlier version
        # of this migration iterated NodeMCPConfig's top-level keys as if
        # they were mcp ids, producing garbage rows like
        # (local, "available_mcps", "{}") / (local, "agent_bindings", "{}")
        # which then corrupted the _load path. Only real MCP rows are
        # migrated here.
        mcp_path = os.path.join(self._data_dir, "mcp_configs.json")
        if os.path.isfile(mcp_path) and self.count("mcp_configs") == 0:
            try:
                with open(mcp_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                node_cfgs = data.get("node_configs", data)
                if isinstance(node_cfgs, dict):
                    cnt = 0
                    for nid, node_cfg in node_cfgs.items():
                        if not isinstance(node_cfg, dict):
                            continue
                        available = node_cfg.get("available_mcps", {}) or {}
                        if not isinstance(available, dict):
                            continue
                        for mid, cfg in available.items():
                            if not isinstance(cfg, dict):
                                continue
                            self.save_mcp_config(nid, mid, cfg)
                            cnt += 1
                    imported.append(f"mcp_configs: {cnt}")
            except Exception as e:
                logger.warning("migrate mcp_configs failed: %s", e)

        if imported:
            logger.info("JSON → SQLite migration complete: %s",
                        ", ".join(imported))
        return imported

    def _migrate_json_file(self, path: str, table: str, pk_col: str,
                           list_key: str,
                           pk_field, columns_fn) -> list[str]:
        """通用 JSON 列表文件迁移助手。"""
        if not os.path.isfile(path):
            return []
        if self.count(table) > 0:
            return []  # 表已有数据，跳过
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            items = raw.get(list_key, []) if isinstance(raw, dict) else raw
            if not isinstance(items, list):
                return []
            for item in items:
                pk_val = pk_field(item) if callable(pk_field) else item.get(pk_field, "")
                if not pk_val:
                    continue
                cols = columns_fn(item) if callable(columns_fn) else {}
                self.upsert(table, pk_col, pk_val, columns=cols, data=item)
            return [f"{table}: {len(items)}"]
        except Exception as e:
            logger.warning("migrate %s failed: %s", path, e)
            return []

    # ==================================================================
    # Cleanup
    # ==================================================================

    def close(self):
        """关闭数据库连接。"""
        try:
            self._conn.close()
        except Exception:
            pass

    def vacuum(self):
        """压缩数据库文件。"""
        self._conn.execute("VACUUM")
