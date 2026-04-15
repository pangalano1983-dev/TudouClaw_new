"""
Node lifecycle manager for TudouClaw's distributed architecture.

Runs on the Master node and manages all connected Nodes.
Handles node registration, heartbeats, agent routing, and fault detection.
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class NodeInfo:
    """
    Information about a Node in the TudouClaw cluster.

    Attributes:
        node_id: Unique identifier for the node
        name: Human-readable node name
        url: WebSocket connection URL (empty until connected)
        status: Node status - "online", "offline", or "draining"
        capabilities: Dict with gpu, cpu_cores, ram_gb, local_models, max_agents
        agent_count: Current number of agents on this node
        agent_ids: List of agent IDs assigned to this node
        config_version: Last synced configuration version
        last_seen: Unix timestamp of last heartbeat
        ws_connected: Whether WebSocket connection is active
        registered_at: Unix timestamp when node was registered
    """
    node_id: str
    name: str
    url: str = ""
    status: str = "offline"  # online, offline, draining
    capabilities: dict = field(default_factory=dict)
    agent_count: int = 0
    agent_ids: list = field(default_factory=list)
    config_version: int = 0
    last_seen: float = 0.0
    ws_connected: bool = False
    registered_at: float = 0.0

    def to_dict(self) -> dict:
        """Convert NodeInfo to dictionary for serialization."""
        return {
            "node_id": self.node_id,
            "name": self.name,
            "url": self.url,
            "status": self.status,
            "capabilities": self.capabilities,
            "agent_count": self.agent_count,
            "agent_ids": self.agent_ids,
            "config_version": self.config_version,
            "last_seen": self.last_seen,
            "ws_connected": self.ws_connected,
            "registered_at": self.registered_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "NodeInfo":
        """Construct NodeInfo from dictionary."""
        return cls(
            node_id=data["node_id"],
            name=data["name"],
            url=data.get("url", ""),
            status=data.get("status", "offline"),
            capabilities=data.get("capabilities", {}),
            agent_count=data.get("agent_count", 0),
            agent_ids=data.get("agent_ids", []),
            config_version=data.get("config_version", 0),
            last_seen=data.get("last_seen", 0.0),
            ws_connected=data.get("ws_connected", False),
            registered_at=data.get("registered_at", 0.0),
        )


@dataclass
class AgentRoute:
    """
    Route information for an Agent.

    Maps an agent to its assigned node and tracks its execution state.

    Attributes:
        agent_id: Unique identifier for the agent
        node_id: ID of the node where agent is assigned
        status: Agent status - "idle", "busy", "error", or "offline"
        model: Model name agent is running
        provider: Provider name (e.g., "openai", "anthropic")
        updated_at: Unix timestamp of last status update
    """
    agent_id: str
    node_id: str
    status: str = "idle"  # idle, busy, error, offline
    model: str = ""
    provider: str = ""
    updated_at: float = 0.0

    def to_dict(self) -> dict:
        """Convert AgentRoute to dictionary for serialization."""
        return {
            "agent_id": self.agent_id,
            "node_id": self.node_id,
            "status": self.status,
            "model": self.model,
            "provider": self.provider,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AgentRoute":
        """Construct AgentRoute from dictionary."""
        return cls(
            agent_id=data["agent_id"],
            node_id=data["node_id"],
            status=data.get("status", "idle"),
            model=data.get("model", ""),
            provider=data.get("provider", ""),
            updated_at=data.get("updated_at", 0.0),
        )


class NodeManager:
    """
    Manages the lifecycle of Nodes and agent routing in TudouClaw cluster.

    Runs on the Master node. Handles:
    - Node registration and discovery
    - Heartbeat monitoring and fault detection
    - Agent assignment and migration
    - Load balancing and node selection
    - Node state synchronization

    Thread-safe via RLock.
    """

    def __init__(self):
        """Initialize the NodeManager."""
        self._nodes: dict[str, NodeInfo] = {}
        self._agent_routes: dict[str, AgentRoute] = {}
        self._lock = threading.RLock()
        logger.info("NodeManager initialized")

    # ==================== Node Lifecycle Methods ====================

    def register_node(
        self, node_id: str, name: str, capabilities: dict, secret: str = ""
    ) -> Optional[NodeInfo]:
        """
        Register a new node with the cluster.

        Args:
            node_id: Unique node identifier
            name: Human-readable node name
            capabilities: Node capabilities dict (gpu, cpu_cores, ram_gb, etc)
            secret: Registration secret (for validation - empty for dev)

        Returns:
            NodeInfo if successful, None if node_id already registered
        """
        with self._lock:
            if node_id in self._nodes:
                logger.warning(f"Node {node_id} already registered")
                return None

            now = time.time()
            node_info = NodeInfo(
                node_id=node_id,
                name=name,
                status="offline",
                capabilities=capabilities,
                registered_at=now,
                last_seen=now,
            )
            self._nodes[node_id] = node_info
            logger.info(
                f"Registered node {node_id} ({name}) "
                f"with capabilities: {capabilities}"
            )
            return node_info

    def unregister_node(self, node_id: str) -> list[str]:
        """
        Unregister a node and orphan its agents.

        Args:
            node_id: ID of node to unregister

        Returns:
            List of agent IDs that were orphaned
        """
        with self._lock:
            if node_id not in self._nodes:
                logger.warning(f"Cannot unregister unknown node {node_id}")
                return []

            node_info = self._nodes[node_id]
            orphaned_agents = list(node_info.agent_ids)

            # Mark agents as offline
            for agent_id in orphaned_agents:
                if agent_id in self._agent_routes:
                    self._agent_routes[agent_id].status = "offline"

            # Remove node
            del self._nodes[node_id]
            logger.info(
                f"Unregistered node {node_id}, orphaned {len(orphaned_agents)} agents"
            )
            return orphaned_agents

    def update_heartbeat(
        self, node_id: str, agent_statuses: list[dict]
    ) -> bool:
        """
        Update node heartbeat and sync agent states.

        Called when node sends heartbeat. Updates last_seen timestamp
        and syncs agent status information.

        Args:
            node_id: ID of heartbeating node
            agent_statuses: List of dicts with agent status info
                [{agent_id, status, model, provider}, ...]

        Returns:
            True if update successful, False if node not found
        """
        with self._lock:
            if node_id not in self._nodes:
                logger.warning(f"Heartbeat from unknown node {node_id}")
                return False

            node_info = self._nodes[node_id]
            now = time.time()
            node_info.last_seen = now
            node_info.status = "online"
            node_info.ws_connected = True

            # Update agent statuses
            for agent_status in agent_statuses:
                agent_id = agent_status.get("agent_id")
                if agent_id not in self._agent_routes:
                    continue

                route = self._agent_routes[agent_id]
                route.status = agent_status.get("status", "idle")
                route.model = agent_status.get("model", "")
                route.provider = agent_status.get("provider", "")
                route.updated_at = now

            logger.debug(f"Heartbeat from {node_id}, {len(agent_statuses)} agents")
            return True

    def get_node(self, node_id: str) -> Optional[NodeInfo]:
        """
        Get node information.

        Args:
            node_id: Node ID to look up

        Returns:
            NodeInfo or None if not found
        """
        with self._lock:
            return self._nodes.get(node_id)

    def list_nodes(self, status: Optional[str] = None) -> list[NodeInfo]:
        """
        List all nodes, optionally filtered by status.

        Args:
            status: Filter by status ("online", "offline", "draining")
                   If None, return all nodes

        Returns:
            List of NodeInfo objects
        """
        with self._lock:
            nodes = list(self._nodes.values())
            if status:
                nodes = [n for n in nodes if n.status == status]
            return nodes

    def get_online_nodes(self) -> list[NodeInfo]:
        """
        Get all online nodes.

        Returns:
            List of NodeInfo objects with status="online"
        """
        return self.list_nodes(status="online")

    # ==================== Agent Routing Methods ====================

    def assign_agent(
        self, agent_id: str, node_id: str, model: str = "", provider: str = ""
    ) -> Optional[AgentRoute]:
        """
        Assign an agent to a node.

        Args:
            agent_id: Agent ID
            node_id: Target node ID
            model: Model name agent runs
            provider: Provider name

        Returns:
            AgentRoute if successful, None if node not found
        """
        with self._lock:
            if node_id not in self._nodes:
                logger.error(f"Cannot assign agent to unknown node {node_id}")
                return None

            now = time.time()
            route = AgentRoute(
                agent_id=agent_id,
                node_id=node_id,
                model=model,
                provider=provider,
                status="idle",
                updated_at=now,
            )
            self._agent_routes[agent_id] = route

            # Update node tracking
            node_info = self._nodes[node_id]
            if agent_id not in node_info.agent_ids:
                node_info.agent_ids.append(agent_id)
                node_info.agent_count += 1

            logger.info(f"Assigned agent {agent_id} to node {node_id}")
            return route

    def remove_agent_route(self, agent_id: str) -> bool:
        """
        Remove an agent from the routing table.

        Args:
            agent_id: Agent ID to remove

        Returns:
            True if removed, False if not found
        """
        with self._lock:
            if agent_id not in self._agent_routes:
                logger.warning(f"Cannot remove route for unknown agent {agent_id}")
                return False

            route = self._agent_routes[agent_id]
            node_id = route.node_id

            # Update node tracking
            if node_id in self._nodes:
                node_info = self._nodes[node_id]
                if agent_id in node_info.agent_ids:
                    node_info.agent_ids.remove(agent_id)
                    node_info.agent_count = max(0, node_info.agent_count - 1)

            del self._agent_routes[agent_id]
            logger.info(f"Removed route for agent {agent_id}")
            return True

    def get_agent_route(self, agent_id: str) -> Optional[AgentRoute]:
        """
        Look up an agent's route.

        Args:
            agent_id: Agent ID

        Returns:
            AgentRoute or None if not found
        """
        with self._lock:
            return self._agent_routes.get(agent_id)

    def get_agents_on_node(self, node_id: str) -> list[AgentRoute]:
        """
        Get all agents assigned to a node.

        Args:
            node_id: Node ID

        Returns:
            List of AgentRoute objects
        """
        with self._lock:
            if node_id not in self._nodes:
                return []
            node_info = self._nodes[node_id]
            routes = []
            for agent_id in node_info.agent_ids:
                if agent_id in self._agent_routes:
                    routes.append(self._agent_routes[agent_id])
            return routes

    def find_best_node(
        self, model: str = "", required_gpu: bool = False
    ) -> Optional[NodeInfo]:
        """
        Find the best node for agent assignment.

        Uses simple load balancing: prefers online nodes with fewest agents,
        with affinity toward nodes that support the target model.

        Args:
            model: Preferred model (optional affinity)
            required_gpu: Whether GPU is required

        Returns:
            Best NodeInfo or None if no suitable node found
        """
        with self._lock:
            candidates = []
            for node in self._nodes.values():
                if node.status != "online":
                    continue
                if required_gpu and not node.capabilities.get("gpu"):
                    continue
                candidates.append(node)

            if not candidates:
                return None

            # Sort by agent count (ascending) then by model affinity
            def sort_key(node):
                # Primary: fewest agents
                load = node.agent_count
                # Secondary: model affinity (prefer nodes with model)
                affinity = 0
                if model and model not in node.capabilities.get("local_models", []):
                    affinity = 1
                return (load, affinity)

            candidates.sort(key=sort_key)
            best_node = candidates[0]
            logger.debug(f"Selected node {best_node.node_id} for model {model}")
            return best_node

    # ==================== Agent Migration ====================

    def migrate_agent(
        self, agent_id: str, from_node: str, to_node: str
    ) -> tuple[Optional[AgentRoute], Optional[AgentRoute]]:
        """
        Migrate an agent from one node to another.

        Args:
            agent_id: Agent ID
            from_node: Source node ID
            to_node: Target node ID

        Returns:
            Tuple (old_route, new_route) or (None, None) if migration failed
        """
        with self._lock:
            if agent_id not in self._agent_routes:
                logger.error(f"Cannot migrate unknown agent {agent_id}")
                return None, None

            if from_node not in self._nodes or to_node not in self._nodes:
                logger.error(f"Cannot migrate to unknown nodes")
                return None, None

            route = self._agent_routes[agent_id]
            if route.node_id != from_node:
                logger.error(
                    f"Agent {agent_id} not on source node {from_node}"
                )
                return None, None

            old_route = AgentRoute.from_dict(route.to_dict())

            # Update route
            route.node_id = to_node
            route.status = "idle"
            route.updated_at = time.time()

            # Update node tracking
            from_node_info = self._nodes[from_node]
            to_node_info = self._nodes[to_node]

            if agent_id in from_node_info.agent_ids:
                from_node_info.agent_ids.remove(agent_id)
                from_node_info.agent_count = max(0, from_node_info.agent_count - 1)

            if agent_id not in to_node_info.agent_ids:
                to_node_info.agent_ids.append(agent_id)
                to_node_info.agent_count += 1

            logger.info(f"Migrated agent {agent_id} from {from_node} to {to_node}")
            return old_route, route

    # ==================== Fault Detection ====================

    def check_health(self, timeout: float = 30.0) -> list[str]:
        """
        Check node health based on heartbeat timeout.

        Returns list of node IDs that missed heartbeat deadline.
        Does NOT modify node status - that's handled by handle_node_failure.

        Args:
            timeout: Heartbeat timeout in seconds

        Returns:
            List of node IDs with missed heartbeats
        """
        with self._lock:
            now = time.time()
            unhealthy_nodes = []
            for node_id, node_info in self._nodes.items():
                if node_info.status == "offline":
                    continue
                if now - node_info.last_seen > timeout:
                    unhealthy_nodes.append(node_id)
                    logger.warning(
                        f"Node {node_id} missed heartbeat "
                        f"(last seen {now - node_info.last_seen:.1f}s ago)"
                    )
            return unhealthy_nodes

    def handle_node_failure(self, node_id: str) -> list[str]:
        """
        Handle failure of a node.

        Marks node as offline and returns orphaned agent IDs.
        Should be called after check_health detects unhealthy nodes.

        Args:
            node_id: ID of failed node

        Returns:
            List of orphaned agent IDs
        """
        with self._lock:
            if node_id not in self._nodes:
                logger.warning(f"Cannot fail unknown node {node_id}")
                return []

            node_info = self._nodes[node_id]
            orphaned_agents = list(node_info.agent_ids)

            # Mark node offline
            node_info.status = "offline"
            node_info.ws_connected = False

            # Mark agents offline
            for agent_id in orphaned_agents:
                if agent_id in self._agent_routes:
                    self._agent_routes[agent_id].status = "offline"

            logger.error(
                f"Node {node_id} marked offline, orphaned {len(orphaned_agents)} agents"
            )
            return orphaned_agents

    # ==================== Persistence ====================

    def to_dict(self) -> dict:
        """
        Serialize NodeManager state to dictionary.

        Returns:
            Dict with nodes and agent_routes
        """
        with self._lock:
            return {
                "nodes": {
                    node_id: node.to_dict()
                    for node_id, node in self._nodes.items()
                },
                "agent_routes": {
                    agent_id: route.to_dict()
                    for agent_id, route in self._agent_routes.items()
                },
            }

    def from_dict(self, data: dict) -> None:
        """
        Restore NodeManager state from dictionary.

        Args:
            data: Dict with nodes and agent_routes
        """
        with self._lock:
            self._nodes = {
                node_id: NodeInfo.from_dict(node_data)
                for node_id, node_data in data.get("nodes", {}).items()
            }
            self._agent_routes = {
                agent_id: AgentRoute.from_dict(route_data)
                for agent_id, route_data in data.get("agent_routes", {}).items()
            }
            logger.info(
                f"Restored {len(self._nodes)} nodes "
                f"and {len(self._agent_routes)} agent routes"
            )

    # ==================== Statistics ====================

    def get_cluster_stats(self) -> dict:
        """
        Get cluster statistics.

        Returns:
            Dict with cluster metrics:
            - total_nodes: Total nodes registered
            - online_nodes: Nodes currently online
            - offline_nodes: Nodes currently offline
            - draining_nodes: Nodes in draining status
            - total_agents: Total agents in routes
            - busy_agents: Agents with status="busy"
            - idle_agents: Agents with status="idle"
            - error_agents: Agents with status="error"
            - offline_agents: Agents with status="offline"
            - total_capabilities: Aggregated capabilities
        """
        with self._lock:
            total_nodes = len(self._nodes)
            online_nodes = sum(1 for n in self._nodes.values() if n.status == "online")
            offline_nodes = sum(1 for n in self._nodes.values() if n.status == "offline")
            draining_nodes = sum(1 for n in self._nodes.values() if n.status == "draining")

            total_agents = len(self._agent_routes)
            busy_agents = sum(
                1 for r in self._agent_routes.values() if r.status == "busy"
            )
            idle_agents = sum(
                1 for r in self._agent_routes.values() if r.status == "idle"
            )
            error_agents = sum(
                1 for r in self._agent_routes.values() if r.status == "error"
            )
            offline_agents = sum(
                1 for r in self._agent_routes.values() if r.status == "offline"
            )

            # Aggregate capabilities
            total_gpu = sum(
                n.capabilities.get("gpu", 0) for n in self._nodes.values()
            )
            total_cpu_cores = sum(
                n.capabilities.get("cpu_cores", 0) for n in self._nodes.values()
            )
            total_ram_gb = sum(
                n.capabilities.get("ram_gb", 0) for n in self._nodes.values()
            )

            return {
                "total_nodes": total_nodes,
                "online_nodes": online_nodes,
                "offline_nodes": offline_nodes,
                "draining_nodes": draining_nodes,
                "total_agents": total_agents,
                "busy_agents": busy_agents,
                "idle_agents": idle_agents,
                "error_agents": error_agents,
                "offline_agents": offline_agents,
                "total_gpu": total_gpu,
                "total_cpu_cores": total_cpu_cores,
                "total_ram_gb": total_ram_gb,
            }


# ==================== Global Singleton ====================

_node_manager: Optional[NodeManager] = None
_manager_lock = threading.Lock()


def init_node_manager() -> NodeManager:
    """
    Initialize the global NodeManager singleton.

    Returns:
        NodeManager instance
    """
    global _node_manager
    with _manager_lock:
        if _node_manager is None:
            _node_manager = NodeManager()
        return _node_manager


def get_node_manager() -> NodeManager:
    """
    Get the global NodeManager singleton.

    Returns:
        NodeManager instance (initializes if needed)
    """
    global _node_manager
    if _node_manager is None:
        return init_node_manager()
    return _node_manager
