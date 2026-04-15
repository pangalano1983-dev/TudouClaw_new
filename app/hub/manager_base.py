"""
Base class for Hub manager modules.

Each manager holds a back-reference to the Hub instance it belongs to,
giving it access to shared state (agents dict, remote_nodes, etc.)
while encapsulating a single domain of responsibility.

Usage during gradual migration:
    1. Create a manager subclass (e.g. AgentManager).
    2. Move methods from Hub into the manager.
    3. On the Hub side, delegate to the manager:
           def create_agent(self, **kw):
               return self._agent_mgr.create_agent(**kw)
    4. Once all callers are updated, remove the Hub shim.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ._core import Hub

logger = logging.getLogger("tudou.hub")


class ManagerBase:
    """Thin base that every domain manager inherits from."""

    def __init__(self, hub: Hub) -> None:
        self._hub = hub

    # Convenience accessors so subclasses don't need ``self._hub.xxx``
    # everywhere.  Add more as needed during migration.

    @property
    def hub(self) -> Hub:
        return self._hub

    @property
    def agents(self):
        return self._hub.agents

    @property
    def remote_nodes(self):
        return self._hub.remote_nodes

    @property
    def _data_dir(self) -> str:
        return self._hub._data_dir

    @property
    def _db(self):
        return self._hub._db

    @property
    def _lock(self):
        return self._hub._lock
