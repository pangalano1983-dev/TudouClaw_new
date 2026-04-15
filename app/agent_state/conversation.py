"""
ConversationLog — the "对话域" (conversation domain).

A thin append-only wrapper around dialogue turns. The crucial difference
from the existing `Agent.messages` list is:

  * Each turn may carry `artifact_refs` — a list of ArtifactStore IDs
    mentioned in this turn. Compression may rewrite `text`, but must
    keep `artifact_refs` intact so downstream passes can still find
    the concrete values (Invariant I2).

  * Turns are typed by Role so we can split system / user / assistant /
    tool clearly, independent of OpenAI's message schema.

This domain is intentionally narrow — it does NOT know about tool call
arguments, token counts, or model-specific envelopes. Those are the
ContextAssembler's job in a later phase.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional


class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    # we deliberately do NOT model "function" separately from "tool";
    # if you need the distinction put it in metadata.


@dataclass
class ConversationTurn:
    id: str
    role: Role
    text: str
    created_at: float
    artifact_refs: List[str] = field(default_factory=list)
    task_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["role"] = self.role.value
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ConversationTurn":
        return cls(
            id=d["id"],
            role=Role(d["role"]),
            text=d["text"],
            created_at=float(d.get("created_at", 0.0)),
            artifact_refs=list(d.get("artifact_refs") or []),
            task_id=d.get("task_id"),
            metadata=dict(d.get("metadata") or {}),
        )


class ConversationLog:
    """Append-only log of ConversationTurns.

    Provides a small, well-defined surface: append, tail, iterate,
    snapshot/restore. Everything else (rendering to LLM messages,
    compression, pruning) lives in higher layers.
    """

    def __init__(self) -> None:
        self._turns: List[ConversationTurn] = []

    # ------------------------------------------------------------------
    # write path
    # ------------------------------------------------------------------
    def append(
        self,
        role: Role,
        text: str,
        *,
        artifact_refs: Optional[List[str]] = None,
        task_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ConversationTurn:
        turn = ConversationTurn(
            id=_new_id("turn"),
            role=role,
            text=text,
            created_at=time.time(),
            artifact_refs=list(artifact_refs or []),
            task_id=task_id,
            metadata=dict(metadata or {}),
        )
        self._turns.append(turn)
        return turn

    # ------------------------------------------------------------------
    # read path
    # ------------------------------------------------------------------
    def __len__(self) -> int:
        return len(self._turns)

    def all(self) -> List[ConversationTurn]:
        return list(self._turns)

    def tail(self, n: int) -> List[ConversationTurn]:
        if n <= 0:
            return []
        return self._turns[-n:]

    def last_user_turn(self) -> Optional[ConversationTurn]:
        for t in reversed(self._turns):
            if t.role == Role.USER:
                return t
        return None

    def turns_with_artifact(self, artifact_id: str) -> List[ConversationTurn]:
        return [t for t in self._turns if artifact_id in t.artifact_refs]

    # ------------------------------------------------------------------
    # compression hook (rewrite text but preserve refs — I2)
    # ------------------------------------------------------------------
    def rewrite_text(self, turn_id: str, new_text: str) -> None:
        """Compression/summariser entry point. Only touches `text`;
        `artifact_refs` are explicitly preserved. Callers may not
        drop the turn — use a dedicated prune() method (not yet
        implemented) for that.
        """
        for t in self._turns:
            if t.id == turn_id:
                t.text = new_text
                return
        raise KeyError(turn_id)

    # ------------------------------------------------------------------
    # snapshot / restore
    # ------------------------------------------------------------------
    def snapshot(self) -> Dict[str, Any]:
        return {"turns": [t.to_dict() for t in self._turns]}

    def restore(self, snap: Dict[str, Any]) -> None:
        self._turns = [ConversationTurn.from_dict(d) for d in snap.get("turns", [])]


# ----------------------------------------------------------------------
def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"
