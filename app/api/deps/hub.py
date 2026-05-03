"""Hub singleton dependency — bridges FastAPI with existing TudouClaw core."""
from __future__ import annotations

import os
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...hub import Hub

logger = logging.getLogger("tudouclaw.api.deps")

_hub_instance: "Hub | None" = None


def init_hub() -> "Hub":
    """Initialize and return the Hub singleton.

    Called once during FastAPI lifespan startup.

    Env var pass-through:
      - TUDOU_NODE_ID    → Hub.node_id    (cluster-unique identifier;
                                            critical for multi-node —
                                            two workers with the same
                                            id collide in master's
                                            remote_nodes dict)
      - TUDOU_NODE_NAME  → Hub.node_name  (cosmetic, shown on banner/UI)
      - TUDOU_CLAW_DATA_DIR is read by Hub itself.

    If TUDOU_NODE_ID is unset on a worker (TUDOU_UPSTREAM_HUB present),
    we fall back to hostname instead of the literal "local" — workers
    must NOT all share id="local" or master's remote_nodes overwrites
    each new register on top of the last.
    """
    global _hub_instance
    if _hub_instance is not None:
        return _hub_instance

    try:
        from ...hub import Hub
        node_id = os.environ.get("TUDOU_NODE_ID", "").strip()
        node_name = os.environ.get("TUDOU_NODE_NAME", "")
        # Worker-mode auto-fallback: if the operator set TUDOU_UPSTREAM_HUB
        # but didn't pick an explicit id, derive one from hostname so
        # multiple workers don't all show up as "local".
        if not node_id and os.environ.get("TUDOU_UPSTREAM_HUB", "").strip():
            import socket
            node_id = socket.gethostname() or "worker"
        kwargs = {}
        if node_id:
            kwargs["node_id"] = node_id
        if node_name:
            kwargs["node_name"] = node_name
        _hub_instance = Hub(**kwargs) if kwargs else Hub()
        logger.info("Hub initialized: node_id=%s node_name=%s",
                    _hub_instance.node_id, _hub_instance.node_name)
    except Exception as e:
        logger.error("Failed to initialize Hub: %s", e)
        raise
    return _hub_instance


def shutdown_hub():
    """Clean up Hub on shutdown."""
    global _hub_instance
    if _hub_instance is not None:
        try:
            if hasattr(_hub_instance, "shutdown"):
                _hub_instance.shutdown()
            elif hasattr(_hub_instance, "close"):
                _hub_instance.close()
        except Exception as e:
            logger.warning("Hub shutdown error: %s", e)
        _hub_instance = None


def get_hub() -> "Hub":
    """FastAPI dependency: get the Hub singleton.

    Usage:
        @router.get("/api/portal/agents")
        async def list_agents(hub: Hub = Depends(get_hub)):
            ...
    """
    if _hub_instance is None:
        raise RuntimeError("Hub not initialized — did the lifespan fail?")
    return _hub_instance
