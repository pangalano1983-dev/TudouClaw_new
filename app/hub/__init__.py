"""
app.hub — Hub package.

This package is the refactored home of the Hub class and its supporting
types.  All public names that were previously importable from the flat
``app.hub`` module are re-exported here so that existing code like::

    from app.hub import Hub, get_hub, init_hub
    from app.hub import AgentConfigPayload

continues to work without modification.

Package layout:
    __init__.py       — this file (re-exports for backward compat)
    _core.py          — Hub class, get_hub(), init_hub() singleton helpers
    types.py          — dataclass models (RemoteNode, AgentMessage, ...)
    manager_base.py   — base class for domain managers
    agent_manager.py  — agent CRUD, session/engine, cost tracking
    node_manager.py   — remote node registration / config dispatch / proxy
    project_manager.py — project CRUD / workflow orchestration
    message_bus.py    — inter-agent message routing
    persistence.py    — load/save serialisation for agents, nodes, projects
"""

# --- Domain types (lightweight, no heavy deps) ---
from .types import (  # noqa: F401
    RemoteNode,
    NodeConfigItem,
    NodeConfig,
    AgentConfigPayload,
    ConfigDeployment,
    AgentMessage,
)

# --- Hub class and singleton accessors ---
from ._core import Hub, get_hub, init_hub  # noqa: F401

# --- Domain managers (migrated from _core.py Hub methods) ---
from .manager_base import ManagerBase  # noqa: F401
from .agent_manager import AgentManager  # noqa: F401
from .node_manager import NodeManager  # noqa: F401
from .project_manager import ProjectManager  # noqa: F401
from .message_bus import MessageBus  # noqa: F401
from .persistence import PersistenceManager  # noqa: F401

__all__ = [
    # Types
    "RemoteNode",
    "NodeConfigItem",
    "NodeConfig",
    "AgentConfigPayload",
    "ConfigDeployment",
    "AgentMessage",
    # Hub
    "Hub",
    "get_hub",
    "init_hub",
    # Managers
    "ManagerBase",
    "AgentManager",
    "NodeManager",
    "ProjectManager",
    "MessageBus",
    "PersistenceManager",
]
