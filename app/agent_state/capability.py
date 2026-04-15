"""
CapabilityIndex — the "能力域" (capability domain).

Phase 1 placeholder. Enough of an interface that the rest of the
state machinery can query "do I have tool X right now?" and enforce
Invariant I4 ("能力不可幻觉") without guessing from text.

Full implementation — wiring to MCPManager, failure-mode taxonomy,
side-effect classification — is phase 2 work.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional


class SideEffect(str, Enum):
    READ = "read"              # pure read, no state change
    WRITE_LOCAL = "write_local"    # writes to our own filesystem
    WRITE_EXTERNAL = "write_external"  # writes to an external system
    NETWORK = "network"        # makes outbound calls, no persistent effect
    UNKNOWN = "unknown"


class Availability(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"      # partially working (e.g. rate-limited)


@dataclass
class Capability:
    tool_id: str               # stable identifier the planner will emit
    description: str           # one-line human description
    side_effects: SideEffect = SideEffect.UNKNOWN
    availability: Availability = Availability.ONLINE
    input_schema: Optional[Dict[str, Any]] = None   # JSON-schema style, optional
    failure_modes: List[str] = field(default_factory=list)
    source: str = ""           # e.g. "mcp:jimeng_video", "builtin"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["side_effects"] = self.side_effects.value
        d["availability"] = self.availability.value
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Capability":
        return cls(
            tool_id=d["tool_id"],
            description=d.get("description", ""),
            side_effects=SideEffect(d.get("side_effects", "unknown")),
            availability=Availability(d.get("availability", "online")),
            input_schema=d.get("input_schema"),
            failure_modes=list(d.get("failure_modes") or []),
            source=d.get("source", ""),
            metadata=dict(d.get("metadata") or {}),
        )


class CapabilityIndex:
    """Simple dict-backed registry.

    No automatic discovery in phase 1 — callers populate it
    explicitly (or a future MCPManager bridge populates it).
    """

    def __init__(self) -> None:
        self._items: Dict[str, Capability] = {}

    def register(self, cap: Capability) -> None:
        self._items[cap.tool_id] = cap

    def unregister(self, tool_id: str) -> None:
        self._items.pop(tool_id, None)

    def has(self, tool_id: str) -> bool:
        cap = self._items.get(tool_id)
        if cap is None:
            return False
        return cap.availability != Availability.OFFLINE

    def get(self, tool_id: str) -> Optional[Capability]:
        return self._items.get(tool_id)

    def list(self) -> List[Capability]:
        return list(self._items.values())

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, tool_id: str) -> bool:
        return tool_id in self._items

    # ------------------------------------------------------------------
    def snapshot(self) -> Dict[str, Any]:
        return {"items": [c.to_dict() for c in self._items.values()]}

    def restore(self, snap: Dict[str, Any]) -> None:
        self._items.clear()
        for d in snap.get("items", []):
            c = Capability.from_dict(d)
            self._items[c.tool_id] = c
