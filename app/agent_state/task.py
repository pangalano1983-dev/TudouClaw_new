"""
TaskStack — the "任务域" (task domain).

Keeps a stack of Tasks describing what the agent is currently trying to do.
The stack is NOT the same as the existing `Agent.tasks` list in app/agent.py
(that list is a flat todo board). This structure is semantically narrower:
  * it is ordered — the top is "current"
  * completed tasks are retained (not removed) so that follow-up actions
    on their results can still find them
  * each task carries result_refs pointing into ArtifactStore, not raw
    values (Invariant I1)

Classification of new user messages into "continue top" / "push new" /
"close top" / ... is done by the IntentClassifier in a later phase.
This module only provides the mechanics.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional


class TaskStatus(str, Enum):
    PENDING = "pending"       # created, not yet worked on
    ACTIVE = "active"         # top of stack, being worked on
    DONE = "done"             # finished successfully
    FAILED = "failed"         # finished unsuccessfully
    ABANDONED = "abandoned"   # user cancelled / superseded


_TERMINAL = {TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.ABANDONED}


@dataclass
class Task:
    id: str
    goal: str
    status: TaskStatus
    created_at: float
    parent_task_id: Optional[str] = None
    closed_at: Optional[float] = None
    result_refs: List[str] = field(default_factory=list)   # artifact ids
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_terminal(self) -> bool:
        return self.status in _TERMINAL

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Task":
        return cls(
            id=d["id"],
            goal=d["goal"],
            status=TaskStatus(d["status"]),
            created_at=float(d.get("created_at", 0.0)),
            parent_task_id=d.get("parent_task_id"),
            closed_at=d.get("closed_at"),
            result_refs=list(d.get("result_refs") or []),
            metadata=dict(d.get("metadata") or {}),
        )


class TaskStackFull(Exception):
    pass


class TaskNotFound(KeyError):
    pass


class TaskStack:
    """An ordered, bounded stack of Tasks.

    Terminal tasks are kept until the stack exceeds `max_retained` entries,
    at which point the oldest terminal entries are dropped from the tail.
    Active/pending tasks are never auto-dropped.
    """

    DEFAULT_MAX_DEPTH = 16          # hard ceiling on non-terminal tasks
    DEFAULT_MAX_RETAINED = 64       # soft ceiling on total (incl. terminal)

    def __init__(
        self,
        *,
        max_depth: int = DEFAULT_MAX_DEPTH,
        max_retained: int = DEFAULT_MAX_RETAINED,
    ) -> None:
        self._stack: List[Task] = []
        self._by_id: Dict[str, Task] = {}
        self._max_depth = max_depth
        self._max_retained = max_retained

    # ------------------------------------------------------------------
    # write path
    # ------------------------------------------------------------------
    def push(
        self,
        goal: str,
        *,
        parent_task_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Task:
        live = sum(1 for t in self._stack if not t.is_terminal())
        if live >= self._max_depth:
            raise TaskStackFull(
                f"cannot push: {live} non-terminal tasks already on stack "
                f"(max_depth={self._max_depth})"
            )
        # if there is an active task, demote it to pending (it will
        # become active again when the new task terminates)
        for t in self._stack:
            if t.status == TaskStatus.ACTIVE:
                t.status = TaskStatus.PENDING
        t = Task(
            id=_new_id("task"),
            goal=goal,
            status=TaskStatus.ACTIVE,
            created_at=time.time(),
            parent_task_id=parent_task_id,
            metadata=dict(metadata or {}),
        )
        self._stack.append(t)
        self._by_id[t.id] = t
        self._gc()
        return t

    def mark_done(
        self, task_id: str, *, result_refs: Optional[List[str]] = None
    ) -> Task:
        return self._terminate(task_id, TaskStatus.DONE, result_refs)

    def mark_failed(
        self,
        task_id: str,
        *,
        reason: Optional[str] = None,
        result_refs: Optional[List[str]] = None,
    ) -> Task:
        t = self._terminate(task_id, TaskStatus.FAILED, result_refs)
        if reason:
            t.metadata["failure_reason"] = reason
        return t

    def mark_abandoned(self, task_id: str, *, reason: Optional[str] = None) -> Task:
        t = self._terminate(task_id, TaskStatus.ABANDONED, None)
        if reason:
            t.metadata["abandon_reason"] = reason
        return t

    def attach_result(self, task_id: str, artifact_id: str) -> None:
        t = self._by_id.get(task_id)
        if t is None:
            raise TaskNotFound(task_id)
        if artifact_id not in t.result_refs:
            t.result_refs.append(artifact_id)

    def _terminate(
        self,
        task_id: str,
        status: TaskStatus,
        result_refs: Optional[List[str]],
    ) -> Task:
        t = self._by_id.get(task_id)
        if t is None:
            raise TaskNotFound(task_id)
        if t.is_terminal():
            return t
        t.status = status
        t.closed_at = time.time()
        if result_refs:
            for r in result_refs:
                if r not in t.result_refs:
                    t.result_refs.append(r)
        # promote the most recent non-terminal task (if any) back to active
        for other in reversed(self._stack):
            if other is t:
                continue
            if not other.is_terminal() and other.status != TaskStatus.ACTIVE:
                other.status = TaskStatus.ACTIVE
                break
        self._gc()
        return t

    def _gc(self) -> None:
        # drop oldest TERMINAL entries if we exceed max_retained
        overflow = len(self._stack) - self._max_retained
        if overflow <= 0:
            return
        new_stack: List[Task] = []
        dropped = 0
        for t in self._stack:
            if dropped < overflow and t.is_terminal():
                self._by_id.pop(t.id, None)
                dropped += 1
                continue
            new_stack.append(t)
        self._stack = new_stack

    # ------------------------------------------------------------------
    # read path
    # ------------------------------------------------------------------
    def top(self) -> Optional[Task]:
        """Highest non-terminal task (the "current" one)."""
        for t in reversed(self._stack):
            if not t.is_terminal():
                return t
        return None

    def active(self) -> List[Task]:
        return [t for t in self._stack if not t.is_terminal()]

    def recent_terminal(self, n: int = 3) -> List[Task]:
        out: List[Task] = []
        for t in reversed(self._stack):
            if t.is_terminal():
                out.append(t)
                if len(out) >= n:
                    break
        return out

    def find(self, task_id: str) -> Optional[Task]:
        return self._by_id.get(task_id)

    def all(self) -> List[Task]:
        return list(self._stack)

    def __len__(self) -> int:
        return len(self._stack)

    # ------------------------------------------------------------------
    # snapshot / restore
    # ------------------------------------------------------------------
    def snapshot(self) -> Dict[str, Any]:
        return {
            "stack": [t.to_dict() for t in self._stack],
            "max_depth": self._max_depth,
            "max_retained": self._max_retained,
        }

    def restore(self, snap: Dict[str, Any]) -> None:
        self._stack = [Task.from_dict(d) for d in snap.get("stack", [])]
        self._by_id = {t.id: t for t in self._stack}
        self._max_depth = int(snap.get("max_depth", self.DEFAULT_MAX_DEPTH))
        self._max_retained = int(snap.get("max_retained", self.DEFAULT_MAX_RETAINED))


# ----------------------------------------------------------------------
def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"
