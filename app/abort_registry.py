"""Central task-abort registry.

Gives agent / meeting / project surfaces a uniform way to:

    1. Register the background thread that owns a task
    2. Track external subprocesses (bash, pip_install, python scripts)
       that the task spawned
    3. Flip an "aborted" flag that loops poll
    4. Send SIGTERM / SIGKILL to tracked subprocesses on abort
    5. Clean up when the task ends

Why centralize:

- Meeting already had its own gen-counter interrupt (cooperative only).
  That catches the agent between LLM turns but NOT an agent blocked in
  a long-running `python build_report.py` subprocess call.
- Projects had NO abort path at all.
- Agent chat had `abort_check` parameter but no caller flipping it from
  outside the loop (the hook existed but wasn't wired to any button).

After this module lands, the three surfaces call:

    abort_registry.mark(key, thread=current_thread)
    abort_registry.track_pid(key, pid)      # from bash tool
    abort_registry.is_aborted(key)          # polled by loops
    abort_registry.abort(key)               # the "stop" button handler
    abort_registry.clear(key)               # task ended normally

Thread-level KILLING (ctypes-inject SystemExit into a running Python
thread) is deliberately NOT included. It corrupts internal state of
common libraries (requests, sqlite) and isn't worth the risk. What we
DO provide is prompt cooperative abort + aggressive subprocess kill,
which is sufficient for 95%+ of real aborts (bash loops, runaway
python scripts, LLM spins).
"""
from __future__ import annotations

import logging
import os
import signal
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("tudou.abort_registry")


@dataclass
class _TaskState:
    key: str
    thread: Optional[threading.Thread] = None
    pids: set[int] = field(default_factory=set)
    aborted: bool = False
    aborted_at: float = 0.0
    created_at: float = field(default_factory=time.time)


class _AbortRegistry:
    """Singleton. All mutations guarded by a single lock — registry ops
    are rare enough that contention is irrelevant."""

    def __init__(self) -> None:
        self._tasks: dict[str, _TaskState] = {}
        self._lock = threading.Lock()

    # ── registration ────────────────────────────────────────────────
    def mark(self, key: str, thread: Optional[threading.Thread] = None) -> None:
        """Register a task as running. Safe to call repeatedly — later
        calls update the thread reference but keep the existing pid set
        and abort flag (so we don't accidentally un-abort a task that
        was just aborted)."""
        if not key:
            return
        with self._lock:
            st = self._tasks.get(key)
            if st is None:
                st = _TaskState(key=key)
                self._tasks[key] = st
            if thread is not None:
                st.thread = thread

    def track_pid(self, key: str, pid: int) -> None:
        """Associate an external subprocess with this task.

        Called by tools that spawn real OS processes (bash, pip_install,
        python scripts). On abort we SIGTERM all tracked pids.
        """
        if not key or pid <= 0:
            return
        with self._lock:
            st = self._tasks.get(key)
            if st is None:
                st = _TaskState(key=key)
                self._tasks[key] = st
            st.pids.add(pid)

    def untrack_pid(self, key: str, pid: int) -> None:
        """Forget a pid (subprocess finished normally)."""
        if not key:
            return
        with self._lock:
            st = self._tasks.get(key)
            if st is not None:
                st.pids.discard(pid)

    def clear(self, key: str) -> None:
        """Task ended normally — drop all state for key."""
        if not key:
            return
        with self._lock:
            self._tasks.pop(key, None)

    # ── query ───────────────────────────────────────────────────────
    def is_aborted(self, key: str) -> bool:
        """Polled by the agent execution loop, meeting reply loop,
        project task runner — between tool calls / LLM turns. Returns
        True once abort() has been called for this key, forever (until
        clear())."""
        if not key:
            return False
        with self._lock:
            st = self._tasks.get(key)
            return st is not None and st.aborted

    def get_state(self, key: str) -> dict | None:
        """Introspection — used by tests and /api/*/abort/status."""
        if not key:
            return None
        with self._lock:
            st = self._tasks.get(key)
            if st is None:
                return None
            return {
                "key": st.key,
                "aborted": st.aborted,
                "pids": sorted(st.pids),
                "age_s": time.time() - st.created_at,
                "aborted_age_s": (time.time() - st.aborted_at) if st.aborted_at else 0.0,
            }

    # ── abort ───────────────────────────────────────────────────────
    def abort(self, key: str, *, grace_s: float = 2.0) -> dict:
        """Flip the aborted flag and SIGTERM tracked subprocesses.

        Returns a summary dict:
            {key, found, killed_pids, failed_pids, aborted_now}

        `found=False` when the key has no registered task — caller
        should decide if that's an error (e.g. stop a meeting that
        isn't running) or a no-op (idempotent abort of something that
        already finished).

        `grace_s` — after SIGTERM we wait up to this long for each
        subprocess to exit, then SIGKILL. Default 2s — short because
        the user clicked a button and wants immediate feedback.
        """
        if not key:
            return {"key": key, "found": False, "killed_pids": [],
                    "failed_pids": [], "aborted_now": False}
        with self._lock:
            st = self._tasks.get(key)
            if st is None:
                return {"key": key, "found": False, "killed_pids": [],
                        "failed_pids": [], "aborted_now": False}
            already = st.aborted
            st.aborted = True
            if not already:
                st.aborted_at = time.time()
            pids_to_kill = list(st.pids)

        killed: list[int] = []
        failed: list[int] = []
        for pid in pids_to_kill:
            try:
                os.kill(pid, signal.SIGTERM)
                killed.append(pid)
            except ProcessLookupError:
                # Already exited — fine.
                killed.append(pid)
            except PermissionError as e:
                logger.warning("abort_registry: SIGTERM pid=%d failed: %s", pid, e)
                failed.append(pid)
            except Exception as e:
                logger.warning("abort_registry: SIGTERM pid=%d error: %s", pid, e)
                failed.append(pid)

        # Grace period, then SIGKILL stragglers.
        if killed and grace_s > 0:
            deadline = time.time() + grace_s
            while time.time() < deadline:
                # Check which are still alive
                still_alive = []
                for pid in killed:
                    try:
                        os.kill(pid, 0)  # signal 0 = existence probe
                        still_alive.append(pid)
                    except ProcessLookupError:
                        pass
                    except Exception:
                        still_alive.append(pid)
                if not still_alive:
                    break
                time.sleep(0.1)
            # After grace, SIGKILL anyone still hanging around.
            for pid in killed:
                try:
                    os.kill(pid, 0)
                    # still alive → SIGKILL
                    os.kill(pid, signal.SIGKILL)
                    logger.info("abort_registry: SIGKILL pid=%d (didn't exit on SIGTERM)", pid)
                except ProcessLookupError:
                    pass
                except Exception as e:
                    logger.debug("abort_registry: post-grace kill pid=%d: %s", pid, e)

        logger.info(
            "abort_registry: abort %s — killed %d pids, failed %d, already_aborted=%s",
            key, len(killed), len(failed), already,
        )
        return {
            "key": key,
            "found": True,
            "killed_pids": killed,
            "failed_pids": failed,
            "aborted_now": not already,
        }


