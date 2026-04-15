"""
AgentState — aggregate of the five state domains, with atomic commit.

Usage pattern (from a future agent main loop):

    state = AgentState()
    state.env.deliverable_dir = "/path/to/user/folder"
    state.capabilities.register(Capability(tool_id="jimeng_video.submit_task", ...))

    with state.commit() as draft:
        draft.conversation.append(Role.USER, "生成一个打工人视频")
        task = draft.tasks.push("生成打工人视频")
        # ... planner/executor ...
        art = draft.artifacts.create(
            kind=ArtifactKind.VIDEO,
            value="https://...signed-url...",
            label="打工人周一清晨 30s",
            produced_by=ProducedBy(task_id=task.id, tool_id="jimeng_video.submit_task"),
        )
        draft.tasks.attach_result(task.id, art.id)
        draft.tasks.mark_done(task.id)
        draft.conversation.append(
            Role.ASSISTANT,
            "已生成视频 {art}",          # text uses ref id, not raw URL
            artifact_refs=[art.id],
        )

    # If anything inside the `with` block raises, the snapshot is
    # restored and no partial changes remain.
    # After commit, invariants I1..I5 are checked automatically.

The `draft` you receive inside the `with` block is the same object as
`state` — there is no copy-on-write. The snapshot is taken on entry
and restored on exception only. This keeps the hot path cheap.
"""
from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional

from .artifact import ArtifactStore
from .task import TaskStack
from .conversation import ConversationLog
from .capability import CapabilityIndex
from .env import EnvState
from .invariants import Violation, Severity, check_all


class CommitError(Exception):
    """Raised when a commit fails invariant checks and is rolled back."""
    def __init__(self, violations: List[Violation]):
        self.violations = violations
        super().__init__(
            "commit rejected: "
            + "; ".join(str(v) for v in violations[:5])
            + ("..." if len(violations) > 5 else "")
        )


@dataclass
class StateSnapshot:
    """Opaque snapshot blob used for rollback."""
    artifacts: Dict[str, Any]
    tasks: Dict[str, Any]
    conversation: Dict[str, Any]
    capabilities: Dict[str, Any]
    env: Dict[str, Any]


class AgentState:
    """Aggregate of ConversationLog + TaskStack + ArtifactStore +
    CapabilityIndex + EnvState. Owns the commit boundary.
    """

    def __init__(
        self,
        *,
        conversation: Optional[ConversationLog] = None,
        tasks: Optional[TaskStack] = None,
        artifacts: Optional[ArtifactStore] = None,
        capabilities: Optional[CapabilityIndex] = None,
        env: Optional[EnvState] = None,
    ) -> None:
        self.conversation = conversation or ConversationLog()
        self.tasks = tasks or TaskStack()
        self.artifacts = artifacts or ArtifactStore()
        self.capabilities = capabilities or CapabilityIndex()
        self.env = env or EnvState()

    # ------------------------------------------------------------------
    # snapshot / restore (I6: atomic commit)
    # ------------------------------------------------------------------
    def snapshot(self) -> StateSnapshot:
        return StateSnapshot(
            artifacts=self.artifacts.snapshot(),
            tasks=self.tasks.snapshot(),
            conversation=self.conversation.snapshot(),
            capabilities=self.capabilities.snapshot(),
            env=self.env.snapshot(),
        )

    def restore(self, snap: StateSnapshot) -> None:
        self.artifacts.restore(snap.artifacts)
        self.tasks.restore(snap.tasks)
        self.conversation.restore(snap.conversation)
        self.capabilities.restore(snap.capabilities)
        self.env.restore(snap.env)

    # ------------------------------------------------------------------
    @contextlib.contextmanager
    def commit(
        self, *, strict: bool = True
    ) -> Iterator["AgentState"]:
        """Context manager for one atomic turn.

        * On exception inside the `with` block, state is rolled back
          to the snapshot taken at entry.
        * On normal exit, invariants I1..I5 are checked. If `strict`
          is True (default) and any ERROR-severity violation is
          found, the state is rolled back and CommitError is raised.
          WARN-severity violations are returned via the violations
          attribute on the draft (and logged, eventually).
        """
        snap = self.snapshot()
        try:
            yield self
        except Exception:
            self.restore(snap)
            raise
        # post-commit invariants
        violations = check_all(self)
        errors = [v for v in violations if v.severity == Severity.ERROR]
        if errors and strict:
            self.restore(snap)
            raise CommitError(errors)
        # expose non-fatal warnings for caller inspection
        self._last_violations = violations

    # ------------------------------------------------------------------
    @property
    def last_violations(self) -> List[Violation]:
        return getattr(self, "_last_violations", [])

    # ------------------------------------------------------------------
    def summary(self) -> Dict[str, Any]:
        """Lightweight dict summary for logging / debugging."""
        top = self.tasks.top()
        return {
            "conversation_turns": len(self.conversation),
            "tasks_total": len(self.tasks),
            "tasks_active": len(self.tasks.active()),
            "top_task": top.goal if top else None,
            "top_task_id": top.id if top else None,
            "artifacts_total": len(self.artifacts),
            "capabilities": len(self.capabilities),
            "deliverable_dir": self.env.deliverable_dir,
        }
