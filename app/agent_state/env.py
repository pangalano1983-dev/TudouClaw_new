"""
EnvState — the "环境域" (environment domain).

Phase 1 placeholder. The critical job it already does in phase 1
is to distinguish SANDBOX paths from USER-VISIBLE paths, so that
Invariant I5 ("路径不可跨域") can be enforced on file-kind artifacts.

Everything else (user identity, clock skew, MCP connection list,
language prefs) is stub fields for now.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class EnvState:
    # ------------------------------------------------------------------
    # directories — the ONLY place these live. Artifacts and tools
    # must read paths from here, not from config modules directly.
    # ------------------------------------------------------------------
    sandbox_dir: str = ""        # agent's private scratch dir (not user-visible)
    deliverable_dir: str = ""    # MUST be writable AND user-visible

    # ------------------------------------------------------------------
    # ambient info
    # ------------------------------------------------------------------
    user_id: str = ""
    agent_id: str = ""
    session_id: str = ""
    started_at: float = 0.0
    locale: str = "zh-CN"
    connected_mcps: List[str] = field(default_factory=list)
    extras: Dict[str, Any] = field(default_factory=dict)
    # Additional public roots — meeting / project shared workspaces the
    # agent is currently participating in. is_public_path accepts paths
    # under ANY of these (in addition to deliverable_dir). Populated by
    # shadow._init_env / _refresh_public_roots each turn so artifact
    # downloads for files produced in a meeting workspace don't trip
    # the "path outside deliverable_dir" I5 check.
    extra_public_roots: List[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    def __post_init__(self) -> None:
        if not self.started_at:
            self.started_at = time.time()

    # ------------------------------------------------------------------
    # path helpers — used to enforce I5
    # ------------------------------------------------------------------
    def is_public_path(self, path: str) -> bool:
        """True iff `path` is under deliverable_dir OR any extra public root.

        Extra public roots are meeting / project shared workspaces that
        the agent is currently working in — artifacts produced there
        are user-visible through the regular meeting / project UI, so
        download flows should let them through.

        Returns False for empty path (fail-closed: we cannot prove a
        path is public, so assume it is not).
        """
        if not path:
            return False
        try:
            p = os.path.abspath(path)
            if self.deliverable_dir:
                d = os.path.abspath(self.deliverable_dir)
                if p == d or p.startswith(d + os.sep):
                    return True
            for root in (self.extra_public_roots or []):
                if not root:
                    continue
                try:
                    r = os.path.abspath(root)
                except Exception:
                    continue
                if p == r or p.startswith(r + os.sep):
                    return True
            return False
        except Exception:
            return False

    def is_sandbox_path(self, path: str) -> bool:
        if not path or not self.sandbox_dir:
            return False
        try:
            p = os.path.abspath(path)
            s = os.path.abspath(self.sandbox_dir)
            return p == s or p.startswith(s + os.sep)
        except Exception:
            return False

    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EnvState":
        return cls(
            sandbox_dir=d.get("sandbox_dir", ""),
            deliverable_dir=d.get("deliverable_dir", ""),
            user_id=d.get("user_id", ""),
            agent_id=d.get("agent_id", ""),
            session_id=d.get("session_id", ""),
            started_at=float(d.get("started_at", 0.0)),
            locale=d.get("locale", "zh-CN"),
            connected_mcps=list(d.get("connected_mcps") or []),
            extras=dict(d.get("extras") or {}),
            extra_public_roots=list(d.get("extra_public_roots") or []),
        )

    # ------------------------------------------------------------------
    def snapshot(self) -> Dict[str, Any]:
        return self.to_dict()

    def restore(self, snap: Dict[str, Any]) -> None:
        other = EnvState.from_dict(snap)
        self.sandbox_dir = other.sandbox_dir
        self.deliverable_dir = other.deliverable_dir
        self.user_id = other.user_id
        self.agent_id = other.agent_id
        self.session_id = other.session_id
        self.started_at = other.started_at
        self.locale = other.locale
        self.connected_mcps = other.connected_mcps
        self.extras = other.extras
        self.extra_public_roots = other.extra_public_roots
