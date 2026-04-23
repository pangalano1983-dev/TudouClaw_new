"""Progress SSE — expose the ProgressBus over Server-Sent Events.

Endpoints:
    GET  /api/portal/progress/stream?channel=<pattern>&replay=1&since=<seq>
        → text/event-stream of ProgressFrame JSON
        channel = "plan:<id>" | "agent:<id>" | "tool:<session>" | "global" |
                  any pattern ending in "*"

    GET  /api/portal/progress/stats
        → JSON stats (subscribers, channels, total_published, channel_sizes)

Design notes:
- SSE chosen over WebSocket: unidirectional flow (bus → client), simpler,
  browser EventSource has auto-reconnect built in.
- Client sends `Last-Event-ID` header on reconnect; we parse that as the
  `since` seq and replay from there. Standard SSE behaviour.
- Heartbeat every 25s keeps intermediaries (proxies / browsers) from
  killing the connection on quiet channels.
"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from ..deps.auth import CurrentUser, get_current_user

from ...progress_bus import get_bus, ProgressFrame

logger = logging.getLogger("tudouclaw.api.progress")
router = APIRouter(prefix="/api/portal/progress", tags=["progress"])


@router.get("/stream")
async def stream_progress(
    request: Request,
    channel: str = Query("global", description="Channel pattern to subscribe to"),
    replay: int = Query(0, description="1 = seed with recent ring buffer"),
    since: int | None = Query(None, description="Only replay frames with seq > this"),
    user: CurrentUser = Depends(get_current_user),
):
    """Subscribe to live progress frames via Server-Sent Events.

    Uses Last-Event-ID header (standard SSE reconnect mechanism) if the
    client didn't explicitly pass ?since — lets EventSource handle drops
    transparently.
    """
    # If client sent Last-Event-ID (auto-set by browser EventSource on
    # reconnect), use it as the `since` floor. Explicit query param wins.
    if since is None:
        hdr = request.headers.get("last-event-id") or request.headers.get("Last-Event-ID")
        if hdr:
            try:
                since = int(hdr)
            except ValueError:
                since = None

    bus = get_bus()
    sub = bus.subscribe(
        channel_pattern=channel,
        replay=bool(replay) or since is not None,
        replay_since_seq=since,
    )

    async def event_iter():
        try:
            # Run the blocking queue.get in a thread so the asyncio event
            # loop stays responsive — we still want to detect client
            # disconnect promptly via request.is_disconnected().
            loop = asyncio.get_event_loop()
            while True:
                # Poll disconnect every heartbeat interval
                if await request.is_disconnected():
                    return
                frame: ProgressFrame | None = await loop.run_in_executor(
                    None, sub.next, 5.0,  # 5s wait
                )
                if frame is None:
                    # Keepalive comment — doesn't bump EventSource's id
                    yield ": keepalive\n\n"
                    continue
                # SSE frame format:
                #   id: <seq>\n
                #   event: <kind>\n
                #   data: <json>\n\n
                # `id` lets browser auto-set Last-Event-ID on reconnect.
                lines = [
                    f"id: {frame.seq}",
                    f"event: {frame.kind}",
                    f"data: {frame.to_json()}",
                    "", "",
                ]
                yield "\n".join(lines)
        finally:
            bus.unsubscribe(sub)

    headers = {
        "Cache-Control": "no-cache, no-transform",
        "Content-Type": "text/event-stream; charset=utf-8",
        # Tell reverse proxies not to buffer (nginx in particular).
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_iter(), headers=headers,
                              media_type="text/event-stream")


@router.get("/stats")
async def stats(user: CurrentUser = Depends(get_current_user)):
    return get_bus().stats()
