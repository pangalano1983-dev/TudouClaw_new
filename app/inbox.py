"""Block 0 — persistent per-agent inbox.

The old `send_message` tool was fire-and-forget: A's message to B
got stuffed into B's next prompt only if B happened to be actively
chatting. Cross-time collaboration (DBA agent wakes at 3am to do DB
cutover, main agent follows up next day) was impossible — messages
sent to a sleeping agent just evaporated.

This module gives every agent a persistent SQLite-backed inbox with:

  - Delivery guarantee across server restart
  - ACK semantics (sender knows recipient saw it)
  - Thread IDs for reply chains
  - Priority (urgent / normal / low) for ordering
  - TTL for auto-expiry
  - Safe concurrent access via SQLite's WAL mode

API (thread-safe singleton via get_store()):

  store.send(to_agent, from_agent, content, ...) -> msg_id
  store.fetch_unread(agent_id, limit=50, since_id=None) -> list[InboxMessage]
  store.mark_read(msg_ids, reader_agent_id) -> count
  store.mark_acked(msg_ids, reader_agent_id) -> count
  store.get_thread(thread_id) -> list[InboxMessage]
  store.get_by_id(msg_id) -> InboxMessage | None
  store.stats() -> dict
  store.cleanup_expired() -> count   # call periodically to enforce TTL

Not goals (leave for later):
  - Presence ("is agent B online right now")
  - Multi-recipient fan-out (send to multiple at once)
  - End-to-end encryption
  - Server clustering (single-node SQLite is fine for now)
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger("tudou.inbox")


# ─── Data model ────────────────────────────────────────────────────

@dataclass
class InboxMessage:
    id: str
    to_agent: str              # recipient agent id (or "user", "system")
    from_agent: str            # sender agent id (or "user", "system")
    content: str               # message body
    thread_id: str = ""        # correlation id for reply chains
    reply_to: str = ""         # msg_id this is a reply to
    priority: str = "normal"   # urgent | normal | low
    state: str = "new"         # new | read | acked | expired
    created_at: float = field(default_factory=time.time)
    read_at: float = 0.0       # when recipient first fetched it
    acked_at: float = 0.0      # when recipient explicitly ack'd
    ttl_s: float = 0.0         # 0 = no expiry; else expires at created_at + ttl_s
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["metadata"] = dict(self.metadata)
        return d

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "InboxMessage":
        md_raw = row["metadata"] or ""
        try:
            md = json.loads(md_raw) if md_raw else {}
        except Exception:
            md = {}
        return cls(
            id=row["id"], to_agent=row["to_agent"],
            from_agent=row["from_agent"], content=row["content"] or "",
            thread_id=row["thread_id"] or "",
            reply_to=row["reply_to"] or "",
            priority=row["priority"] or "normal",
            state=row["state"] or "new",
            created_at=row["created_at"] or 0.0,
            read_at=row["read_at"] or 0.0,
            acked_at=row["acked_at"] or 0.0,
            ttl_s=row["ttl_s"] or 0.0,
            metadata=md,
        )

    @property
    def is_expired(self) -> bool:
        if self.ttl_s <= 0:
            return False
        return time.time() > self.created_at + self.ttl_s


# ─── SQLite store ──────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS inbox_messages (
    id          TEXT PRIMARY KEY,
    to_agent    TEXT NOT NULL,
    from_agent  TEXT NOT NULL,
    content     TEXT NOT NULL,
    thread_id   TEXT NOT NULL DEFAULT '',
    reply_to    TEXT NOT NULL DEFAULT '',
    priority    TEXT NOT NULL DEFAULT 'normal',
    state       TEXT NOT NULL DEFAULT 'new',
    created_at  REAL NOT NULL,
    read_at     REAL NOT NULL DEFAULT 0,
    acked_at    REAL NOT NULL DEFAULT 0,
    ttl_s       REAL NOT NULL DEFAULT 0,
    metadata    TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_inbox_to_state
    ON inbox_messages (to_agent, state, created_at);

CREATE INDEX IF NOT EXISTS idx_inbox_thread
    ON inbox_messages (thread_id);

CREATE INDEX IF NOT EXISTS idx_inbox_created
    ON inbox_messages (created_at);
"""

_PRIORITY_ORDER = {"urgent": 0, "normal": 1, "low": 2}


