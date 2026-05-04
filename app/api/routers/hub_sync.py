"""Hub sync and inter-node communication router — agent sync, registration, messaging."""
from __future__ import annotations

import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Body

from ..deps.hub import get_hub
from ..deps.auth import CurrentUser, get_current_user
from ..deps.hub_auth import verify_hub_secret

logger = logging.getLogger("tudouclaw.api.hub_sync")

router = APIRouter(prefix="/api/hub", tags=["hub"])


# ---------------------------------------------------------------------------
# Local agents for inter-node sync
# ---------------------------------------------------------------------------

@router.get("/agents")
async def get_local_agents_for_sync(
    hub=Depends(get_hub),
    auth_tag: str = Depends(verify_hub_secret),
):
    """Return THIS hub's local agents for inter-node sync.

    Used by master's ``refresh_node`` to pull a worker's current
    agent list. Critical for cross-node chat: master's
    ``find_agent_node`` walks ``remote_nodes[*].agents`` looking
    for an agent_id, and that data only stays fresh thanks to this
    endpoint being polled.

    Auth: ``X-Hub-Secret`` (this is an inter-node call, not a UI
    request — JWT would require the master to log into every
    worker, which doesn't make sense).
    """
    try:
        # Walk hub.agents directly. The previous implementation
        # called ``hub.get_local_agents_for_sync()`` which never
        # existed on the Hub class — every request silently returned
        # an empty list, breaking master's view of remote agent lists
        # and making cross-node chat 404 on every send.
        agents = list(getattr(hub, "agents", {}).values()) or []
        out: list[dict] = []
        for a in agents:
            try:
                d = a.to_dict() if hasattr(a, "to_dict") else dict(a)
                # Mark the canonical node so master's UI labels it.
                d.setdefault("node_id", getattr(hub, "node_id", "local"))
                d["location"] = "local"
                out.append(d)
            except Exception:
                continue
        return {"agents": out}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("get_local_agents_for_sync failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/node/{node_id}")
