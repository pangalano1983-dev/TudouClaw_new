"""SQLite-backed persistence for decomposition drafts.

Owns the ``long_task_drafts`` table in ``~/.tudou_claw/tudou_claw.db``.
Schema is created idempotently on first access (``CREATE TABLE IF NOT
EXISTS``) — no separate migration step required.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

from .models import Draft, DraftStatus

logger = logging.getLogger("tudouclaw.long_task.draft_store")

# DB file is the same one the rest of TudouClaw uses; we get our own
# table inside it so backups / migrations cover this data automatically.
_DB_PATH = Path(os.environ.get(
    "TUDOU_CLAW_DB",
    str(Path.home() / ".tudou_claw" / "tudou_claw.db"),
))


_SCHEMA = """
CREATE TABLE IF NOT EXISTS long_task_drafts (
    id                     TEXT PRIMARY KEY,
    project_id             TEXT NOT NULL,
    parent_task_id         TEXT NOT NULL,
    proposed_by_agent_id   TEXT NOT NULL,
    title                  TEXT NOT NULL,
    summary                TEXT NOT NULL,
    prd                    TEXT NOT NULL DEFAULT '',
    prd_source             TEXT NOT NULL DEFAULT 'agent_generated',
    status                 TEXT NOT NULL DEFAULT 'pending',
    created_at             REAL NOT NULL,
    confirmed_at           REAL NOT NULL DEFAULT 0,
    cancelled_at           REAL NOT NULL DEFAULT 0,
    materialized_task_ids  TEXT NOT NULL DEFAULT '[]',  -- JSON array
    user_overrides         TEXT NOT NULL DEFAULT '{}',  -- JSON object
    scaffold_dirs          TEXT NOT NULL DEFAULT '[]',  -- JSON array
    sub_tasks              TEXT NOT NULL DEFAULT '[]'   -- JSON array of SubTaskSpec
);

-- Common queries: by project + status, and by parent_task_id.
CREATE INDEX IF NOT EXISTS idx_ltd_project_status
  ON long_task_drafts (project_id, status);
CREATE INDEX IF NOT EXISTS idx_ltd_parent_task
  ON long_task_drafts (parent_task_id);
"""


class DraftStore:
    """Thread-safe access to ``long_task_drafts``.

    Wraps a single sqlite connection with a re-entrant lock — same
    pattern used by ``app/core/memory.py``. Connection is shared across
    callers; sqlite handles concurrent reads, write-coordination is via
    ``self._lock``.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self._path = db_path or _DB_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: we serialize writes through the lock
        # and FastAPI runs handlers across worker threads.
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    # ── Writes ────────────────────────────────────────────────────────

    def save(self, draft: Draft) -> Draft:
        """Insert-or-replace by id. Updates ``confirmed_at`` /
        ``cancelled_at`` automatically when status transitions."""
        if draft.status == DraftStatus.CONFIRMED and not draft.confirmed_at:
            draft.confirmed_at = time.time()
        if draft.status == DraftStatus.CANCELLED and not draft.cancelled_at:
            draft.cancelled_at = time.time()
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO long_task_drafts
                  (id, project_id, parent_task_id, proposed_by_agent_id,
                   title, summary, prd, prd_source, status,
                   created_at, confirmed_at, cancelled_at,
                   materialized_task_ids, user_overrides,
                   scaffold_dirs, sub_tasks)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    draft.id, draft.project_id, draft.parent_task_id,
                    draft.proposed_by_agent_id,
                    draft.title, draft.summary, draft.prd, draft.prd_source,
                    draft.status.value,
                    draft.created_at, draft.confirmed_at, draft.cancelled_at,
                    json.dumps(draft.materialized_task_ids),
                    json.dumps(draft.user_overrides),
                    json.dumps(draft.scaffold_dirs),
                    json.dumps([s.to_dict() for s in draft.sub_tasks]),
                ),
            )
            self._conn.commit()
        logger.debug("DraftStore.save id=%s status=%s",
                     draft.id, draft.status.value)
        return draft

    def delete(self, draft_id: str) -> bool:
        """Hard-delete a draft. Returns True if a row was removed."""
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM long_task_drafts WHERE id=?", (draft_id,))
            self._conn.commit()
            return cur.rowcount > 0

    # ── Reads ─────────────────────────────────────────────────────────

    def get(self, draft_id: str) -> Optional[Draft]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM long_task_drafts WHERE id=?",
                (draft_id,),
            ).fetchone()
        return self._row_to_draft(row) if row else None

    def list_for_project(self, project_id: str,
                         status: Optional[DraftStatus] = None,
                         ) -> list[Draft]:
        with self._lock:
            if status is None:
                rows = self._conn.execute(
                    "SELECT * FROM long_task_drafts WHERE project_id=? "
                    "ORDER BY created_at DESC",
                    (project_id,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM long_task_drafts WHERE project_id=? "
                    "AND status=? ORDER BY created_at DESC",
                    (project_id, status.value),
                ).fetchall()
        return [self._row_to_draft(r) for r in rows if r]

    def list_pending(self, max_age_s: float = 0) -> list[Draft]:
        """All drafts in PENDING status. ``max_age_s`` > 0 filters to
        drafts older than that many seconds (used by the expirer)."""
        with self._lock:
            if max_age_s > 0:
                cutoff = time.time() - max_age_s
                rows = self._conn.execute(
                    "SELECT * FROM long_task_drafts WHERE status='pending' "
                    "AND created_at < ? ORDER BY created_at ASC",
                    (cutoff,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM long_task_drafts WHERE status='pending' "
                    "ORDER BY created_at DESC",
                ).fetchall()
        return [self._row_to_draft(r) for r in rows if r]

    # ── Internal ──────────────────────────────────────────────────────

    @staticmethod
    def _row_to_draft(row: sqlite3.Row) -> Draft:
        d = dict(row)
        d["materialized_task_ids"] = json.loads(d.get("materialized_task_ids") or "[]")
        d["user_overrides"] = json.loads(d.get("user_overrides") or "{}")
        d["scaffold_dirs"] = json.loads(d.get("scaffold_dirs") or "[]")
        d["sub_tasks"] = json.loads(d.get("sub_tasks") or "[]")
        return Draft.from_dict(d)


# ── Module-level singleton ────────────────────────────────────────────
# Match the pattern used by app.core.memory — one shared store per
# process, lazily created on first call.

_singleton: Optional[DraftStore] = None
_singleton_lock = threading.Lock()


def get_draft_store() -> DraftStore:
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                _singleton = DraftStore()
    return _singleton