class InboxStore:
    """SQLite-backed inbox. One instance per process; all methods
    thread-safe (single connection + lock)."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._lock = threading.RLock()
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        # check_same_thread=False: we're guarded by our own lock, so SQLite's
        # thread-restriction is redundant and prevents multithreaded agents
        # from sharing the connection.
        self._conn = sqlite3.connect(db_path, check_same_thread=False,
                                       isolation_level=None)  # autocommit
        self._conn.row_factory = sqlite3.Row
        # WAL for better concurrent readers; synchronous=NORMAL balances
        # durability against throughput (we accept losing last ~sec on crash).
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(_SCHEMA)

    # ── send ──────────────────────────────────────────────────────

    def send(self, *, to_agent: str, from_agent: str, content: str,
              thread_id: str = "", reply_to: str = "",
              priority: str = "normal", ttl_s: float = 0.0,
              metadata: Optional[dict] = None) -> str:
        """Persist a message. Returns msg_id.

        - to_agent / from_agent / content must be non-empty
        - priority must be one of urgent/normal/low (bad values silently
          coerced to normal rather than rejecting — tool callers get
          lenient handling)
        - thread_id defaults to this msg's own id if empty (every msg
          starts its own thread unless explicitly continuing one)
        """
        if not to_agent or not from_agent or not content:
            raise ValueError(
                f"send() requires to_agent/from_agent/content (got "
                f"to={to_agent!r} from={from_agent!r} content_len={len(content or '')})"
            )
        if priority not in _PRIORITY_ORDER:
            priority = "normal"
        msg_id = f"msg_{uuid.uuid4().hex[:12]}"
        if not thread_id:
            thread_id = msg_id  # self-rooted thread
        md_json = json.dumps(metadata or {}, ensure_ascii=False, default=str)

        with self._lock:
            self._conn.execute(
                """INSERT INTO inbox_messages
                   (id, to_agent, from_agent, content, thread_id, reply_to,
                    priority, state, created_at, read_at, acked_at,
                    ttl_s, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'new', ?, 0, 0, ?, ?)""",
                (msg_id, to_agent, from_agent, content, thread_id, reply_to,
                 priority, time.time(), float(ttl_s or 0.0), md_json),
            )
        logger.debug("inbox: sent %s (%s → %s, prio=%s)",
                      msg_id, from_agent, to_agent, priority)
        return msg_id

    # ── fetch ─────────────────────────────────────────────────────

    def fetch_unread(self, agent_id: str, *, limit: int = 50,
                      since_id: Optional[str] = None) -> list[InboxMessage]:
        """Return messages for `agent_id` in state=new, priority-ordered
        then oldest-first within each priority. `since_id` is a pagination
        hint — returns messages created after that one (by created_at)."""
        limit = max(1, min(int(limit), 500))
        with self._lock:
            since_ts = 0.0
            if since_id:
                row = self._conn.execute(
                    "SELECT created_at FROM inbox_messages WHERE id=?",
                    (since_id,),
                ).fetchone()
                if row:
                    since_ts = row["created_at"]
            # Filter out expired messages. We use a subquery so expiry
            # detection is consistent with what cleanup_expired() would do.
            now = time.time()
            rows = self._conn.execute(
                """SELECT * FROM inbox_messages
                   WHERE to_agent = ?
                     AND state = 'new'
                     AND created_at > ?
                     AND (ttl_s = 0 OR created_at + ttl_s > ?)
                   ORDER BY
                       CASE priority
                           WHEN 'urgent' THEN 0
                           WHEN 'normal' THEN 1
                           WHEN 'low' THEN 2
                           ELSE 3
                       END,
                       created_at ASC
                   LIMIT ?""",
                (agent_id, since_ts, now, limit),
            ).fetchall()
            return [InboxMessage.from_row(r) for r in rows]

    def unread_count(self, agent_id: str) -> int:
        now = time.time()
        with self._lock:
            row = self._conn.execute(
                """SELECT COUNT(*) AS c FROM inbox_messages
                   WHERE to_agent = ? AND state = 'new'
                     AND (ttl_s = 0 OR created_at + ttl_s > ?)""",
                (agent_id, now),
            ).fetchone()
            return int(row["c"] or 0)

    def get_by_id(self, msg_id: str) -> Optional[InboxMessage]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM inbox_messages WHERE id=?", (msg_id,),
            ).fetchone()
            return InboxMessage.from_row(row) if row else None

    def get_thread(self, thread_id: str, *,
                    limit: int = 100) -> list[InboxMessage]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT * FROM inbox_messages
                   WHERE thread_id = ?
                   ORDER BY created_at ASC
                   LIMIT ?""",
                (thread_id, int(limit)),
            ).fetchall()
            return [InboxMessage.from_row(r) for r in rows]

    # ── mutations ─────────────────────────────────────────────────

    def mark_read(self, msg_ids: list[str],
                   reader_agent_id: str) -> int:
        """Move matching messages from 'new' → 'read'. Only affects
        messages actually addressed to reader_agent_id — protects
        against agent A mistakenly marking B's messages read.

        Returns number of rows updated.
        """
        if not msg_ids:
            return 0
        with self._lock:
            now = time.time()
            placeholders = ",".join("?" * len(msg_ids))
            cur = self._conn.execute(
                f"""UPDATE inbox_messages
                    SET state = 'read', read_at = ?
                    WHERE id IN ({placeholders})
                      AND to_agent = ?
                      AND state = 'new'""",
                [now] + list(msg_ids) + [reader_agent_id],
            )
            return cur.rowcount

    def mark_acked(self, msg_ids: list[str],
                    reader_agent_id: str) -> int:
        """Move matching messages to 'acked' state (from new or read).
        Implies read — sets read_at if not already set."""
        if not msg_ids:
            return 0
        with self._lock:
            now = time.time()
            placeholders = ",".join("?" * len(msg_ids))
            cur = self._conn.execute(
                f"""UPDATE inbox_messages
                    SET state = 'acked',
                        acked_at = ?,
                        read_at = CASE WHEN read_at = 0 THEN ? ELSE read_at END
                    WHERE id IN ({placeholders})
                      AND to_agent = ?
                      AND state IN ('new', 'read')""",
                [now, now] + list(msg_ids) + [reader_agent_id],
            )
            return cur.rowcount

    def cleanup_expired(self) -> int:
        """Move past-TTL messages into state='expired'. Call from a
        periodic watchdog — does NOT run automatically on each operation
        (would be wasted work on the hot path)."""
        with self._lock:
            now = time.time()
            cur = self._conn.execute(
                """UPDATE inbox_messages
                   SET state = 'expired'
                   WHERE ttl_s > 0
                     AND created_at + ttl_s <= ?
                     AND state IN ('new', 'read')""",
                (now,),
            )
            return cur.rowcount

    def delete_older_than(self, cutoff_s: float,
                           *, only_state: Optional[str] = None) -> int:
        """Hard-delete old messages. Default: delete any >= cutoff_s
        seconds old. Pass only_state='acked' to preserve unread history."""
        with self._lock:
            cutoff = time.time() - float(cutoff_s)
            if only_state:
                cur = self._conn.execute(
                    "DELETE FROM inbox_messages WHERE created_at < ? AND state = ?",
                    (cutoff, only_state),
                )
            else:
                cur = self._conn.execute(
                    "DELETE FROM inbox_messages WHERE created_at < ?",
                    (cutoff,),
                )
            return cur.rowcount

    # ── introspection ─────────────────────────────────────────────

    def stats(self) -> dict:
        with self._lock:
            total = self._conn.execute(
                "SELECT COUNT(*) AS c FROM inbox_messages").fetchone()["c"]
            by_state = {}
            for row in self._conn.execute(
                "SELECT state, COUNT(*) AS c FROM inbox_messages GROUP BY state"
            ).fetchall():
                by_state[row["state"]] = row["c"]
            return {"total": total, "by_state": by_state,
                    "db_path": self._db_path}

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass


# ─── Singleton accessor ────────────────────────────────────────────

_store: InboxStore | None = None
_store_lock = threading.Lock()


def get_store(db_path: Optional[str] = None) -> InboxStore:
    """Return the global inbox store. First caller picks the DB path.

    Default location: $TUDOU_CLAW_DATA_DIR/inbox.db (falling back to
    ~/.tudou_claw/inbox.db). Tests override by passing an explicit
    db_path (usually a tmp_path).
    """
    global _store
    if _store is not None and db_path is None:
        return _store
    with _store_lock:
        if _store is not None and db_path is None:
            return _store
        if db_path is None:
            from .paths import data_dir
            db_path = str(data_dir() / "inbox.db")
        if _store is not None:
            try:
                _store.close()
            except Exception:
                pass
        _store = InboxStore(db_path)
        return _store


def reset_store_for_test() -> None:
    """Close and clear the singleton. Tests call this between setups."""
    global _store
    with _store_lock:
        if _store is not None:
            try:
                _store.close()
            except Exception:
                pass
            _store = None


__all__ = [
    "InboxMessage", "InboxStore", "get_store", "reset_store_for_test",
]
