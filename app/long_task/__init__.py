"""Long-task subsystem — decomposition, isolated parallel execution.

Exists to support the workflow:
  1. A main agent receives a large project task that one agent can't
     reasonably finish (multi-module code project, multi-chapter report).
  2. Main agent calls ``propose_decomposition`` (this module's builtin
     tool) with a draft list of sub-tasks + a directory scaffold.
  3. The draft is persisted (does NOT yet create ProjectTasks) and
     pushed to the user for confirmation.
  4. User reviews, optionally adjusts agent assignments / sub-task
     count, confirms.
  5. Confirm creates real ``ProjectTask`` rows with isolated
     ``working_dir`` per sub-task, sets DAG ``depends_on``, and
     auto-assigns to capable idle agents (matched by ``role_hint``).
  6. Hub heartbeat dispatches ready sub-tasks in parallel; isolation
     middleware blocks writes outside each agent's wd so concurrent
     agents can't corrupt one another.

Module layout:
  models.py        — Draft + SubTaskSpec dataclasses (wire format)
  draft_store.py   — SQLite-backed persistence (table ``long_task_drafts``)
  tool_propose.py  — ``_tool_propose_decomposition`` builtin tool body
  confirm.py       — Draft → ProjectTask creation + wd scaffold + PRD copy
  auto_assign.py   — Capability-based ``role_hint`` → idle agent matcher
  isolation.py     — ``check_write_path()`` for middleware PRE_TOOL stage

What this module DOES NOT do (defer to a future Phase 3 ``long_task.merge``):
  • Static analysis / lint of merged output
  • Contract conformance checking against ``interfaces/api.yaml``
  • Integration test execution
  • Integrator agent for conflict resolution
  • Result aggregation tools

Existing files only need minimal hooks (registration / heartbeat /
middleware glue) — all logic stays here.
"""
from __future__ import annotations

# Re-export the public surface so callers ``from app.long_task import X``
# without spelunking submodules. Keep this list narrow — internal helpers
# stay private.
from .models import Draft, SubTaskSpec, DraftStatus
from .draft_store import get_draft_store
from .auto_assign import tick as auto_assign_tick
from .isolation import check_write_path
from .aggregate import (
    aggregate_parent_task,
    tick_aggregate,
    VALID_MODES as AGGREGATE_MODES,
)

__all__ = [
    "Draft",
    "SubTaskSpec",
    "DraftStatus",
    "get_draft_store",
    "auto_assign_tick",
    "check_write_path",
    "aggregate_parent_task",
    "tick_aggregate",
    "AGGREGATE_MODES",
]
