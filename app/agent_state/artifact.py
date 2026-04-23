"""
ArtifactStore — the "产物域" (artifact domain).

Holds every object that later turns of the agent may need to refer back to:
file paths, URLs, external record IDs, structured blobs, etc.

Design rules (see architecture doc):
  * append-only: no update, no delete. TTL is metadata only; expired
    artifacts stay in the store so history stays auditable.
  * `value` is the PRECISE string/reference. Compression passes MUST NOT
    touch it. (Invariant I2.)
  * Entries are keyed by a stable opaque id so ConversationLog,
    TaskStack, and LLM prompts can reference them symbolically.
    (Invariant I1: no one else stores the precise value.)
  * File-kind artifacts must live under EnvState.deliverable_dir.
    (Invariant I5 — enforced at put() time when env is supplied.)

This class is pure-Python; persistence is out of scope for phase 1.
"""
from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional


class ArtifactKind(str, Enum):
    FILE = "file"             # generic file fallback (unknown extension)
    URL = "url"               # an http/https URL with no recognisable extension
    IMAGE = "image"           # png/jpg/gif/svg/...
    VIDEO = "video"           # mp4/webm/mov/...
    AUDIO = "audio"           # mp3/wav/m4a/...
    DOCUMENT = "document"     # pdf/docx/xlsx/pptx/txt/md/csv/code...
    ARCHIVE = "archive"       # zip/tar/gz/7z/rar...
    RECORD = "record"         # structured data blob (json-serialisable)
    TEXT_BLOB = "text_blob"   # large text body produced by a tool
    EXTERNAL_ID = "external_id"  # e.g. Notion page id, Jira ticket key
    OTHER = "other"


@dataclass(frozen=True)
class ProducedBy:
    """Who / what produced an artifact. Used for provenance and filtering."""
    task_id: Optional[str] = None
    tool_id: Optional[str] = None
    agent_id: Optional[str] = None


@dataclass
class Artifact:
    id: str
    kind: ArtifactKind
    value: str                          # PRECISE; never compressed/summarised
    label: str                          # short human-readable name
    produced_at: float
    produced_by: ProducedBy
    mime: Optional[str] = None
    size: Optional[int] = None
    ttl_s: Optional[float] = None       # None => never expires
    metadata: Dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # serialisation helpers — used by StateSnapshot
    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["kind"] = self.kind.value
        d["produced_by"] = asdict(self.produced_by)
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Artifact":
        pb = d.get("produced_by") or {}
        return cls(
            id=d["id"],
            kind=ArtifactKind(d["kind"]),
            value=d["value"],
            label=d.get("label", ""),
            produced_at=float(d.get("produced_at", 0.0)),
            produced_by=ProducedBy(
                task_id=pb.get("task_id"),
                tool_id=pb.get("tool_id"),
                agent_id=pb.get("agent_id"),
            ),
            mime=d.get("mime"),
            size=d.get("size"),
            ttl_s=d.get("ttl_s"),
            metadata=dict(d.get("metadata") or {}),
        )

    # ------------------------------------------------------------------
    def is_expired(self, now: Optional[float] = None) -> bool:
        if self.ttl_s is None:
            return False
        now = now if now is not None else time.time()
        return (now - self.produced_at) > self.ttl_s


