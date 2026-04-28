"""Materializer: turn a confirmed Draft into real ProjectTasks.

Called by the API endpoint ``POST /projects/{id}/decomposition-drafts/{draft_id}/confirm``.
Steps:
  1. Validate the draft is still PENDING.
  2. Apply user_overrides (e.g., reassigned role_hint per sub_task,
     dropped sub_tasks).
  3. Create the project's scaffold directories (under the project's
     working_dir).
  4. Write PRD.md and (if absent) ARCHITECTURE.md to project root.
  5. For each sub_task, create a ``ProjectTask`` with:
       - parent_task_id  → the original big task
       - role_hint       → for auto_assign
       - decomp_metadata → the raw SubTaskSpec for traceability
       - depends_on      → translated from sub_task.id refs to real
                            ProjectTask ids
       - assigned_to     → "" (empty; auto_assign fills it later)
  6. Mark the original parent task status=DECOMPOSED so its agent
     stops trying to handle it directly.
  7. Mark draft CONFIRMED + record materialized_task_ids.
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

from .draft_store import get_draft_store
from .models import Draft, DraftStatus

logger = logging.getLogger("tudouclaw.long_task.confirm")


class ConfirmError(Exception):
    """Raised when the draft cannot be materialized. The API layer
    converts this to a 4xx response with the message body intact."""


def _project_root(hub, project) -> Path:
    """Return the project's filesystem root (where scaffold goes).

    Prefers ``project.working_directory`` (set at create time);
    falls back to a per-project subfolder under the user's
    ``~/.tudou_claw/workspaces/projects/<project_id>/``.
    """
    wd = (getattr(project, "working_directory", "") or "").strip()
    if wd:
        return Path(wd).expanduser()
    return Path.home() / ".tudou_claw" / "workspaces" / "projects" / project.id


def _apply_overrides(draft: Draft) -> Draft:
    """Apply user_overrides to the draft in-place. Supported overrides:

    .. code-block:: json

       {
         "dropped_sub_task_ids": ["st_abc", "st_def"],
         "role_overrides":       {"st_xyz": "researcher"},
         "title_overrides":      {"st_xyz": "Renamed title"},
         "output_path_overrides":{"st_xyz": "backend/auth_v2"}
       }
    """
    o = draft.user_overrides or {}
    dropped = set(o.get("dropped_sub_task_ids") or [])
    role_o = o.get("role_overrides") or {}
    title_o = o.get("title_overrides") or {}
    path_o = o.get("output_path_overrides") or {}

    kept = []
    for st in draft.sub_tasks:
        if st.id in dropped:
            continue
        if st.id in role_o:
            st.role_hint = role_o[st.id]
        if st.id in title_o:
            st.title = title_o[st.id]
        if st.id in path_o:
            st.output_path = path_o[st.id]
        kept.append(st)
    draft.sub_tasks = kept

    # Also drop dependencies that point at dropped sub_tasks.
    kept_ids = {st.id for st in kept}
    for st in kept:
        st.depends_on = [d for d in st.depends_on if d in kept_ids]
    return draft


def _scaffold_filesystem(root: Path, draft: Draft) -> None:
    """Create scaffold dirs + write PRD.md + ARCHITECTURE.md."""
    root.mkdir(parents=True, exist_ok=True)
    # PRD — write only if not already present (respect a user-uploaded one).
    prd_path = root / "PRD.md"
    if not prd_path.exists() and draft.prd:
        try:
            prd_path.write_text(draft.prd, encoding="utf-8")
        except OSError as e:
            logger.warning("Failed to write PRD.md: %s", e)
    # Scaffold dirs
    for d in draft.scaffold_dirs or []:
        try:
            (root / d).mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.warning("Failed to mkdir scaffold %s: %s", d, e)
    # Sub-task output_paths get created too (so each agent's wd exists
    # before it gets dispatched — avoids "wd does not exist" errors in
    # the chat loop).
    for st in draft.sub_tasks or []:
        if st.output_path:
            try:
                (root / st.output_path).mkdir(parents=True, exist_ok=True)
            except OSError as e:
                logger.warning(
                    "Failed to mkdir sub-task wd %s: %s", st.output_path, e)


def _materialize_tasks(hub, project, draft: Draft, root: Path) -> list[str]:
    """Create one ProjectTask per sub_task. Returns the list of new
    ProjectTask ids in declaration order (so callers can build a UI
    "10 tasks created" notice)."""
    from ..project import ProjectTask, ProjectTaskStatus

    # Map sub_task spec id → minted ProjectTask id, so depends_on can
    # be translated after all tasks exist.
    spec_to_task_id: dict[str, str] = {}
    new_tasks: list[ProjectTask] = []

    for st in draft.sub_tasks:
        # Concrete working_dir for this agent (absolute path).
        agent_wd = str((root / st.output_path).resolve()) if st.output_path else str(root)
        task = ProjectTask(
            title=st.title,
            description=st.description or st.prd_excerpt or "",
            assigned_to="",  # auto_assign fills this later
            created_by=draft.proposed_by_agent_id or "system:long_task",
            priority=0,
            acceptance=st.acceptance or "",
            depends_on=[],   # translated below
        )
        # Long-task extension fields (set via setattr to be tolerant of
        # ProjectTask not yet declaring them — the project.py edit comes
        # in a separate step).
        try:
            task.parent_task_id = draft.parent_task_id
            task.role_hint = st.role_hint
            task.decomp_metadata = {
                "draft_id": draft.id,
                "sub_task_id": st.id,
                "output_path": st.output_path,
                "agent_wd": agent_wd,
                "order": st.order,
                "interface_contract": st.interface_contract,
            }
        except Exception:
            # Older ProjectTask without these fields — stash in metadata
            try:
                task.metadata["parent_task_id"] = draft.parent_task_id
                task.metadata["role_hint"] = st.role_hint
                task.metadata["decomp"] = {
                    "draft_id": draft.id,
                    "sub_task_id": st.id,
                    "output_path": st.output_path,
                    "agent_wd": agent_wd,
                    "order": st.order,
                }
            except Exception:
                pass

        spec_to_task_id[st.id] = task.id
        new_tasks.append(task)

    # Now translate depends_on (sub_task spec id → real ProjectTask id)
    for st, task in zip(draft.sub_tasks, new_tasks):
        translated = [spec_to_task_id[d] for d in st.depends_on
                      if d in spec_to_task_id]
        task.depends_on = translated

    # Append to project + persist
    if project.tasks is None:
        project.tasks = []
    project.tasks.extend(new_tasks)

    try:
        if hasattr(hub, "_save_projects"):
            hub._save_projects()
    except Exception as e:
        logger.warning("Failed to persist project after materialize: %s", e)

    return [t.id for t in new_tasks]


def _mark_parent_decomposed(hub, project, parent_task_id: str) -> None:
    """Set the original big task's status so its agent stops working it
    directly. We don't have a formal DECOMPOSED enum yet; reuse
    BLOCKED + a metadata flag that the UI can read to render
    "decomposed into N sub-tasks" instead of "blocked"."""
    if not parent_task_id:
        return
    from ..project import ProjectTaskStatus
    parent = next((t for t in (project.tasks or [])
                   if t.id == parent_task_id), None)
    if parent is None:
        return
    parent.status = ProjectTaskStatus.BLOCKED
    try:
        parent.metadata = parent.metadata or {}
        parent.metadata["decomposed"] = True
        parent.metadata["decomposed_at"] = time.time()
    except Exception:
        pass


def confirm_draft(hub, draft_id: str,
                  user_overrides: dict | None = None) -> dict:
    """API entry-point. Returns a dict with the materialized task ids
    + project_id, suitable for the JSON response.

    Raises ConfirmError on validation failures (caller maps to 4xx).
    """
    store = get_draft_store()
    draft = store.get(draft_id)
    if draft is None:
        raise ConfirmError(f"draft {draft_id!r} not found")
    if draft.status != DraftStatus.PENDING:
        raise ConfirmError(
            f"draft {draft_id!r} is {draft.status.value}, "
            f"only pending drafts can be confirmed",
        )

    # Merge passed-in overrides into draft before applying.
    if user_overrides:
        merged = dict(draft.user_overrides or {})
        merged.update(user_overrides)
        draft.user_overrides = merged
    _apply_overrides(draft)

    if not draft.sub_tasks:
        raise ConfirmError("draft has no sub_tasks after applying overrides")

    project = hub.get_project(draft.project_id) \
        if hasattr(hub, "get_project") else None
    if project is None:
        raise ConfirmError(f"project {draft.project_id!r} not found")

    root = _project_root(hub, project)
    _scaffold_filesystem(root, draft)
    new_ids = _materialize_tasks(hub, project, draft, root)
    _mark_parent_decomposed(hub, project, draft.parent_task_id)

    # Mark draft confirmed + record materialized ids
    draft.status = DraftStatus.CONFIRMED
    draft.materialized_task_ids = new_ids
    store.save(draft)

    logger.info(
        "Confirmed draft %s for project %s: created %d sub-tasks",
        draft.id, project.id, len(new_ids),
    )

    return {
        "ok": True,
        "draft_id": draft.id,
        "project_id": project.id,
        "parent_task_id": draft.parent_task_id,
        "sub_task_ids": new_ids,
        "scaffold_root": str(root),
    }


def cancel_draft(draft_id: str) -> bool:
    """Mark a draft as cancelled (no tasks created). Returns True if the
    draft existed and was pending; False otherwise."""
    store = get_draft_store()
    draft = store.get(draft_id)
    if draft is None or draft.status != DraftStatus.PENDING:
        return False
    draft.status = DraftStatus.CANCELLED
    store.save(draft)
    return True
