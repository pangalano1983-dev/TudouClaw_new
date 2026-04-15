"""Agent experience and learning router — stats, insights, retrospective, active learning."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Body

from ..deps.hub import get_hub
from ..deps.auth import CurrentUser, get_current_user

logger = logging.getLogger("tudouclaw.api.experience")

router = APIRouter(prefix="/api/portal/experience", tags=["experience"])


# ---------------------------------------------------------------------------
# Experience stats — matches legacy portal_routes_get
# ---------------------------------------------------------------------------

@router.get("/stats")
async def get_experience_stats(
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """Get experience statistics."""
    try:
        from ...experience_library import get_experience_library
        lib = get_experience_library()
        return lib.get_stats()
    except (ImportError, Exception) as e:
        return {"total": 0, "by_role": {}}


# ---------------------------------------------------------------------------
# Experience listing — matches legacy: requires `role` param
# ---------------------------------------------------------------------------

@router.get("/list")
async def list_experiences(
    role: str = Query("", description="Role to filter by (required)"),
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """List experiences by role."""
    if not role:
        raise HTTPException(400, "role parameter required")
    try:
        from ...experience_library import get_experience_library
        lib = get_experience_library()
        exps = lib.get_all_experiences(role)
        return {
            "role": role,
            "count": len(exps),
            "experiences": [e.to_dict() for e in exps[-100:]],
        }
    except (ImportError, Exception) as e:
        return {"role": role, "count": 0, "experiences": []}


# ---------------------------------------------------------------------------
# Learning history — matches legacy: iterates over agents
# ---------------------------------------------------------------------------

@router.get("/history")
async def get_learning_history(
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """Get recent retrospective/learning history from all agents."""
    try:
        history = []
        for agent in hub.agents.values():
            si = getattr(agent, 'self_improvement', None)
            if not si:
                continue
            for r in getattr(si, 'retrospective_history', [])[-10:]:
                history.append({
                    "type": "retrospective",
                    "agent_name": r.get("agent_name", agent.name),
                    "summary": r.get("what_happened", "")[:100],
                    "new_count": len(r.get("new_experiences", [])),
                    "created_at": r.get("created_at", 0),
                })
            for l in getattr(si, 'learning_history', [])[-10:]:
                history.append({
                    "type": "active_learning",
                    "agent_name": l.get("agent_name", agent.name),
                    "summary": l.get("learning_goal", "")[:100],
                    "new_count": len(l.get("new_experiences", [])),
                    "created_at": l.get("created_at", 0),
                })
        history.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        return {"history": history[:30]}
    except Exception as e:
        return {"history": []}


# ---------------------------------------------------------------------------
# Learning plans — matches legacy: iterates over agents' self_improvement
# ---------------------------------------------------------------------------

@router.get("/plans")
async def get_learning_plans(
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """Get learning plan data grouped by lifecycle state."""
    try:
        plans = []
        queued_total = running_total = completed_total = converted_total = exp_produced = 0

        for agent in hub.agents.values():
            si = getattr(agent, 'self_improvement', None)
            if not si:
                continue
            agent_role = getattr(agent, 'role', '') or ''
            agent_name = getattr(agent, 'name', '') or ''

            # Queued tasks
            for q in list(getattr(si, '_learning_queue', []) or []):
                queued_total += 1
                plans.append({
                    "id": q.get("id", ""),
                    "state": "queued",
                    "agent_id": agent.id,
                    "agent_name": agent_name,
                    "role": agent_role,
                    "learning_goal": q.get("learning_goal", ""),
                    "knowledge_gap": q.get("knowledge_gap", ""),
                    "new_experiences": [],
                    "queued_at": q.get("queued_at", 0),
                    "started_at": 0,
                    "completed_at": 0,
                    "created_at": q.get("queued_at", 0),
                })

            # Currently running
            cur = getattr(si, '_current_learning', None)
            if cur:
                running_total += 1
                plans.append({
                    "id": cur.get("id", ""),
                    "state": "running",
                    "agent_id": agent.id,
                    "agent_name": agent_name,
                    "role": agent_role,
                    "learning_goal": cur.get("learning_goal", ""),
                    "knowledge_gap": cur.get("knowledge_gap", ""),
                    "new_experiences": [],
                    "started_at": cur.get("started_at", 0),
                    "completed_at": 0,
                    "created_at": cur.get("started_at", 0),
                })

            # Completed (from learning_history)
            for h in getattr(si, 'learning_history', [])[-20:]:
                completed_total += 1
                new_exps = h.get("new_experiences", []) or []
                if new_exps:
                    converted_total += 1
                    exp_produced += len(new_exps)
                plans.append({
                    "id": h.get("id", ""),
                    "state": "completed",
                    "agent_id": agent.id,
                    "agent_name": agent_name,
                    "role": agent_role,
                    "learning_goal": h.get("learning_goal", ""),
                    "source_type": h.get("source_type", ""),
                    "source_detail": h.get("source_detail", ""),
                    "key_findings": h.get("key_findings", ""),
                    "applicable_scenes": h.get("applicable_scenes", ""),
                    "new_experiences": new_exps,
                    "started_at": h.get("started_at", 0),
                    "completed_at": h.get("completed_at", 0),
                    "created_at": h.get("completed_at", 0),
                })

        plans.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        return {
            "plans": plans[:50],
            "stats": {
                "queued": queued_total,
                "running": running_total,
                "completed": completed_total,
                "converted": converted_total,
                "exp_produced": exp_produced,
            },
        }
    except Exception as e:
        return {"plans": [], "stats": {}}


# ---------------------------------------------------------------------------
# Retrospective insights
# ---------------------------------------------------------------------------

@router.get("/insights")
async def get_retrospective_insights(
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """Get retrospective insights aggregated from all agents."""
    try:
        insights = []
        for agent in hub.agents.values():
            si = getattr(agent, 'self_improvement', None)
            if not si:
                continue
            for r in getattr(si, 'retrospective_history', [])[-5:]:
                insights.append({
                    "agent_name": getattr(agent, 'name', ''),
                    "role": getattr(agent, 'role', ''),
                    "what_happened": r.get("what_happened", ""),
                    "lesson": r.get("lesson", ""),
                    "new_experiences": r.get("new_experiences", []),
                    "created_at": r.get("created_at", 0),
                })
        insights.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        return {"insights": insights[:20]}
    except Exception as e:
        return {"insights": []}


# ---------------------------------------------------------------------------
# Trigger retrospective
# ---------------------------------------------------------------------------

@router.post("/retrospective")
async def trigger_retrospective(
    body: dict = Body(...),
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """Trigger a retrospective analysis for an agent."""
    try:
        agent_id = body.get("agent_id", "")
        if not agent_id:
            raise HTTPException(400, "Missing agent_id")

        agent = hub.get_agent(agent_id)
        if not agent:
            raise HTTPException(404, "Agent not found")

        si = getattr(agent, 'self_improvement', None)
        if si and hasattr(si, 'trigger_retrospective'):
            result = si.trigger_retrospective(body)
            return {"ok": True, "result": result}

        return {"ok": True, "message": "Self-improvement not available for this agent"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Active learning
# ---------------------------------------------------------------------------

@router.post("/learning")
async def trigger_active_learning(
    body: dict = Body(...),
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """Trigger active learning for an agent."""
    try:
        agent_id = body.get("agent_id", "")
        if not agent_id:
            raise HTTPException(400, "Missing agent_id")

        agent = hub.get_agent(agent_id)
        if not agent:
            raise HTTPException(404, "Agent not found")

        si = getattr(agent, 'self_improvement', None)
        if si and hasattr(si, 'trigger_learning'):
            result = si.trigger_learning(body)
            return {"ok": True, "result": result}

        return {"ok": True, "message": "Self-improvement not available for this agent"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
