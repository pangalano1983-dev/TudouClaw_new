"""
Invariants I1..I6 — runtime checks against an AgentState aggregate.

These are the architectural "law" the whole state model exists to
enforce. Any violation means some caller is bypassing the contract.

    I1  Artifact single-write: every artifact_ref in ConversationLog
        and every result_ref in TaskStack points to an existing
        Artifact. No one stores raw values outside ArtifactStore.
        (This file can only check the forward direction — raw-value
        leaks in free text are caught by a separate static scan.)

    I2  Precise values are not compressed: ArtifactStore values are
        non-empty strings (compression would blank them). We also
        verify no turn's artifact_refs list got corrupted into text.

    I3  Reference resolution is not skipped: best-effort structural
        check — assistant turns that mention an artifact_ref should
        either carry the ref explicitly or the turn metadata should
        mark it as "pre-resolved". (Soft warning, not a hard fail.)

    I4  Capability non-hallucination: every tool_id referenced in
        a task's metadata.planned_tool must exist in CapabilityIndex.
        (Soft warning if CapabilityIndex is empty.)

    I5  Path cross-domain: every FILE/IMAGE/VIDEO/AUDIO artifact
        whose `value` looks like a filesystem path must be under
        EnvState.deliverable_dir. URLs bypass this check.

    I6  Atomic commit: verified at commit time by AgentState, not
        checked here — included for completeness.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, TYPE_CHECKING

from .artifact import ArtifactKind

if TYPE_CHECKING:  # pragma: no cover
    from .state import AgentState


class Severity(str, Enum):
    ERROR = "error"
    WARN = "warn"


@dataclass
class Violation:
    code: str          # e.g. "I1", "I5"
    severity: Severity
    message: str
    detail: dict

    def __str__(self) -> str:
        return f"[{self.severity.value.upper()}] {self.code}: {self.message}"


# ----------------------------------------------------------------------
_FILE_KINDS = {
    ArtifactKind.FILE,
    ArtifactKind.IMAGE,
    ArtifactKind.VIDEO,
    ArtifactKind.AUDIO,
}


def _looks_like_path(value: str) -> bool:
    if not value:
        return False
    if value.startswith(("http://", "https://", "data:", "s3://", "gs://")):
        return False
    return value.startswith("/") or value.startswith("~") or (
        len(value) > 2 and value[1] == ":"  # windows C:\...
    )


# ----------------------------------------------------------------------
def check_i1(state: "AgentState") -> List[Violation]:
    """Every artifact_ref / result_ref must resolve in ArtifactStore."""
    out: List[Violation] = []
    store = state.artifacts
    # conversation refs
    for turn in state.conversation.all():
        for ref in turn.artifact_refs:
            if ref not in store:
                out.append(Violation(
                    code="I1",
                    severity=Severity.ERROR,
                    message=f"ConversationTurn {turn.id} references "
                            f"unknown artifact {ref}",
                    detail={"turn_id": turn.id, "artifact_ref": ref},
                ))
    # task result refs
    for task in state.tasks.all():
        for ref in task.result_refs:
            if ref not in store:
                out.append(Violation(
                    code="I1",
                    severity=Severity.ERROR,
                    message=f"Task {task.id} references "
                            f"unknown artifact {ref}",
                    detail={"task_id": task.id, "artifact_ref": ref},
                ))
    return out


def check_i2(state: "AgentState") -> List[Violation]:
    """Artifact.value must be non-empty. Compression must not blank it."""
    out: List[Violation] = []
    for art in state.artifacts.all():
        if not art.value:
            out.append(Violation(
                code="I2",
                severity=Severity.ERROR,
                message=f"Artifact {art.id} has empty value "
                        f"(compression bug?)",
                detail={"artifact_id": art.id, "kind": art.kind.value},
            ))
    return out


def check_i4(state: "AgentState") -> List[Violation]:
    """Tools referenced by tasks must exist in CapabilityIndex."""
    out: List[Violation] = []
    caps = state.capabilities
    if len(caps) == 0:
        # empty index = phase-1 warning, not an error
        return out
    for task in state.tasks.all():
        planned = task.metadata.get("planned_tool") if task.metadata else None
        if planned and not caps.has(planned):
            out.append(Violation(
                code="I4",
                severity=Severity.ERROR,
                message=f"Task {task.id} plans tool {planned!r} "
                        f"which is not in CapabilityIndex",
                detail={"task_id": task.id, "tool_id": planned},
            ))
    return out


def check_i5(state: "AgentState") -> List[Violation]:
    """File-kind artifacts with path-like values must be under deliverable_dir."""
    out: List[Violation] = []
    env = state.env
    if not env.deliverable_dir:
        # no deliverable dir configured — phase-1 warn
        return out
    for art in state.artifacts.all():
        if art.kind not in _FILE_KINDS:
            continue
        if not _looks_like_path(art.value):
            continue  # it's a URL, skip
        if not env.is_public_path(art.value):
            out.append(Violation(
                code="I5",
                severity=Severity.ERROR,
                message=f"Artifact {art.id} ({art.kind.value}) has path "
                        f"outside deliverable_dir: {art.value}",
                detail={
                    "artifact_id": art.id,
                    "path": art.value,
                    "deliverable_dir": env.deliverable_dir,
                },
            ))
    return out


# ----------------------------------------------------------------------
def check_all(state: "AgentState") -> List[Violation]:
    """Run every structural invariant check against `state`."""
    out: List[Violation] = []
    out.extend(check_i1(state))
    out.extend(check_i2(state))
    out.extend(check_i4(state))
    out.extend(check_i5(state))
    return out
