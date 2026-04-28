"""In-memory install progress tracker for URL-based skill installs.

Use case: an `install_skill_from_url` call takes 5-10 seconds. The UI was
showing zero feedback during that window, so users thought the system
was hung. This module exposes per-install progress state that the UI
can poll.

Pattern
=======
1. Caller (UI handler) calls ``start(install_id)``
2. The installer module updates progress at each step via ``update(...)``
3. UI polls ``get(install_id)`` every ~500ms to drive a progress bar
4. When done, ``complete(install_id, result)`` records final state
   (success/error). State is kept ~5 min then GC'd so polls after the UI
   closes don't leak memory.

Thread-safe (uses a lock — installs run in worker threads).
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional


# ──────────────────────────────────────────────────────────────────────
# State
# ──────────────────────────────────────────────────────────────────────


@dataclass
class InstallProgress:
    """Per-install status snapshot (returned to the UI poll endpoint)."""
    install_id: str
    phase: str = "pending"          # short machine-readable phase key
    message: str = ""               # human-readable display text
    progress_pct: int = 0           # 0-100, monotonically increasing
    status: str = "running"         # running | success | error
    error: str = ""                 # populated when status == "error"
    result: dict | None = None      # populated when status == "success"
    source_url: str = ""            # original URL the user pasted
    started_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "install_id": self.install_id,
            "phase": self.phase,
            "message": self.message,
            "progress_pct": self.progress_pct,
            "status": self.status,
            "error": self.error,
            "result": self.result,
            "source_url": self.source_url,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "elapsed_s": round(self.updated_at - self.started_at, 2),
        }


# ──────────────────────────────────────────────────────────────────────
# Registry
# ──────────────────────────────────────────────────────────────────────


_LOCK = threading.Lock()
_INSTALLS: dict[str, InstallProgress] = {}
_TTL_S = 300  # keep terminal-state entries 5 min so late polls still work


def start(source_url: str = "") -> str:
    """Allocate a new install_id and return it. Initial state = 'pending'."""
    install_id = uuid.uuid4().hex[:12]
    with _LOCK:
        _INSTALLS[install_id] = InstallProgress(
            install_id=install_id,
            source_url=source_url,
            phase="pending",
            message="排队中...",
            progress_pct=0,
        )
        _gc_locked()
    return install_id


def update(install_id: str, *,
            phase: str | None = None,
            message: str | None = None,
            progress_pct: int | None = None) -> None:
    """Update an in-flight install. Silently no-op if install_id unknown."""
    with _LOCK:
        st = _INSTALLS.get(install_id)
        if st is None:
            return
        if phase is not None:
            st.phase = phase
        if message is not None:
            st.message = message
        if progress_pct is not None:
            # Monotonic — UI shouldn't go backwards
            st.progress_pct = max(st.progress_pct, min(100, progress_pct))
        st.updated_at = time.time()


def complete(install_id: str, *,
              success: bool,
              result: dict | None = None,
              error: str = "") -> None:
    """Mark install as terminal. Future polls return final state."""
    with _LOCK:
        st = _INSTALLS.get(install_id)
        if st is None:
            return
        st.status = "success" if success else "error"
        st.phase = "done" if success else "error"
        st.message = "✓ 安装完成" if success else f"安装失败: {error[:200]}"
        st.progress_pct = 100
        st.result = result
        st.error = error
        st.updated_at = time.time()


def get(install_id: str) -> InstallProgress | None:
    """Return current state. Caller should ``.to_dict()`` for JSON."""
    with _LOCK:
        return _INSTALLS.get(install_id)


def _gc_locked() -> None:
    """Drop terminal-state entries older than TTL. Call WITH _LOCK held."""
    now = time.time()
    stale = [
        k for k, v in _INSTALLS.items()
        if v.status in ("success", "error") and (now - v.updated_at) > _TTL_S
    ]
    for k in stale:
        _INSTALLS.pop(k, None)


__all__ = [
    "InstallProgress",
    "start",
    "update",
    "complete",
    "get",
]
