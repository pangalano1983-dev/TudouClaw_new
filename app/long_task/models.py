"""Data models for the long-task subsystem.

The wire format used by ``propose_decomposition`` (LLM tool argument)
and ``confirm_draft`` (user-facing confirmation) lives here so neither
the tool body nor the API layer has to invent its own schema.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum


class DraftStatus(str, Enum):
    """Lifecycle of a decomposition draft."""
    PENDING = "pending"            # awaiting user confirmation
    CONFIRMED = "confirmed"        # user approved → ProjectTasks created
    CANCELLED = "cancelled"        # user rejected
    EXPIRED = "expired"            # user never responded; reaper swept it


@dataclass
class SubTaskSpec:
    """One sub-task as proposed by the main agent.

    Field semantics:
      * ``id``: stable id used to reference this entry across edits in
        the confirm UI. NOT the eventual ProjectTask id (that gets
        minted on confirm).
      * ``order``: explicit ordering hint for UI / linear aggregation
        ("chapter 1 before chapter 2"). DAG dependencies still go in
        ``depends_on``.
      * ``role_hint``: required agent role to handle this sub-task
        (``coder`` / ``researcher`` / ``general`` / ``advisor``). Reuses
        existing role taxonomy — no new ``module_type`` enum.
      * ``output_path``: declared file/dir the agent will produce.
        Becomes the agent's working_dir on confirm; the isolation
        middleware blocks writes outside it.
      * ``acceptance``: one-line "task is done when X" criterion;
        surfaced both in the agent prompt and in the confirm UI.
      * ``depends_on``: list of sibling ``SubTaskSpec.id`` values whose
        ProjectTasks must reach DONE before this one becomes runnable.
        Translates into ``ProjectTask.depends_on`` post-confirm.
    """
    id: str = field(default_factory=lambda: "st_" + uuid.uuid4().hex[:10])
    title: str = ""
    description: str = ""
    role_hint: str = "general"
    output_path: str = ""              # relative to project root
    acceptance: str = ""
    order: int = 0
    depends_on: list[str] = field(default_factory=list)
    # Optional code-task extras (Phase 1 may carry these even though
    # MVP doesn't enforce — saves a future migration).
    prd_excerpt: str = ""              # task-specific slice of the PRD
    interface_contract: str = ""       # API/type hints if applicable

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "role_hint": self.role_hint,
            "output_path": self.output_path,
            "acceptance": self.acceptance,
            "order": self.order,
            "depends_on": list(self.depends_on),
            "prd_excerpt": self.prd_excerpt,
            "interface_contract": self.interface_contract,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SubTaskSpec":
        return cls(
            id=d.get("id", "st_" + uuid.uuid4().hex[:10]),
            title=d.get("title", ""),
            description=d.get("description", ""),
            role_hint=d.get("role_hint", "general"),
            output_path=d.get("output_path", ""),
            acceptance=d.get("acceptance", ""),
            order=int(d.get("order", 0) or 0),
            depends_on=list(d.get("depends_on") or []),
            prd_excerpt=d.get("prd_excerpt", ""),
            interface_contract=d.get("interface_contract", ""),
        )


@dataclass
class Draft:
    """A decomposition draft awaiting user confirmation.

    One row in the ``long_task_drafts`` table. After confirmation the
    draft moves to status=CONFIRMED and the ``materialized_task_ids``
    column gets populated; we keep the row (do not delete) so an audit
    trail of "what got proposed → what got created" is preserved.
    """
    id: str = field(default_factory=lambda: "draft_" + uuid.uuid4().hex[:10])
    project_id: str = ""
    parent_task_id: str = ""           # the big task being decomposed
    proposed_by_agent_id: str = ""
    title: str = ""                    # e.g. "Decompose: build admin panel"
    summary: str = ""                  # main agent's plain-language pitch
    prd: str = ""                      # full PRD content (md), if generated
    prd_source: str = "agent_generated"  # "user_uploaded" | "agent_generated"
    scaffold_dirs: list[str] = field(default_factory=list)  # dirs to mkdir on confirm
    sub_tasks: list[SubTaskSpec] = field(default_factory=list)
    status: DraftStatus = DraftStatus.PENDING
    created_at: float = field(default_factory=time.time)
    confirmed_at: float = 0.0
    cancelled_at: float = 0.0
    materialized_task_ids: list[str] = field(default_factory=list)
    # Free-form: confirm endpoint may stash user-edited overrides here
    # (e.g., reassigned role_hint per sub_task) before materializing.
    user_overrides: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "parent_task_id": self.parent_task_id,
            "proposed_by_agent_id": self.proposed_by_agent_id,
            "title": self.title,
            "summary": self.summary,
            "prd": self.prd,
            "prd_source": self.prd_source,
            "scaffold_dirs": list(self.scaffold_dirs),
            "sub_tasks": [s.to_dict() for s in self.sub_tasks],
            "status": self.status.value,
            "created_at": self.created_at,
            "confirmed_at": self.confirmed_at,
            "cancelled_at": self.cancelled_at,
            "materialized_task_ids": list(self.materialized_task_ids),
            "user_overrides": dict(self.user_overrides),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Draft":
        return cls(
            id=d.get("id", "draft_" + uuid.uuid4().hex[:10]),
            project_id=d.get("project_id", ""),
            parent_task_id=d.get("parent_task_id", ""),
            proposed_by_agent_id=d.get("proposed_by_agent_id", ""),
            title=d.get("title", ""),
            summary=d.get("summary", ""),
            prd=d.get("prd", ""),
            prd_source=d.get("prd_source", "agent_generated"),
            scaffold_dirs=list(d.get("scaffold_dirs") or []),
            sub_tasks=[SubTaskSpec.from_dict(x) for x in (d.get("sub_tasks") or [])],
            status=DraftStatus(d.get("status", "pending")),
            created_at=float(d.get("created_at", time.time()) or time.time()),
            confirmed_at=float(d.get("confirmed_at", 0) or 0),
            cancelled_at=float(d.get("cancelled_at", 0) or 0),
            materialized_task_ids=list(d.get("materialized_task_ids") or []),
            user_overrides=dict(d.get("user_overrides") or {}),
        )