# Singleton instance.
_registry = _AbortRegistry()


# ── module-level convenience API (what callers actually use) ────────

def mark(key: str, thread: Optional[threading.Thread] = None) -> None:
    _registry.mark(key, thread)


def track_pid(key: str, pid: int) -> None:
    _registry.track_pid(key, pid)


def untrack_pid(key: str, pid: int) -> None:
    _registry.untrack_pid(key, pid)


def clear(key: str) -> None:
    _registry.clear(key)


def is_aborted(key: str) -> bool:
    return _registry.is_aborted(key)


def get_state(key: str) -> dict | None:
    return _registry.get_state(key)


def abort(key: str, *, grace_s: float = 2.0) -> dict:
    return _registry.abort(key, grace_s=grace_s)


def abort_with_checkpoint(key: str, *,
                          snapshot_fn,
                          grace_s: float = 2.0) -> dict:
    """Snapshot-then-abort: safe "pause" semantics.

    `snapshot_fn()` MUST return a dict with keys expected by
    `checkpoint.save_for_abort`:
        {agent_id, scope, scope_id, plan_json, artifact_refs,
         chat_tail, reason, metadata}

    Any key it omits falls back to sensible defaults. A failure in
    snapshotting MUST NOT block the actual abort — we log and proceed.

    Returns the same shape as `abort()` plus a `checkpoint_id` field
    (empty string if snapshotting failed).
    """
    # Checkpoint BEFORE we kill anything — otherwise SIGTERM'd subprocess
    # output would be lost from the tail we capture.
    ckpt_id = ""
    try:
        snap = snapshot_fn() or {}
    except Exception as e:
        logger.warning("abort_with_checkpoint snapshot_fn raised: %s", e)
        snap = {}
    try:
        from . import checkpoint as _ckpt
        ckpt_id = _ckpt.save_for_abort(
            agent_id=snap.get("agent_id", ""),
            scope=snap.get("scope", _ckpt.SCOPE_AGENT),
            scope_id=snap.get("scope_id", ""),
            plan_json=snap.get("plan_json") or {},
            artifact_refs=snap.get("artifact_refs") or [],
            chat_tail=snap.get("chat_tail") or [],
            reason=snap.get("reason", _ckpt.REASON_USER_ABORT),
            metadata=snap.get("metadata") or {},
        )
    except Exception as e:
        logger.warning("abort_with_checkpoint save failed: %s", e)

    result = abort(key, grace_s=grace_s)
    result["checkpoint_id"] = ckpt_id
    return result


# ── key helpers (naming convention) ─────────────────────────────────

def agent_key(agent_id: str) -> str:
    """Key for an agent's currently-running chat turn.
    One key per agent; a new turn replaces the previous one cleanly
    (the old task should have called clear() on completion)."""
    return f"agent:{agent_id}"


def meeting_key(meeting_id: str) -> str:
    return f"meeting:{meeting_id}"


def project_key(project_id: str) -> str:
    return f"project:{project_id}"


def project_task_key(project_id: str, task_id: str) -> str:
    return f"project:{project_id}:task:{task_id}"


# Thread-local stack of "current" abort keys. Tools like bash pop the
# most recent one to know which task to track their subprocess under.
_current_key = threading.local()


def current_key() -> str:
    """Return the abort key bound to the current thread, if any."""
    return getattr(_current_key, "key", "") or ""


class AbortScope:
    """Context manager — sets the thread-local current abort key while
    a task is running. Tools consult current_key() to associate their
    spawned subprocesses with the right task. Nested scopes stack.

    Usage:
        with AbortScope(meeting_key(m.id), thread=threading.current_thread()):
            run_the_task()

    On exit, the registry is cleared automatically (no-op if abort
    was never called).
    """
    def __init__(self, key: str, thread: Optional[threading.Thread] = None,
                 clear_on_exit: bool = True):
        self.key = key
        self.thread = thread
        self.clear_on_exit = clear_on_exit
        self._prev_key: str = ""

    def __enter__(self) -> "AbortScope":
        if self.key:
            mark(self.key, self.thread)
            self._prev_key = getattr(_current_key, "key", "") or ""
            _current_key.key = self.key
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.key:
            _current_key.key = self._prev_key
            if self.clear_on_exit:
                clear(self.key)
