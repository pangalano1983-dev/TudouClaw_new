"""Orchestration view endpoints — feeds the operator dashboard.

Three read-only endpoints:
  • ``GET /orchestration/overview``  — at-a-glance system health
  • ``GET /orchestration/agents``    — agent leaderboard (success rate)
  • ``GET /orchestration/pipelines`` — long-task pipeline (parent tasks
                                       + child status + aggregator state)

All queries are pure aggregation over already-persisted state. No new
schema. Designed to be cheap enough that the orchestration page can
poll on a 5-10s cadence.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps.hub import get_hub
from ..deps.auth import CurrentUser, get_current_user

logger = logging.getLogger("tudouclaw.api.orchestration")

router = APIRouter(prefix="/api/portal/orchestration", tags=["orchestration"])


@router.get("/overview")
async def get_overview(
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """At-a-glance system stats. Aggregated over the last hour."""
    agents = list((hub.agents or {}).values()) if hasattr(hub, "agents") else []
    total_events = sum(len(getattr(a, "events", []) or []) for a in agents)
    # Tokens
    total_in = 0
    total_out = 0
    for a in agents:
        try:
            total_in += int(getattr(a, "total_input_tokens", 0) or 0)
            total_out += int(getattr(a, "total_output_tokens", 0) or 0)
        except Exception:
            pass
    # Project + long-task pipeline counts
    proj_count = 0
    parent_task_count = 0
    in_flight_subtasks = 0
    aggregated_count = 0
    try:
        from ..deps.hub import get_hub as _gh  # noqa: F401
        from ...project import ProjectTaskStatus
        for p in (hub.list_projects() if hasattr(hub, "list_projects") else []):
            proj_count += 1
            for t in (p.tasks or []):
                if getattr(t, "parent_task_id", ""):
                    if t.status == ProjectTaskStatus.IN_PROGRESS:
                        in_flight_subtasks += 1
                else:
                    # Possible parent — check if has children
                    has_children = any(
                        getattr(c, "parent_task_id", "") == t.id
                        for c in (p.tasks or [])
                    )
                    if has_children:
                        parent_task_count += 1
                        if (t.metadata or {}).get("aggregated"):
                            aggregated_count += 1
    except Exception as e:
        logger.debug("overview project scan failed: %s", e)

    # Agent status breakdown
    status_counts = {"idle": 0, "busy": 0, "error": 0, "offline": 0}
    for a in agents:
        st = getattr(a, "status", None)
        sv = getattr(st, "value", st) or "offline"
        status_counts[str(sv)] = status_counts.get(str(sv), 0) + 1

    return {
        "agent_count": len(agents),
        "agent_status": status_counts,
        "total_events": total_events,
        "tokens": {
            "in": total_in,
            "out": total_out,
            "total": total_in + total_out,
        },
        "projects": {
            "count": proj_count,
            "parent_tasks": parent_task_count,
            "in_flight_subtasks": in_flight_subtasks,
            "aggregated": aggregated_count,
        },
        "ts": time.time(),
    }


@router.get("/agents")
async def get_agent_leaderboard(
    limit: int = Query(50, ge=1, le=200),
    role: Optional[str] = Query(None),
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """Agent leaderboard sorted by success rate.

    Smoothed rate: ``(success + 1) / (success + fail + 2)`` so brand-new
    agents start at 50% and aren't punished by zero data. Same formula
    as ``long_task.auto_assign._success_rate``.
    """
    agents = list((hub.agents or {}).values()) if hasattr(hub, "agents") else []
    rows = []
    for a in agents:
        if role and (a.role or "").lower() != role.lower():
            continue
        s = int(getattr(a, "role_success_count", 0) or 0)
        f = int(getattr(a, "role_fail_count", 0) or 0)
        rate = (s + 1) / (s + f + 2)
        last_at = float(getattr(a, "role_last_success_at", 0) or 0)
        # Status surface for the UI
        st = getattr(a, "status", None)
        st_val = getattr(st, "value", st) or "offline"
        rows.append({
            "id": a.id,
            "name": a.name,
            "role": a.role,
            "label": f"{a.role or '?'}-{a.name or '?'}",
            "success_count": s,
            "fail_count": f,
            "total_count": s + f,
            "success_rate": round(rate, 4),
            "last_success_at": last_at,
            "status": str(st_val),
        })
    # Sort: agents with real history first (push 0/0 to the bottom — their
    # 50% smoothed score is a prior, not a measurement). Within each group:
    # rate desc, then total_count desc (more data = more trustworthy).
    rows.sort(key=lambda r: (
        0 if r["total_count"] > 0 else 1,
        -r["success_rate"],
        -r["total_count"],
    ))
    return {
        "agents": rows[:limit],
        "total": len(rows),
        "ts": time.time(),
    }


@router.get("/pipelines")
async def get_pipelines(
    limit: int = Query(20, ge=1, le=100),
    include_done: bool = Query(False),
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """In-flight long-task pipelines (parent + children + aggregator).

    Each entry: parent task title + child status breakdown + aggregator
    mode + result hint.
    """
    out = []
    try:
        from ...project import ProjectTaskStatus
        for p in (hub.list_projects() if hasattr(hub, "list_projects") else []):
            tasks_by_id = {t.id: t for t in (p.tasks or [])}
            # Find parent tasks (those with at least one child)
            parent_ids: set[str] = set()
            for t in (p.tasks or []):
                pid = getattr(t, "parent_task_id", "") or ""
                if pid and pid in tasks_by_id:
                    parent_ids.add(pid)
            for pid in parent_ids:
                parent = tasks_by_id.get(pid)
                if not parent:
                    continue
                meta = parent.metadata or {}
                aggregated = bool(meta.get("aggregated"))
                if aggregated and not include_done:
                    continue
                children = [t for t in (p.tasks or [])
                            if getattr(t, "parent_task_id", "") == pid]
                child_status_counts = {}
                child_rows = []
                for c in children:
                    sv = getattr(c.status, "value", c.status) or "?"
                    child_status_counts[sv] = child_status_counts.get(sv, 0) + 1
                    cmeta = c.decomp_metadata or {}
                    cmeta_full = c.metadata or {}
                    # Look up assigned agent name for inline display
                    agent_name = ""
                    if c.assigned_to and hasattr(hub, "get_agent"):
                        ag = hub.get_agent(c.assigned_to)
                        if ag is not None:
                            agent_name = getattr(ag, "name", "") or c.assigned_to
                    child_rows.append({
                        "id": c.id,
                        "title": c.title,
                        "status": str(sv),
                        "assigned_to": c.assigned_to or "",
                        "assigned_to_name": agent_name,
                        "role_hint": getattr(c, "role_hint", ""),
                        "order": int(cmeta.get("order", 0) or 0),
                        "output_path": cmeta.get("output_path", ""),
                        "depends_on": list(getattr(c, "depends_on", []) or []),
                        "assignment_reason": cmeta_full.get("assignment_reason") or {},
                    })
                child_rows.sort(key=lambda r: r["order"])
                out.append({
                    "project_id": p.id,
                    "project_name": p.name,
                    "parent_task_id": parent.id,
                    "parent_title": parent.title,
                    "parent_status": str(getattr(parent.status, "value",
                                                 parent.status) or "?"),
                    "child_count": len(children),
                    "child_status_counts": child_status_counts,
                    "children": child_rows,
                    "aggregated": aggregated,
                    "aggregator_mode": meta.get("aggregator_mode") or
                                       meta.get("aggregator_mode_hint") or
                                       "concat_markdown",
                    "aggregated_at": float(meta.get("aggregated_at", 0) or 0),
                    "result_preview": (parent.result or "")[:200],
                })
    except Exception as e:
        logger.warning("pipelines scan failed: %s", e)
    # Sort: in-flight first, then most recently aggregated
    out.sort(key=lambda r: (r["aggregated"], -r.get("aggregated_at", 0)))
    return {
        "pipelines": out[:limit],
        "total": len(out),
        "ts": time.time(),
    }