async def unregister_node(
    node_id: str,
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """Unregister a remote node from this Hub.

    Parity with legacy ``DELETE /api/hub/node/{id}`` in
    ``portal_routes_post.py``. Used when a node is decommissioned or
    offline long enough that the operator wants it removed from the
    dashboard.
    """
    try:
        hub.unregister_node(node_id)
        try:
            from ...auth import get_auth
            auth = get_auth()
            auth.audit("delete_node", actor=user.user_id,
                       role=user.role, target=node_id)
        except Exception:
            pass
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Remote node registration
# ---------------------------------------------------------------------------

@router.post("/register")
async def register_remote_node(
    body: dict = Body(...),
    hub=Depends(get_hub),
    auth_tag: str = Depends(verify_hub_secret),
):
    """Register a remote node for synchronization.

    Authentication: ``X-Hub-Secret`` header (shared secret). NOT
    JWT — workers are processes, not users. The secret is configured
    via ``TUDOU_SECRET`` on the master and ``TUDOU_UPSTREAM_SECRET``
    on each worker.
    """
    try:
        node_id = body.get("node_id", "")
        # New flow uses 'endpoint'; old single-agent path used 'url'.
        endpoint = body.get("endpoint", "") or body.get("url", "")
        if not node_id:
            raise HTTPException(400, "Missing node_id")
        if not endpoint:
            logger.warning(
                "Node %s registered without callback URL — config "
                "dispatch and inter-node messages will fail",
                node_id,
            )

        name = body.get("name", "") or node_id
        agents = body.get("agents") or []
        # Direct path: use the public node_manager API (idempotent
        # register that overwrites existing entry).
        if hasattr(hub, "register_node"):
            hub.register_node(
                node_id=node_id,
                name=name,
                url=endpoint,
                agents=agents,
                secret="",  # never echo back the master's secret
            )
            logger.info(
                "Hub register: node=%s name=%s url=%s agents=%d auth=%s",
                node_id, name, endpoint, len(agents), auth_tag,
            )
            return {"ok": True, "node_id": node_id}
        # Older signature
        if hasattr(hub, "register_remote_node"):
            result = hub.register_remote_node(node_id, endpoint, body)
            return {"ok": True, "result": result}
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("register_remote_node failed")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Agent synchronization
# ---------------------------------------------------------------------------

@router.post("/sync")
async def sync_agents(
    body: dict = Body(...),
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """Sync agents with remote nodes."""
    try:
        node_id = body.get("node_id", "")
        agent_ids = body.get("agent_ids", [])

        if hasattr(hub, "sync_agents"):
            result = hub.sync_agents(node_id, agent_ids, body)
            return {"ok": True, "result": result}

        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Heartbeat (keepalive)
# ---------------------------------------------------------------------------

@router.post("/heartbeat")
async def send_heartbeat(
    body: dict = Body(default={}),
    hub=Depends(get_hub),
    auth_tag: str = Depends(verify_hub_secret),
):
    """Receive keepalive heartbeat from a downstream node.

    Authentication: ``X-Hub-Secret`` header — same as ``/register``.

    Side effects:
      - bump ``last_seen`` on the existing remote_nodes entry
      - if the node isn't registered yet (master restarted, or first
        heartbeat raced ahead of register), auto-upsert with whatever
        identity fields the body carries. Heartbeat thus serves as a
        recovery path for missed registrations.
    """
    try:
        node_id = body.get("node_id", "")
        if not node_id:
            raise HTTPException(400, "Missing node_id")

        existing = None
        if hasattr(hub, "remote_nodes"):
            existing = hub.remote_nodes.get(node_id)

        if existing is not None:
            # Bump last_seen — keeps the watchdog from flagging stale.
            try:
                existing.last_seen = time.time()
                if body.get("name"):
                    existing.name = body["name"]
                # Note: we deliberately don't update agents from heartbeat
                # — that's what /api/hub/sync is for. Heartbeat stays cheap.
            except Exception as e:
                logger.debug("heartbeat last_seen update failed: %s", e)
        else:
            # Auto-recover: master forgot us (restart with stale data?)
            # or our first register call lost. Re-create from heartbeat
            # body. URL may be empty, which is OK for a recovery path
            # — caller can issue a full /register later.
            if hasattr(hub, "register_node"):
                hub.register_node(
                    node_id=node_id,
                    name=body.get("name", "") or node_id,
                    url=body.get("url", "") or body.get("endpoint", ""),
                    agents=body.get("agents") or [],
                    secret="",
                )
                logger.info(
                    "Heartbeat from unknown node %s — auto-registered (auth=%s)",
                    node_id, auth_tag,
                )

        # Optional hub-level bookkeeping (some hubs track aggregate stats).
        if hasattr(hub, "send_heartbeat"):
            try:
                hub.send_heartbeat(node_id, body)
            except Exception as e:
                logger.debug("hub.send_heartbeat hook failed: %s", e)

        return {"ok": True, "node_id": node_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("send_heartbeat failed")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Inter-agent messaging
# ---------------------------------------------------------------------------

@router.post("/message")
async def send_inter_agent_message(
    body: dict = Body(...),
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """Send a message between agents across nodes."""
    try:
        from_agent_id = body.get("from_agent_id", "")
        to_agent_id = body.get("to_agent_id", "")
        message = body.get("message", "")
        if not from_agent_id or not to_agent_id or not message:
            raise HTTPException(400, "Missing from_agent_id, to_agent_id, or message")

        if hasattr(hub, "send_inter_agent_message"):
            result = hub.send_inter_agent_message(from_agent_id, to_agent_id, message, body)
            return {"ok": True, "result": result}

        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Broadcast messaging
# ---------------------------------------------------------------------------

@router.post("/broadcast")
async def broadcast_message(
    body: dict = Body(...),
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """Broadcast a message to all nodes."""
    try:
        message = body.get("message", "")
        message_type = body.get("type", "info")
        if not message:
            raise HTTPException(400, "Missing message")

        if hasattr(hub, "broadcast"):
            msgs = hub.broadcast(body.get("content", message))
            return {"ok": True, "sent": len(msgs) if isinstance(msgs, list) else 0}

        if hasattr(hub, "broadcast_message"):
            result = hub.broadcast_message(message, message_type=message_type, data=body)
            return {"ok": True, "result": result}

        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Node refresh
# ---------------------------------------------------------------------------

@router.post("/refresh")
async def refresh_node(
    body: dict = Body(...),
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """Refresh a remote node's agent data."""
    try:
        node_id = body.get("node_id", "")
        if not node_id:
            raise HTTPException(400, "Missing node_id")

        ok = hub.refresh_node(node_id) if hasattr(hub, "refresh_node") else False
        return {"ok": ok}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Message delivery (delegate to local agent)
# ---------------------------------------------------------------------------

@router.post("/deliver")
async def deliver_message(
    body: dict = Body(...),
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """Deliver a message to a local agent (trigger delegation)."""
    import threading

    try:
        to_id = body.get("to_agent", "")
        if not to_id:
            raise HTTPException(400, "Missing to_agent")

        agent = hub.get_agent(to_id) if hasattr(hub, "get_agent") else None
        if not agent:
            raise HTTPException(404, "Agent not found")

        content = body.get("content", "")
        from_id = body.get("from_agent", "remote")
        threading.Thread(
            target=agent.delegate, args=(content, from_id), daemon=True
        ).start()
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Config deployment: dispatch, batch-dispatch, apply, confirm
# ---------------------------------------------------------------------------

@router.post("/dispatch-config")
async def dispatch_config(
    body: dict = Body(...),
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """Push config to a specific agent on a specific node."""
    try:
        from ...hub import AgentConfigPayload

        node_id = body.get("node_id", "local")
        agent_id = body.get("agent_id", "")
        if not agent_id:
            raise HTTPException(400, "Missing agent_id")

        config = AgentConfigPayload.from_dict(body.get("config", {}))
        dep = hub.dispatch_config(node_id, agent_id, config)
        return dep.to_dict() if hasattr(dep, "to_dict") else {"ok": True, "result": dep}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch-dispatch-config")
async def batch_dispatch_config(
    body: dict = Body(...),
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """Push configs to multiple agents across nodes."""
    try:
        configs = body.get("configs", [])
        if not configs:
            raise HTTPException(400, "Missing configs")

        deps = hub.batch_dispatch_config(configs)
        return {"deployments": [d.to_dict() for d in deps]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/apply-config")
async def apply_config(
    body: dict = Body(...),
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """Receive config from hub (called by remote nodes, or by self for local)."""
    try:
        from ...hub import AgentConfigPayload

        deploy_id = body.get("deploy_id", "")
        agent_id = body.get("agent_id", "")
        config = AgentConfigPayload.from_dict(body.get("config", {}))
        ok = hub.apply_config_to_local_agent(agent_id, config) if hasattr(hub, "apply_config_to_local_agent") else False
        return {
            "ok": ok,
            "applied": ok,
            "deploy_id": deploy_id,
            "agent_id": agent_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/confirm-config")
async def confirm_config(
    body: dict = Body(...),
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """Remote node confirms config was applied."""
    try:
        deploy_id = body.get("deploy_id", "")
        success = body.get("success", True)
        error = body.get("error", "")
        ok = hub.confirm_config_applied(deploy_id, success, error) if hasattr(hub, "confirm_config_applied") else False
        return {"ok": ok}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/apply-node-config")
async def apply_node_config(
    body: dict = Body(...),
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """Receive config push from Hub (called on remote nodes)."""
    try:
        result = hub.apply_received_node_config(body) if hasattr(hub, "apply_received_node_config") else {"ok": False}
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Multi-agent orchestration
# ---------------------------------------------------------------------------

@router.post("/orchestrate")
async def orchestrate_agents(
    body: dict = Body(...),
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """Orchestrate a task across multiple agents."""
    try:
        task = body.get("task", "")
        agent_ids = body.get("agent_ids")
        if not task:
            raise HTTPException(400, "Missing task")

        results = hub.orchestrate(task, agent_ids) if hasattr(hub, "orchestrate") else {}
        return {"results": {k: v[:2000] if isinstance(v, str) else v for k, v in results.items()}}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Cross-node audit ingest
# ---------------------------------------------------------------------------

@router.post("/audit/ingest")
async def audit_ingest(
    body: dict = Body(...),
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """Ingest audit entries from remote nodes."""
    try:
        entries = body.get("entries") or []
        source_node = body.get("source_node", "")
        if not isinstance(entries, list):
            raise HTTPException(400, "entries must be a list")

        from ...auth import get_auth
        auth = get_auth()
        count = auth.ingest_remote_audit(entries, source_node=source_node) if hasattr(auth, "ingest_remote_audit") else 0
        return {"ok": True, "ingested": count}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
