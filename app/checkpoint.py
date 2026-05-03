"""Block 3 — Checkpoint store.

Lets a long-running agent / meeting / project task be serialized at an
arbitrary moment (abort, scheduled pause, manual snapshot) so it can be
resumed later with minimal token cost.

A checkpoint captures:
  * plan_json      — ExecutionPlan.to_dict() at snapshot time
  * artifact_refs  — pointers to files/values produced so far (NOT payloads —
                     the actual content lives in ArtifactStore)
  * chat_tail      — the last N chat messages for continuity
  * digest         — optional LLM-compressed history (populated later in
                     Block 3 Day 4-5)
  * reason         — why we snapshotted (user_abort / system_pause / ...)
  * metadata       — scope-specific extras (meeting_id, project_id, ...)

Design constraints:
  * Additive to existing data paths — nothing in agent.py / meeting.py /
    project.py is forced through the checkpoint store in Day 1-2.
  * SQLite (WAL) mirrors the inbox store pattern so ops complexity stays flat.
  * Checkpoints are mostly-immutable: save once, then only status
    transitions (open → restored → archived).
  * No payload inlining; we quote refs so a 200MB PDF artifact doesn't
    bloat the DB.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


# Scope constants — string literals intentionally, to keep the store
# decoupled from the agent/meeting/project class hierarchies.
SCOPE_AGENT = "agent"
SCOPE_MEETING = "meeting"
SCOPE_PROJECT_TASK = "project_task"
_VALID_SCOPES = (SCOPE_AGENT, SCOPE_MEETING, SCOPE_PROJECT_TASK)

# Reason taxonomy — open set, but these are the documented values.
REASON_USER_ABORT = "user_abort"
REASON_SYSTEM_PAUSE = "system_pause"
REASON_SCHEDULED = "scheduled"
REASON_MANUAL = "manual"
REASON_ERROR = "error"

STATUS_OPEN = "open"           # just saved, can be resumed
STATUS_RESTORED = "restored"   # resumed at least once
STATUS_ARCHIVED = "archived"   # user / gc said "done, don't show"


# ── Data model ──────────────────────────────────────────────────────


@dataclass
class AgentCheckpoint:
    id: str = ""
    agent_id: str = ""
    scope: str = SCOPE_AGENT          # agent | meeting | project_task
    scope_id: str = ""                # meeting_id / project_task_id / "" for agent scope
    created_at: float = 0.0
    reason: str = REASON_MANUAL

    plan_json: dict = field(default_factory=dict)      # ExecutionPlan.to_dict()
    artifact_refs: list[dict] = field(default_factory=list)  # [{id, kind, path, ...}]
    chat_tail: list[dict] = field(default_factory=list)      # [{role, content, source, ts}]

    digest: str = ""                  # populated later (Block 3 Day 4-5)
    metadata: dict = field(default_factory=dict)

    status: str = STATUS_OPEN
    restored_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "scope": self.scope,
            "scope_id": self.scope_id,
            "created_at": self.created_at,
            "reason": self.reason,
            "plan_json": dict(self.plan_json or {}),
            "artifact_refs": list(self.artifact_refs or []),
            "chat_tail": list(self.chat_tail or []),
            "digest": self.digest,
            "metadata": dict(self.metadata or {}),
            "status": self.status,
            "restored_at": self.restored_at,
        }

    @staticmethod
    def from_row(row: sqlite3.Row) -> "AgentCheckpoint":
        def _load(s: str, default):
            if not s:
                return default
            try:
                return json.loads(s)
            except Exception:
                return default
        return AgentCheckpoint(
            id=row["id"],
            agent_id=row["agent_id"],
            scope=row["scope"],
            scope_id=row["scope_id"] or "",
            created_at=row["created_at"],
            reason=row["reason"] or REASON_MANUAL,
            plan_json=_load(row["plan_json"], {}),
            artifact_refs=_load(row["artifact_refs"], []),
            chat_tail=_load(row["chat_tail"], []),
            digest=row["digest"] or "",
            metadata=_load(row["metadata"], {}),
            status=row["status"] or STATUS_OPEN,
            restored_at=row["restored_at"] or 0.0,
        )


# ── Schema ──────────────────────────────────────────────────────────


_SCHEMA = """
CREATE TABLE IF NOT EXISTS checkpoints (
    id              TEXT PRIMARY KEY,
    agent_id        TEXT NOT NULL,
    scope           TEXT NOT NULL,
    scope_id        TEXT NOT NULL DEFAULT '',
    created_at      REAL NOT NULL,
    reason          TEXT NOT NULL DEFAULT '',
    plan_json       TEXT NOT NULL DEFAULT '',
    artifact_refs   TEXT NOT NULL DEFAULT '',
    chat_tail       TEXT NOT NULL DEFAULT '',
    digest          TEXT NOT NULL DEFAULT '',
    metadata        TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'open',
    restored_at     REAL NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_ckpt_agent
    ON checkpoints(agent_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ckpt_scope
    ON checkpoints(scope, scope_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ckpt_created
    ON checkpoints(created_at DESC);
"""


# ── Store ───────────────────────────────────────────────────────────


class CheckpointStore:
    """Thread-safe SQLite-backed checkpoint store."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            db_path, check_same_thread=False,
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(_SCHEMA)

    # ── write ──

    def save(self, *,
             agent_id: str,
             plan_json: Optional[dict] = None,
             scope: str = SCOPE_AGENT,
             scope_id: str = "",
             reason: str = REASON_MANUAL,
             artifact_refs: Optional[list[dict]] = None,
             chat_tail: Optional[list[dict]] = None,
             digest: str = "",
             metadata: Optional[dict] = None) -> str:
        """Persist a new checkpoint. Returns the new id."""
        if not agent_id:
            raise ValueError("agent_id is required")
        if scope not in _VALID_SCOPES:
            raise ValueError(f"invalid scope: {scope!r}")

        cid = f"ckpt_{uuid.uuid4().hex[:14]}"
        now = time.time()
        row = (
            cid, agent_id, scope, scope_id or "", now, reason or REASON_MANUAL,
            json.dumps(plan_json or {}, ensure_ascii=False, default=str),
            json.dumps(artifact_refs or [], ensure_ascii=False, default=str),
            json.dumps(chat_tail or [], ensure_ascii=False, default=str),
            digest or "",
            json.dumps(metadata or {}, ensure_ascii=False, default=str),
            STATUS_OPEN, 0.0,
        )
        with self._lock:
            self._conn.execute(
                "INSERT INTO checkpoints(id, agent_id, scope, scope_id, "
                "created_at, reason, plan_json, artifact_refs, chat_tail, "
                "digest, metadata, status, restored_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                row,
            )
            self._conn.commit()
        return cid

    def mark_restored(self, checkpoint_id: str) -> bool:
        """Flip status to `restored` + set restored_at."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE checkpoints SET status=?, restored_at=? WHERE id=?",
                (STATUS_RESTORED, time.time(), checkpoint_id),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def archive(self, checkpoint_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE checkpoints SET status=? WHERE id=?",
                (STATUS_ARCHIVED, checkpoint_id),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def update_digest(self, checkpoint_id: str, digest: str) -> bool:
        """Set/replace the digest text. Used by Block 3 Day 4-5."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE checkpoints SET digest=? WHERE id=?",
                (digest or "", checkpoint_id),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def set_metadata_flag(self, checkpoint_id: str,
                          flag: str, value: Any) -> bool:
        """Merge a single key into the row's metadata JSON (load → set → save).

        Used by Day 8 to mark `pending_chat_delivery=True` on restore, and by
        the agent chat loop to flip it back to False after consumption.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT metadata FROM checkpoints WHERE id=?",
                (checkpoint_id,),
            ).fetchone()
            if row is None:
                return False
            try:
                current = json.loads(row["metadata"] or "{}") or {}
            except Exception:
                current = {}
            current[flag] = value
            self._conn.execute(
                "UPDATE checkpoints SET metadata=? WHERE id=?",
                (json.dumps(current, ensure_ascii=False, default=str),
                 checkpoint_id),
            )
            self._conn.commit()
        return True

    def consume_pending_resume(self,
                               agent_id: str) -> Optional[AgentCheckpoint]:
        """Atomic read-and-clear for the resume delivery mechanism.

        Finds the most recent checkpoint where:
          - agent_id matches
          - status is `restored`
          - metadata.pending_chat_delivery is truthy

        Flips the flag to False and returns the checkpoint. Returns None
        if no pending resume is queued. Called at the start of each chat
        turn so the digest gets delivered exactly once.
        """
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM checkpoints WHERE agent_id=? AND status=? "
                "ORDER BY created_at DESC LIMIT 20",
                (agent_id, STATUS_RESTORED),
            ).fetchall()
            for row in rows:
                try:
                    md = json.loads(row["metadata"] or "{}") or {}
                except Exception:
                    md = {}
                if md.get("pending_chat_delivery"):
                    # Flip the flag atomically.
                    md["pending_chat_delivery"] = False
                    md["delivered_at"] = time.time()
                    self._conn.execute(
                        "UPDATE checkpoints SET metadata=? WHERE id=?",
                        (json.dumps(md, ensure_ascii=False, default=str),
                         row["id"]),
                    )
                    self._conn.commit()
                    # Re-select the row with the fresh metadata.
                    refreshed = self._conn.execute(
                        "SELECT * FROM checkpoints WHERE id=?",
                        (row["id"],),
                    ).fetchone()
                    return AgentCheckpoint.from_row(refreshed)
        return None

    # ── read ──

    def load(self, checkpoint_id: str) -> Optional[AgentCheckpoint]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM checkpoints WHERE id=?",
                (checkpoint_id,),
            ).fetchone()
        return AgentCheckpoint.from_row(row) if row else None

    def list_for_agent(self, agent_id: str, *,
                       status: Optional[str] = None,
                       scope: Optional[str] = None,
                       limit: int = 50) -> list[AgentCheckpoint]:
        sql = "SELECT * FROM checkpoints WHERE agent_id=?"
        params: list[Any] = [agent_id]
        if status:
            sql += " AND status=?"; params.append(status)
        if scope:
            sql += " AND scope=?"; params.append(scope)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        with self._lock:
            rows = self._conn.execute(sql, tuple(params)).fetchall()
        return [AgentCheckpoint.from_row(r) for r in rows]

    def list_for_scope(self, scope: str, scope_id: str, *,
                       status: Optional[str] = None,
                       limit: int = 50) -> list[AgentCheckpoint]:
        if scope not in _VALID_SCOPES:
            raise ValueError(f"invalid scope: {scope!r}")
        sql = "SELECT * FROM checkpoints WHERE scope=? AND scope_id=?"
        params: list[Any] = [scope, scope_id]
        if status:
            sql += " AND status=?"; params.append(status)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        with self._lock:
            rows = self._conn.execute(sql, tuple(params)).fetchall()
        return [AgentCheckpoint.from_row(r) for r in rows]

    def latest_open_for_scope(self, scope: str,
                              scope_id: str) -> Optional[AgentCheckpoint]:
        """Return the most recent OPEN checkpoint for a given scope —
        the canonical "what should we resume?" lookup."""
        lst = self.list_for_scope(scope, scope_id,
                                  status=STATUS_OPEN, limit=1)
        return lst[0] if lst else None

    # ── maintenance ──

    def prune_older_than(self, cutoff_s: float,
                         only_archived: bool = True) -> int:
        """Delete checkpoints older than cutoff. By default only touches
        archived ones to avoid blowing away something a user might still
        restore."""
        sql = "DELETE FROM checkpoints WHERE created_at < ?"
        params: list[Any] = [float(cutoff_s)]
        if only_archived:
            sql += " AND status=?"; params.append(STATUS_ARCHIVED)
        with self._lock:
            cur = self._conn.execute(sql, tuple(params))
            self._conn.commit()
            return cur.rowcount

    def stats(self) -> dict:
        with self._lock:
            total = self._conn.execute(
                "SELECT COUNT(*) FROM checkpoints").fetchone()[0]
            by_status: dict[str, int] = {}
            for row in self._conn.execute(
                "SELECT status, COUNT(*) c FROM checkpoints GROUP BY status"
            ):
                by_status[row["status"]] = row["c"]
            by_scope: dict[str, int] = {}
            for row in self._conn.execute(
                "SELECT scope, COUNT(*) c FROM checkpoints GROUP BY scope"
            ):
                by_scope[row["scope"]] = row["c"]
        return {
            "total": total,
            "by_status": by_status,
            "by_scope": by_scope,
            "db_path": self._db_path,
        }


# ── Singleton ───────────────────────────────────────────────────────


_STORE: Optional[CheckpointStore] = None
_STORE_LOCK = threading.Lock()


def _default_db_path() -> str:
    from .paths import data_dir
    return str(data_dir() / "checkpoints.db")


def get_store(db_path: Optional[str] = None) -> CheckpointStore:
    """Return (or lazily create) the process-wide singleton."""
    global _STORE
    if _STORE is not None and db_path is None:
        return _STORE
    with _STORE_LOCK:
        if _STORE is None or db_path is not None:
            path = db_path or _default_db_path()
            _STORE = CheckpointStore(path)
        return _STORE


def reset_store_for_test() -> None:
    """Force the singleton off so the next get_store() rebuilds. Test-only."""
    global _STORE
    with _STORE_LOCK:
        if _STORE is not None:
            try:
                _STORE._conn.close()
            except Exception:
                pass
        _STORE = None


# ── High-level helpers used by abort paths ──────────────────────────


def save_for_abort(*,
                   agent_id: str,
                   plan_json: Optional[dict] = None,
                   scope: str = SCOPE_AGENT,
                   scope_id: str = "",
                   reason: str = REASON_USER_ABORT,
                   artifact_refs: Optional[list[dict]] = None,
                   chat_tail: Optional[list[dict]] = None,
                   metadata: Optional[dict] = None,
                   emit_frame: bool = True) -> str:
    """Persist a checkpoint AND emit a `checkpoint_created` frame to the
    ProgressBus so the portal UI can surface it.

    Never raises — persistence failures log and return "" so the abort
    path can still proceed.
    """
    try:
        store = get_store()
        cid = store.save(
            agent_id=agent_id or "unknown",
            plan_json=plan_json or {},
            scope=scope,
            scope_id=scope_id or "",
            reason=reason or REASON_USER_ABORT,
            artifact_refs=artifact_refs or [],
            chat_tail=chat_tail or [],
            metadata=metadata or {},
        )
    except Exception as e:
        import logging as _lg
        _lg.getLogger("tudou.checkpoint").warning(
            "save_for_abort failed (%s): %s", scope, e,
        )
        return ""

    if emit_frame and cid:
        try:
            from .progress_bus import get_bus, ProgressFrame
            bus = get_bus()
            channel = f"{scope}:{scope_id or agent_id}"
            bus.publish(ProgressFrame(
                kind="checkpoint_created",
                channel=channel,
                agent_id=agent_id or "",
                data={
                    "checkpoint_id": cid,
                    "scope": scope,
                    "scope_id": scope_id,
                    "reason": reason,
                },
            ))
        except Exception:
            # Progress bus is optional; never block abort on it.
            pass

    return cid
