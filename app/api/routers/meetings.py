"""Meeting management router — list, CRUD, meeting management."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Body

from ..deps.hub import get_hub
from ..deps.auth import CurrentUser, get_current_user

logger = logging.getLogger("tudouclaw.api.meetings")

router = APIRouter(prefix="/api/portal", tags=["meetings"])


# ---------------------------------------------------------------------------
# Meeting listing — matches legacy portal_routes_get
# ---------------------------------------------------------------------------

@router.get("/meetings")
async def list_meetings(
    project_id: str = Query("", description="Filter by project"),
    status: str = Query("", description="Filter by status"),
    participant: str = Query("", description="Filter by participant agent ID"),
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """List all meetings."""
    try:
        reg = getattr(hub, "meeting_registry", None)
        if reg is None:
            return {"meetings": []}
        items = reg.list(
            project_id=project_id or None,
            status=status or None,
            participant=participant or None,
        )
        return {"meetings": [m.to_summary_dict() for m in items]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Single meeting
# ---------------------------------------------------------------------------

@router.get("/meetings/{meeting_id}")
async def get_meeting(
    meeting_id: str,
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """Get meeting detail."""
    try:
        reg = getattr(hub, "meeting_registry", None)
        if reg is None:
            raise HTTPException(503, "meeting registry not initialized")
        m = reg.get(meeting_id)
        if not m:
            raise HTTPException(404, "Meeting not found")
        return m.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Meeting messages
# ---------------------------------------------------------------------------

@router.get("/meetings/{meeting_id}/messages")
async def get_meeting_messages(
    meeting_id: str,
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """Get meeting messages."""
    try:
        reg = getattr(hub, "meeting_registry", None)
        if reg is None:
            raise HTTPException(503, "meeting registry not initialized")
        m = reg.get(meeting_id)
        if not m:
            raise HTTPException(404, "Meeting not found")
        msg_dicts = [x.to_dict() for x in m.messages]
        return {"messages": msg_dicts}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Meeting assignments
# ---------------------------------------------------------------------------

@router.get("/meetings/{meeting_id}/assignments")
async def get_meeting_assignments(
    meeting_id: str,
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """Get meeting assignments."""
    try:
        reg = getattr(hub, "meeting_registry", None)
        if reg is None:
            raise HTTPException(503, "meeting registry not initialized")
        m = reg.get(meeting_id)
        if not m:
            raise HTTPException(404, "Meeting not found")
        return {"assignments": [a.to_dict() for a in m.assignments]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Meeting CRUD
# ---------------------------------------------------------------------------

@router.post("/meetings")
async def manage_meetings(
    body: dict = Body(...),
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """Create a meeting."""
    try:
        reg = getattr(hub, "meeting_registry", None)
        if reg is None:
            raise HTTPException(503, "meeting registry not initialized")
        meeting = reg.create(body)
        return {"ok": True, "meeting": meeting.to_dict() if hasattr(meeting, "to_dict") else meeting}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Meeting management (start, close, cancel, participants, messages)
# ---------------------------------------------------------------------------

@router.post("/meetings/{meeting_id}")
async def manage_meeting(
    meeting_id: str,
    body: dict = Body(...),
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """Manage meeting operations (start, close, cancel, add/remove participants, etc.)."""
    try:
        reg = getattr(hub, "meeting_registry", None)
        if reg is None:
            raise HTTPException(503, "meeting registry not initialized")
        m = reg.get(meeting_id)
        if not m:
            raise HTTPException(404, "Meeting not found")

        action = body.get("action", "")

        if action == "start":
            m.start()
        elif action == "close":
            m.close(body.get("summary", ""))
        elif action == "cancel":
            m.cancel()
        elif action == "add_participant":
            m.add_participant(body.get("agent_id", ""))
        elif action == "remove_participant":
            m.remove_participant(body.get("agent_id", ""))
        elif action == "message":
            m.add_message(body)
        elif action == "assign":
            m.add_assignment(body)
        else:
            return {"ok": True}

        return {"ok": True, "meeting": m.to_dict() if hasattr(m, "to_dict") else {}}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
