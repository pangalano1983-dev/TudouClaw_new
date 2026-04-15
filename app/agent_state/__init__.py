"""
agent_state — typed, multi-domain state model for TudouClaw agents.

This package replaces the old "flat message list == agent memory" model
with five orthogonal state domains, as designed in
docs/agent_state_architecture (see chat transcript):

    ConversationLog   conversational text (what was said)
    TaskStack         what the agent is currently trying to do
    ArtifactStore     concrete objects produced so far (URLs, files, IDs...)
    CapabilityIndex   what tools exist right now  (placeholder in this phase)
    EnvState          where we are running        (placeholder in this phase)

Core invariants (I1..I6) are enforced by `invariants.check_all()`.
AgentState is the aggregate — it owns one instance of each domain and
provides an atomic `commit()` context manager for per-turn updates.

This module is intentionally standalone: it does NOT import from app.agent
or wire into the existing agent main loop. Phase 1 builds the foundation
in bypass mode; integration happens in a later phase.
"""
from __future__ import annotations

from .artifact import (
    Artifact,
    ArtifactKind,
    ArtifactStore,
    ProducedBy,
)
from .task import (
    Task,
    TaskStatus,
    TaskStack,
    TaskStackFull,
    TaskNotFound,
)
from .conversation import (
    ConversationLog,
    ConversationTurn,
    Role,
)
from .capability import (
    Capability,
    CapabilityIndex,
)
from .env import EnvState
from .state import AgentState, StateSnapshot, CommitError
from .invariants import Violation, check_all

__all__ = [
    "Artifact",
    "ArtifactKind",
    "ArtifactStore",
    "ProducedBy",
    "Task",
    "TaskStatus",
    "TaskStack",
    "TaskStackFull",
    "TaskNotFound",
    "ConversationLog",
    "ConversationTurn",
    "Role",
    "Capability",
    "CapabilityIndex",
    "EnvState",
    "AgentState",
    "StateSnapshot",
    "CommitError",
    "Violation",
    "check_all",
]
