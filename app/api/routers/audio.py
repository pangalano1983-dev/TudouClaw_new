"""Audio events router — TTS/STT event stream."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps.hub import get_hub
from ..deps.auth import CurrentUser, get_current_user

logger = logging.getLogger("tudouclaw.api.audio")

router = APIRouter(prefix="/api/portal", tags=["audio"])


@router.get("/audio/events")
async def get_audio_events(
    since: float = Query(0, description="Timestamp to fetch events after"),
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """Get audio TTS/STT events since a timestamp."""
    try:
        from ...server.tools import get_audio_events
        events = get_audio_events(since=int(since))
    except (ImportError, AttributeError):
        events = []
    return {"events": events}