# ----------------------------------------------------------------------
# ArtifactStore
# ----------------------------------------------------------------------
class ArtifactStore:
    """Append-only store of Artifacts.

    Not thread-safe on its own. AgentState.commit() provides the
    atomicity boundary; callers outside commit() should treat this
    as single-threaded per session.
    """

    def __init__(self) -> None:
        self._items: Dict[str, Artifact] = {}
        # insertion order tracking for stable "latest / list" behaviour
        self._order: List[str] = []

    # ------------------------------------------------------------------
    # write path (I1: only ArtifactStore stores precise values)
    # ------------------------------------------------------------------
    def put(self, artifact: Artifact) -> str:
        if not artifact.id:
            # caller forgot to assign — give them one
            artifact = Artifact(
                id=_new_id("art"),
                kind=artifact.kind,
                value=artifact.value,
                label=artifact.label,
                produced_at=artifact.produced_at or time.time(),
                produced_by=artifact.produced_by,
                mime=artifact.mime,
                size=artifact.size,
                ttl_s=artifact.ttl_s,
                metadata=dict(artifact.metadata),
            )
        if artifact.id in self._items:
            # append-only; duplicate id is a bug
            raise ValueError(f"artifact id already exists: {artifact.id}")
        if not artifact.value:
            raise ValueError("artifact.value must be non-empty")
        self._items[artifact.id] = artifact
        self._order.append(artifact.id)

        # Block 2 Day 6a — broadcast new artifacts to the ProgressBus so
        # UI timeline shows "📄 report.pptx produced (42KB)" in real time.
        # Best-effort: any failure in the bus layer must NOT corrupt
        # artifact storage (put is called on hot paths).
        try:
            _emit_artifact_produced(artifact)
        except Exception:
            pass

        return artifact.id

    def create(
        self,
        kind: ArtifactKind,
        value: str,
        label: str,
        *,
        produced_by: Optional[ProducedBy] = None,
        mime: Optional[str] = None,
        size: Optional[int] = None,
        ttl_s: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Artifact:
        """Convenience constructor + put() in one call."""
        # Use a deterministic id for file-like artifacts so the same
        # file path always maps to the same artifact URL — even after
        # a server restart when the in-memory store is rebuilt.
        art_id = _stable_id(kind, value)
        art = Artifact(
            id=art_id,
            kind=kind,
            value=value,
            label=label,
            produced_at=time.time(),
            produced_by=produced_by or ProducedBy(),
            mime=mime,
            size=size,
            ttl_s=ttl_s,
            metadata=dict(metadata or {}),
        )
        self.put(art)
        return art

    # ------------------------------------------------------------------
    # read path
    # ------------------------------------------------------------------
    def get(self, artifact_id: str) -> Optional[Artifact]:
        return self._items.get(artifact_id)

    def __contains__(self, artifact_id: str) -> bool:
        return artifact_id in self._items

    def __len__(self) -> int:
        return len(self._items)

    def all(self) -> List[Artifact]:
        return [self._items[i] for i in self._order]

    def list(
        self,
        *,
        kind: Optional[ArtifactKind] = None,
        task_id: Optional[str] = None,
        tool_id: Optional[str] = None,
        since: Optional[float] = None,
        include_expired: bool = True,
    ) -> List[Artifact]:
        out: List[Artifact] = []
        for aid in self._order:
            a = self._items[aid]
            if kind is not None and a.kind != kind:
                continue
            if task_id is not None and a.produced_by.task_id != task_id:
                continue
            if tool_id is not None and a.produced_by.tool_id != tool_id:
                continue
            if since is not None and a.produced_at < since:
                continue
            if not include_expired and a.is_expired():
                continue
            out.append(a)
        return out

    def latest(
        self,
        *,
        kind: Optional[ArtifactKind] = None,
        task_id: Optional[str] = None,
    ) -> Optional[Artifact]:
        for aid in reversed(self._order):
            a = self._items[aid]
            if kind is not None and a.kind != kind:
                continue
            if task_id is not None and a.produced_by.task_id != task_id:
                continue
            return a
        return None

    def search_by_label(self, query: str) -> List[Artifact]:
        q = query.lower().strip()
        if not q:
            return []
        return [a for a in self.all() if q in a.label.lower()]

    # ------------------------------------------------------------------
    # snapshot / restore — used by AgentState commit/rollback
    # ------------------------------------------------------------------
    def snapshot(self) -> Dict[str, Any]:
        return {
            "items": [self._items[i].to_dict() for i in self._order],
            "order": list(self._order),
        }

    def restore(self, snap: Dict[str, Any]) -> None:
        self._items.clear()
        self._order.clear()
        for d in snap.get("items", []):
            art = Artifact.from_dict(d)
            self._items[art.id] = art
        self._order = list(snap.get("order", []))


# ----------------------------------------------------------------------
def _new_id(prefix: str) -> str:
    # 8 hex chars of randomness is plenty for a single session
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# File-kind artifacts whose value is a path or URL. For these we use a
# deterministic id derived from the value so the same file always gets
# the same URL — surviving server restarts.
_FILE_LIKE_KINDS = frozenset({
    ArtifactKind.FILE,
    ArtifactKind.IMAGE,
    ArtifactKind.VIDEO,
    ArtifactKind.AUDIO,
    ArtifactKind.DOCUMENT,
    ArtifactKind.ARCHIVE,
})


def _stable_id(kind: ArtifactKind, value: str) -> str:
    """Deterministic artifact id for file-like artifacts (SHA1 of value).

    Non-file artifacts (RECORD, TEXT_BLOB, etc.) keep random ids because
    their value is a mutable blob, not a stable identity.
    """
    if kind in _FILE_LIKE_KINDS and value:
        h = hashlib.sha1(value.encode("utf-8", errors="replace")).hexdigest()
        return f"art_{h[:12]}"
    return _new_id("art")


def _emit_artifact_produced(artifact: "Artifact") -> None:
    """Broadcast a new artifact to the ProgressBus.

    Called once on every ArtifactStore.put. Publishes to three channels
    so different consumers get exactly what they need:
      - `agent:<id>` — that agent's timeline
      - `global` — admin firehose (automatic via bus)

    We intentionally DROP artifact.value from the frame data — values
    can be huge (whole markdown reports). The UI only needs id + kind
    + label + size + mime + downloadable URL to render a tile.
    """
    from ..progress_bus import get_bus, ProgressFrame
    pb = artifact.produced_by
    agent_id = ""
    if pb is not None:
        agent_id = getattr(pb, "agent_id", "") or ""
    # Try to parse an absolute file path for size / link rendering
    is_file = artifact.kind in _FILE_LIKE_KINDS
    label = artifact.label or ""
    # For file artifacts, prefer the label (usually filename) but fall
    # back to a basename of the value (which is the path) if label empty.
    if is_file and not label and artifact.value:
        import os as _os
        label = _os.path.basename(artifact.value) or artifact.value[-60:]

    channel = f"agent:{agent_id}" if agent_id else "global"
    get_bus().publish(ProgressFrame(
        kind="artifact_produced",
        channel=channel,
        agent_id=agent_id,
        data={
            "artifact_id": artifact.id,
            "kind": artifact.kind.value if hasattr(artifact.kind, "value") else str(artifact.kind),
            "label": label[:200],
            "size": artifact.size or 0,
            "mime": artifact.mime or "",
            "produced_at": artifact.produced_at,
            "produced_by": {
                "agent_id": getattr(pb, "agent_id", "") or "" if pb else "",
                "task_id": getattr(pb, "task_id", "") or "" if pb else "",
                "tool_id": getattr(pb, "tool_id", "") or "" if pb else "",
            },
            # For file-like artifacts the portal has a download route
            "download_url": (
                f"/api/agent_state/artifact/{agent_id}/{artifact.id}"
                if is_file and agent_id else ""
            ),
        },
    ))
