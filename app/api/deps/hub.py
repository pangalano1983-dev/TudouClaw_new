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
    Reuses the existing Hub initialization logic from the old portal server.
    """
    global _hub_instance
    if _hub_instance is not None:
        return _hub_instance

    try:
        from ...hub import Hub
        _hub_instance = Hub()
        logger.info("Hub initialized: node_id=%s", _hub_instance.node_id)
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
