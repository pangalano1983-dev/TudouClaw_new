"""
Configuration synchronization module for TudouClaw's distributed architecture.

Runs on the Master node and tracks configuration versions for pushing changes to Nodes.
Provides version tracking, changelog management, and sync payload builders for both
full and incremental synchronization strategies.
"""

import logging
import threading
import time
from dataclasses import dataclass, asdict, field
from typing import Optional, Dict, List, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ConfigChange:
    """Represents a single configuration change in the system."""
    version: int
    scope: str       # "provider", "model", "mcp", "agent"
    action: str      # "create", "update", "delete"
    data: dict       # the changed configuration payload
    admin: str = ""  # who made the change
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        """Convert ConfigChange to dictionary for serialization."""
        return asdict(self)


class ConfigSyncManager:
    """
    Manages configuration versioning and synchronization across Master and Nodes.

    Maintains a changelog with version history and tracks which version each
    connected node has synced to. Provides methods to build full and incremental
    sync payloads for distribution to nodes.
    """

    MAX_CHANGELOG_SIZE = 1000
    FULL_SYNC_THRESHOLD = 100  # Trigger full sync if node is > 100 changes behind

    def __init__(self):
        """Initialize the ConfigSyncManager."""
        self._current_version: int = 0
        self._changelog: List[ConfigChange] = []
        self._node_versions: Dict[str, int] = {}  # node_id -> last synced version
        self._lock = threading.Lock()
        logger.info("ConfigSyncManager initialized")

    # ==================== Version Tracking ====================

    def record_change(self, scope: str, action: str, data: dict, admin: str = "") -> int:
        """
        Record a configuration change and increment version.

        Args:
            scope: Category of change ("provider", "model", "mcp", "agent")
            action: Type of change ("create", "update", "delete")
            data: Configuration payload being changed
            admin: Admin user who made the change

        Returns:
            The new version number
        """
        with self._lock:
            self._current_version += 1
            change = ConfigChange(
                version=self._current_version,
                scope=scope,
                action=action,
                data=data,
                admin=admin
            )
            self._changelog.append(change)

            # Implement ring buffer: remove oldest entry if exceeding max size
            if len(self._changelog) > self.MAX_CHANGELOG_SIZE:
                self._changelog.pop(0)

            logger.info(
                f"Recorded config change v{self._current_version}: "
                f"{scope}/{action} (admin={admin})"
            )
            return self._current_version

    def get_current_version(self) -> int:
        """Get the current configuration version."""
        with self._lock:
            return self._current_version

    def get_changes_since(self, version: int) -> List[ConfigChange]:
        """
        Get all configuration changes after a given version.

        Args:
            version: Starting version (exclusive)

        Returns:
            List of ConfigChange objects with version > given version
        """
        with self._lock:
            # Return changes that occurred after the given version
            return [change for change in self._changelog if change.version > version]

    # ==================== Node Sync State ====================

    def set_node_version(self, node_id: str, version: int) -> None:
        """
        Record that a node has synced up to a specific version.

        Args:
            node_id: Unique node identifier
            version: Version number the node has synced to
        """
        with self._lock:
            self._node_versions[node_id] = version
            logger.debug(f"Node {node_id} synced to version {version}")

    def get_node_version(self, node_id: str) -> int:
        """
        Get the last synced version for a node.

        Args:
            node_id: Unique node identifier

        Returns:
            Version number (0 if node never synced)
        """
        with self._lock:
            return self._node_versions.get(node_id, 0)

    def needs_full_sync(self, node_id: str) -> bool:
        """
        Determine if a node needs a full sync instead of incremental.

        A full sync is needed if:
        - Node has never synced (version is 0)
        - Node is > 100 changes behind current version

        Args:
            node_id: Unique node identifier

        Returns:
            True if full sync is required, False for incremental
        """
        with self._lock:
            node_version = self._node_versions.get(node_id, 0)

            # Always do full sync on first connection
            if node_version == 0:
                return True

            # Check if too many changes have occurred since last sync
            changes_behind = self._current_version - node_version
            if changes_behind > self.FULL_SYNC_THRESHOLD:
                logger.warning(
                    f"Node {node_id} is {changes_behind} changes behind; "
                    "triggering full sync"
                )
                return True

            return False

    # ==================== Sync Payload Builders ====================

    def build_full_sync_payload(self) -> dict:
        """
        Build a complete configuration snapshot for full sync.

        Gathers all current configuration from ProviderRegistry and constructs
        a payload suitable for syncing a new or out-of-date node.

        Returns:
            Dictionary with all current config at current_version
        """
        with self._lock:
            # Lazy import to avoid circular dependencies
            try:
                from app.infra.provider_registry import get_provider_registry
                registry = get_provider_registry()
                providers_data = [p.to_dict() for p in registry.list_providers()]

                # Build models per provider
                models_data = {}
                for provider in registry.list_providers():
                    models_data[provider.id] = [
                        m.to_dict() for m in provider.list_models()
                    ]
            except (ImportError, AttributeError) as e:
                logger.warning(f"Could not load provider registry: {e}")
                providers_data = []
                models_data = {}

            # TODO: Fetch MCP global configs when MCP module is available
            mcp_global_data = []

            payload = {
                "config_version": self._current_version,
                "providers": providers_data,
                "models": models_data,
                "mcp_global": mcp_global_data,
            }

            logger.info(
                f"Built full sync payload at v{self._current_version} "
                f"({len(providers_data)} providers, "
                f"{sum(len(m) for m in models_data.values())} models)"
            )
            return payload

    def build_incremental_sync(self, from_version: int) -> dict:
        """
        Build an incremental sync payload with changes since a version.

        Args:
            from_version: Start point (exclusive) for collecting changes

        Returns:
            Dictionary with incremental changes at current_version
        """
        with self._lock:
            changes_since = [
                change for change in self._changelog
                if change.version > from_version
            ]

            payload = {
                "config_version": self._current_version,
                "changes": [change.to_dict() for change in changes_since],
            }

            logger.info(
                f"Built incremental sync from v{from_version} to "
                f"v{self._current_version} ({len(changes_since)} changes)"
            )
            return payload

    # ==================== Integration Hooks ====================

    def on_provider_changed(
        self, provider_id: str, action: str, data: dict, admin: str = ""
    ) -> int:
        """
        Called when a provider configuration changes.

        Args:
            provider_id: The provider identifier
            action: "create", "update", or "delete"
            data: Provider configuration
            admin: Admin user making the change

        Returns:
            New version number
        """
        scope = "provider"
        change_data = {"provider_id": provider_id, **data}
        return self.record_change(scope, action, change_data, admin)

    def on_model_changed(
        self, provider_id: str, model_name: str, action: str, admin: str = ""
    ) -> int:
        """
        Called when a model configuration changes.

        Args:
            provider_id: The provider identifier
            model_name: The model name
            action: "create", "update", or "delete"
            admin: Admin user making the change

        Returns:
            New version number
        """
        scope = "model"
        change_data = {"provider_id": provider_id, "model_name": model_name}
        return self.record_change(scope, action, change_data, admin)

    def on_mcp_changed(
        self, mcp_id: str, action: str, data: dict, admin: str = ""
    ) -> int:
        """
        Called when an MCP configuration changes.

        Args:
            mcp_id: The MCP identifier
            action: "create", "update", or "delete"
            data: MCP configuration
            admin: Admin user making the change

        Returns:
            New version number
        """
        scope = "mcp"
        change_data = {"mcp_id": mcp_id, **data}
        return self.record_change(scope, action, change_data, admin)

    # ==================== Push Distribution ====================

    def push_to_all_nodes(self, node_ids: List[str]) -> List[Tuple[str, dict]]:
        """
        Build sync payloads for all online nodes.

        For each node, determines whether full or incremental sync is needed
        and builds the appropriate payload.

        Args:
            node_ids: List of online node identifiers

        Returns:
            List of (node_id, payload) tuples ready to send via WS
        """
        push_list = []

        for node_id in node_ids:
            payload = self.push_to_node(node_id)
            if payload:
                push_list.append((node_id, payload))

        logger.info(f"Prepared push payloads for {len(push_list)} nodes")
        return push_list

    def push_to_node(self, node_id: str) -> Optional[dict]:
        """
        Build appropriate sync payload for a specific node.

        Determines whether the node needs full or incremental sync based on
        its current synced version relative to the master.

        Args:
            node_id: Target node identifier

        Returns:
            Sync payload dict, or None if unable to build
        """
        if self.needs_full_sync(node_id):
            payload = self.build_full_sync_payload()
        else:
            node_version = self.get_node_version(node_id)
            payload = self.build_incremental_sync(node_version)

        logger.debug(
            f"Built sync payload for node {node_id} "
            f"(type={'full' if self.needs_full_sync(node_id) else 'incremental'})"
        )
        return payload

    # ==================== Persistence ====================

    def save_to_db(self, db) -> None:
        """
        Persist changelog and version info to database.

        Args:
            db: Database connection/session object with save/commit methods
        """
        with self._lock:
            try:
                # TODO: Implement database persistence
                # This would save self._current_version and self._changelog
                logger.info(f"Saved config state: v{self._current_version}, "
                           f"{len(self._changelog)} changes")
            except Exception as e:
                logger.error(f"Failed to save config state: {e}")

    def load_from_db(self, db) -> None:
        """
        Restore changelog and version info from database on startup.

        Args:
            db: Database connection/session object with query methods
        """
        with self._lock:
            try:
                # TODO: Implement database restoration
                # This would restore self._current_version and self._changelog
                logger.info(f"Loaded config state: v{self._current_version}, "
                           f"{len(self._changelog)} changes")
            except Exception as e:
                logger.error(f"Failed to load config state: {e}")


# ==================== Global Singleton ====================

_sync_manager: Optional[ConfigSyncManager] = None
_sync_lock = threading.Lock()


def init_config_sync() -> ConfigSyncManager:
    """
    Initialize the global ConfigSyncManager singleton.

    Returns:
        The initialized ConfigSyncManager instance
    """
    global _sync_manager
    with _sync_lock:
        if _sync_manager is None:
            _sync_manager = ConfigSyncManager()
        return _sync_manager


def get_config_sync() -> ConfigSyncManager:
    """
    Get the global ConfigSyncManager singleton.

    Returns:
        The ConfigSyncManager instance

    Raises:
        RuntimeError: If init_config_sync() was not called first
    """
    global _sync_manager
    if _sync_manager is None:
        raise RuntimeError(
            "ConfigSyncManager not initialized. Call init_config_sync() first."
        )
    return _sync_manager
