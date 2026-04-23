"""Inbox REST API — list/read/ack/reply persistent inbox messages.

Endpoints (all require portal auth):
    GET    /api/portal/inbox/count                → unread counts (per agent or global)
    GET    /api/portal/inbox/list?agent_id=...    → list messages for an agent
    GET    /api/portal/inbox/thread/<thread_id>   → full thread
    POST   /api/portal/inbox/ack                  → mark message(s) as acked
    POST   /api/portal/inbox/reply                → send a reply (persists + hub-mirror)
    GET    /api/portal/inbox/stats                → global stats

The UI inbox tab + unread badge consumes these. Portal clients carry
the viewer identity in the `agent_id` query / body field (the UI knows
which agent the user is looking at).
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..deps.auth import CurrentUser, get_current_user

from ...inbox import get_store

logger = logging.getLogger("tudouclaw.api.inbox")
router = APIRouter(prefix="/api/portal/inbox", tags=["inbox"])


# ── helpers ─────────────────────────────────────────────────────────


def _msg_to_dict(m) -> dict:
    return {
        "id": m.id,
        "to_agent": m.to_agent,
        "from_agent": m.from_agent,
        "content": m.content,
        "thread_id": m.thread_id,
        "reply_to": m.reply_to,
        "priority": m.priority,
        "state": m.state,
        "created_at": m.created_at,
        "read_at": m.read_at,
        "acked_at": m.acked_at,
        "ttl_s": m.ttl_s,
        "metadata": dict(m.metadata or {}),
    }


# ── GET endpoints ───────────────────────────────────────────────────


@router.get("/count")
async def inbox_count(
    agent_id: str = Query("", description="Agent id; empty → aggregate across hub"),
    user: CurrentUser = Depends(get_current_user),
):
    """Return unread counts. If agent_id is empty, sums across every
    registered agent in the hub — handy for a global badge."""
    store = get_store()
    if agent_id:
        return {"agent_id": agent_id, "unread": store.unread_count(agent_id)}
    # Aggregate across all known agents.
    try:
        from ...hub import get_hub
        hub = get_hub()
        counts = {aid: store.unread_count(aid) for aid in hub.agents.keys()}
    except Exception as e:
        logger.warning("inbox count aggregate failed: %s", e)
        counts = {}
    return {
        "agent_id": "",
        "unread": sum(counts.values()),
        "per_agent": counts,
    }


@router.get("/list")
async def inbox_list(
    agent_id: str = Query(..., description="Which agent's inbox to view"),
    limit: int = Query(50, ge=1, le=500),
    include_read: bool = Query(True),
    include_acked: bool = Query(False),
    user: CurrentUser = Depends(get_current_user),
):
    """List messages for an agent, newest states surfaced first:
    unread → read → (optionally) acked."""
    store = get_store()
    out: list[dict] = []

    unread = store.fetch_unread(agent_id, limit=limit)
    out.extend(_msg_to_dict(m) for m in unread)

    remaining = limit - len(out)
    if include_read and remaining > 0:
        try:
            with store._lock:
                cur = store._conn.execute(
                    "SELECT id FROM inbox_messages WHERE to_agent=? "
                    "AND state='read' ORDER BY created_at DESC LIMIT ?",
                    (agent_id, remaining),
                )
                for row in cur.fetchall():
                    m = store.get_by_id(row["id"])
                    if m:
                        out.append(_msg_to_dict(m))
        except Exception as e:
            logger.debug("inbox_list read-peek failed: %s", e)

    remaining = limit - len(out)
    if include_acked and remaining > 0:
        try:
            with store._lock:
                cur = store._conn.execute(
                    "SELECT id FROM inbox_messages WHERE to_agent=? "
                    "AND state='acked' ORDER BY created_at DESC LIMIT ?",
                    (agent_id, remaining),
                )
                for row in cur.fetchall():
                    m = store.get_by_id(row["id"])
                    if m:
                        out.append(_msg_to_dict(m))
        except Exception as e:
            logger.debug("inbox_list acked-peek failed: %s", e)

    return {
        "agent_id": agent_id,
        "count": len(out),
        "unread_count": len(unread),
        "messages": out,
    }


@router.get("/thread/{thread_id}")
async def inbox_thread(
    thread_id: str,
    limit: int = Query(100, ge=1, le=500),
    user: CurrentUser = Depends(get_current_user),
):
    store = get_store()
    msgs = store.get_thread(thread_id, limit=limit)
    return {
        "thread_id": thread_id,
        "count": len(msgs),
        "messages": [_msg_to_dict(m) for m in msgs],
    }


@router.get("/stats")
async def inbox_stats(user: CurrentUser = Depends(get_current_user)):
    return get_store().stats()


# ── POST endpoints ──────────────────────────────────────────────────


class AckRequest(BaseModel):
    agent_id: str
    message_ids: list[str]


@router.post("/ack")
async def inbox_ack(
    req: AckRequest,
    user: CurrentUser = Depends(get_current_user),
):
    if not req.message_ids:
        raise HTTPException(400, "message_ids is required")
    store = get_store()
    n = store.mark_acked(req.message_ids, req.agent_id)
    return {
        "requested": len(req.message_ids),
        "acked": n,
        "skipped": len(req.message_ids) - n,
    }


class ReadRequest(BaseModel):
    agent_id: str
    message_ids: list[str]


@router.post("/mark_read")
async def inbox_mark_read(
    req: ReadRequest,
    user: CurrentUser = Depends(get_current_user),
):
    if not req.message_ids:
        raise HTTPException(400, "message_ids is required")
    store = get_store()
    n = store.mark_read(req.message_ids, req.agent_id)
    return {
        "requested": len(req.message_ids),
        "marked_read": n,
        "skipped": len(req.message_ids) - n,
    }


class ReplyRequest(BaseModel):
    agent_id: str               # sender identity (the viewer, acting as this agent)
    message_id: str             # the original inbox id being replied to
    content: str
    priority: str = "normal"
    ttl_s: int = 0


@router.post("/reply")
async def inbox_reply(
    req: ReplyRequest,
    user: CurrentUser = Depends(get_current_user),
):
    if not req.content:
        raise HTTPException(400, "content is required")
    if not req.message_id:
        raise HTTPException(400, "message_id is required")

    store = get_store()
    orig = store.get_by_id(req.message_id)
    if orig is None:
        raise HTTPException(404, f"message '{req.message_id}' not found")
    if orig.to_agent != req.agent_id:
        raise HTTPException(
            403,
            f"cannot reply: message was addressed to {orig.to_agent}, "
            f"not {req.agent_id}",
        )

    target = orig.from_agent
    thread = orig.thread_id or orig.id
    new_id = store.send(
        to_agent=target,
        from_agent=req.agent_id,
        content=req.content,
        thread_id=thread,
        reply_to=req.message_id,
        priority=req.priority or "normal",
        ttl_s=int(req.ttl_s or 0),
        metadata={"msg_type": "reply",
                  "source": "portal_inbox_ui",
                  "in_reply_to": req.message_id},
    )

    # Mirror into the live hub channel (parallels tool_reply_message).
    try:
        from ...hub import get_hub
        hub = get_hub()
        route = getattr(hub, "route_message", None)
        if callable(route):
            route(req.agent_id, target, req.content, msg_type="reply",
                  source="portal_inbox_ui")
    except Exception as e:
        logger.debug("portal reply hub-mirror skipped: %s", e)

    return {
        "new_id": new_id,
        "thread_id": thread,
        "to_agent": target,
        "from_agent": req.agent_id,
    }
