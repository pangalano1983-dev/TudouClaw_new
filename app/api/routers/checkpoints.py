"""Checkpoint REST API — list / load / digest / restore / archive / delete.

Endpoints (portal-auth gated):
    GET    /api/portal/checkpoint/list             → filter by agent/scope/status
    GET    /api/portal/checkpoint/{id}             → full load
    GET    /api/portal/checkpoint/{id}/digest      → build-and-return digest text
    POST   /api/portal/checkpoint/{id}/restore     → mark status=restored + return digest
    POST   /api/portal/checkpoint/{id}/archive     → mark status=archived
    POST   /api/portal/checkpoint/{id}/digest/rebuild → recompute + persist
    GET    /api/portal/checkpoint/stats            → global store stats

Schema matches what `portal_bundle.js` consumes (see Day 7).
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..deps.auth import CurrentUser, get_current_user

from ... import checkpoint as ckpt_mod
from ... import digest as digest_mod

logger = logging.getLogger("tudouclaw.api.checkpoint")
router = APIRouter(prefix="/api/portal/checkpoint", tags=["checkpoint"])


def _ckpt_to_dict(c: "ckpt_mod.AgentCheckpoint") -> dict:
    return c.to_dict()


# ── list ───────────────────────────────────────────────────────────


@router.get("/list")
async def list_checkpoints(
    agent_id: str = Query("", description="Filter by agent id (optional)"),
    scope: Optional[str] = Query(None,
        description="agent | meeting | project_task"),
    scope_id: Optional[str] = Query(None,
        description="Scope-specific id (requires scope)"),
    status: Optional[str] = Query(None,
        description="open | restored | archived"),
    limit: int = Query(50, ge=1, le=500),
    user: CurrentUser = Depends(get_current_user),
):
    """Flexible listing. Passing scope+scope_id overrides agent_id."""
    store = ckpt_mod.get_store()
    if scope and scope_id:
        rows = store.list_for_scope(scope, scope_id,
                                    status=status, limit=limit)
    elif agent_id:
        rows = store.list_for_agent(agent_id, status=status,
                                    scope=scope, limit=limit)
    else:
        # No agent / no scope_id pair → surface an error rather than
        # silently returning the most recent globally (that could leak
        # cross-agent data in multi-tenant deployments).
        raise HTTPException(
            400, "Pass agent_id or scope+scope_id to filter the list.",
        )
    return {"count": len(rows),
            "checkpoints": [_ckpt_to_dict(r) for r in rows]}


@router.get("/stats")
async def checkpoint_stats(user: CurrentUser = Depends(get_current_user)):
    return ckpt_mod.get_store().stats()


# ── single-row ─────────────────────────────────────────────────────


@router.get("/{checkpoint_id}")
async def get_checkpoint(
    checkpoint_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    c = ckpt_mod.get_store().load(checkpoint_id)
    if c is None:
        raise HTTPException(404, f"checkpoint {checkpoint_id} not found")
    return _ckpt_to_dict(c)


@router.get("/{checkpoint_id}/digest")
async def get_digest(
    checkpoint_id: str,
    token_budget: int = Query(2000, ge=200, le=20000),
    use_stored: bool = Query(True,
        description="Return the digest already saved on the row if present"),
    user: CurrentUser = Depends(get_current_user),
):
    store = ckpt_mod.get_store()
    c = store.load(checkpoint_id)
    if c is None:
        raise HTTPException(404, f"checkpoint {checkpoint_id} not found")
    if use_stored and c.digest:
        return {
            "checkpoint_id": checkpoint_id,
            "text": c.digest,
            "source": "stored",
        }
    r = digest_mod.build_digest(c, token_budget=token_budget)
    return {
        "checkpoint_id": checkpoint_id,
        "text": r.text,
        "source": "computed",
        "token_estimate": r.token_estimate,
        "sections_included": r.sections_included,
        "truncated": r.truncated,
    }


# ── mutations ─────────────────────────────────────────────────────


class RebuildRequest(BaseModel):
    token_budget: int = 2000


@router.post("/{checkpoint_id}/digest/rebuild")
async def rebuild_digest(
    checkpoint_id: str,
    req: RebuildRequest = RebuildRequest(),
    user: CurrentUser = Depends(get_current_user),
):
    r = digest_mod.update_checkpoint_digest(
        checkpoint_id, token_budget=req.token_budget,
    )
    if r is None:
        raise HTTPException(404, f"checkpoint {checkpoint_id} not found")
    return {"checkpoint_id": checkpoint_id, **r.to_dict()}


@router.post("/{checkpoint_id}/restore")
async def restore_checkpoint(
    checkpoint_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """Flip status=restored and return the digest for the client to
    prepend onto the next LLM turn. Actual re-triggering of the agent /
    meeting is deferred to Day 8 — this endpoint is the UI-visible
    "open it" action."""
    store = ckpt_mod.get_store()
    c = store.load(checkpoint_id)
    if c is None:
        raise HTTPException(404, f"checkpoint {checkpoint_id} not found")
    ok = store.mark_restored(checkpoint_id)
    if not ok:
        raise HTTPException(500, "failed to mark restored")
    # Flag for chat-loop pickup (Day 8): next chat turn for this agent
    # will consume the digest and inject it as system context.
    try:
        store.set_metadata_flag(
            checkpoint_id, "pending_chat_delivery", True,
        )
    except Exception as _e:
        logger.warning("restore: set pending flag failed: %s", _e)
    # Produce a digest ON DEMAND (does not overwrite stored digest).
    r = digest_mod.build_digest(c)
    return {
        "checkpoint_id": checkpoint_id,
        "agent_id": c.agent_id,
        "scope": c.scope,
        "scope_id": c.scope_id,
        "digest": r.text,
        "token_estimate": r.token_estimate,
        "pending_chat_delivery": True,
    }


@router.post("/{checkpoint_id}/archive")
async def archive_checkpoint(
    checkpoint_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    ok = ckpt_mod.get_store().archive(checkpoint_id)
    if not ok:
        raise HTTPException(404, f"checkpoint {checkpoint_id} not found")
    return {"checkpoint_id": checkpoint_id, "status": ckpt_mod.STATUS_ARCHIVED}
