"""
Hub domain types — dataclass models shared across hub manager modules.

Extracted from the monolithic hub module to allow independent import
without pulling in the full Hub class and its heavy dependency graph.
"""
import time
import uuid
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Remote node representation
# ---------------------------------------------------------------------------

@dataclass
class RemoteNode:
    node_id: str
    name: str
    url: str                    # e.g. "http://192.168.1.100:8081"
    agents: list[dict] = field(default_factory=list)
    last_seen: float = field(default_factory=time.time)
    status: str = "online"
    secret: str = ""            # shared secret for auth

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "name": self.name,
            "url": self.url,
            "agent_count": len(self.agents),
            "agents": self.agents,
            "last_seen": self.last_seen,
            "status": self.status,
        }


# ---------------------------------------------------------------------------
# Node-scoped configuration (secrets, tokens, env per node)
# ---------------------------------------------------------------------------

@dataclass
class NodeConfigItem:
    """A single config entry scoped to a specific node.
    Examples: market_api_token, deploy_ssh_key, db_connection_string.
    """
    key: str                          # config key, e.g. "market_api_token"
    value: str = ""                   # the actual value (may be secret)
    description: str = ""             # human-readable description
    category: str = "general"         # general | credentials | integration | custom
    is_secret: bool = False           # if True, value is masked in UI
    created_by: str = "admin"         # who created this config
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    synced: bool = False              # whether this has been synced to the node
    synced_at: float = 0.0

    def to_dict(self, mask: bool = False) -> dict:
        return {
            "key": self.key,
            "value": ("********" if self.is_secret and mask else self.value),
            "description": self.description,
            "category": self.category,
            "is_secret": self.is_secret,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "synced": self.synced,
            "synced_at": self.synced_at,
        }

    @staticmethod
    def from_dict(d: dict) -> "NodeConfigItem":
        return NodeConfigItem(
            key=d.get("key", ""),
            value=d.get("value", ""),
            description=d.get("description", ""),
            category=d.get("category", "general"),
            is_secret=d.get("is_secret", False),
            created_by=d.get("created_by", "admin"),
            created_at=d.get("created_at", 0),
            updated_at=d.get("updated_at", 0),
            synced=d.get("synced", False),
            synced_at=d.get("synced_at", 0),
        )


@dataclass
class NodeConfig:
    """All config items scoped to a single node."""
    node_id: str
    items: dict[str, NodeConfigItem] = field(default_factory=dict)  # key -> item

    def set_item(self, key: str, value: str, description: str = "",
                 category: str = "general", is_secret: bool = False,
                 created_by: str = "admin") -> NodeConfigItem:
        if key in self.items:
            item = self.items[key]
            item.value = value
            if description:
                item.description = description
            if category:
                item.category = category
            item.is_secret = is_secret
            item.updated_at = time.time()
            item.synced = False  # needs re-sync
        else:
            item = NodeConfigItem(
                key=key, value=value, description=description,
                category=category, is_secret=is_secret,
                created_by=created_by,
            )
            self.items[key] = item
        return item

    def get_item(self, key: str) -> NodeConfigItem | None:
        return self.items.get(key)

    def delete_item(self, key: str) -> bool:
        return self.items.pop(key, None) is not None

    def to_dict(self, mask: bool = False) -> dict:
        return {
            "node_id": self.node_id,
            "items": {k: v.to_dict(mask=mask) for k, v in self.items.items()},
        }

    @staticmethod
    def from_dict(d: dict) -> "NodeConfig":
        nc = NodeConfig(node_id=d.get("node_id", ""))
        for k, v in d.get("items", {}).items():
            nc.items[k] = NodeConfigItem.from_dict(v)
        return nc


# ---------------------------------------------------------------------------
# Agent configuration deployment
# ---------------------------------------------------------------------------

@dataclass
class AgentConfigPayload:
    """Configuration payload that can be pushed to any agent on any node."""
    agent_id: str = ""
    name: str = ""
    role: str = ""
    model: str = ""
    provider: str = ""
    system_prompt: str = ""
    profile: dict = field(default_factory=dict)
    working_dir: str = ""
    # Partial update: only non-empty fields are applied
    partial: bool = True

    def to_dict(self) -> dict:
        d = {k: v for k, v in {
            "agent_id": self.agent_id,
            "name": self.name,
            "role": self.role,
            "model": self.model,
            "provider": self.provider,
            "system_prompt": self.system_prompt,
            "profile": self.profile,
            "working_dir": self.working_dir,
            "partial": self.partial,
        }.items() if v or k == "partial"}
        return d

    @staticmethod
    def from_dict(d: dict) -> "AgentConfigPayload":
        return AgentConfigPayload(
            agent_id=d.get("agent_id", ""),
            name=d.get("name", ""),
            role=d.get("role", ""),
            model=d.get("model", ""),
            provider=d.get("provider", ""),
            system_prompt=d.get("system_prompt", ""),
            profile=d.get("profile", {}),
            working_dir=d.get("working_dir", ""),
            partial=d.get("partial", True),
        )


@dataclass
class ConfigDeployment:
    """Tracks a config push to a node/agent with confirmation status."""
    deploy_id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    node_id: str = ""
    agent_id: str = ""
    config: dict = field(default_factory=dict)
    status: str = "pending"   # pending | dispatched | ack | applied | failed | timeout
    error: str = ""
    created_at: float = field(default_factory=time.time)
    dispatched_at: float = 0.0
    acked_at: float = 0.0
    applied_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "deploy_id": self.deploy_id,
            "node_id": self.node_id,
            "agent_id": self.agent_id,
            "config": self.config,
            "status": self.status,
            "error": self.error,
            "created_at": self.created_at,
            "dispatched_at": self.dispatched_at,
            "acked_at": self.acked_at,
            "applied_at": self.applied_at,
            "duration": (
                (self.applied_at or self.acked_at or time.time())
                - self.created_at
            ),
        }


# ---------------------------------------------------------------------------
# Inter-agent message
# ---------------------------------------------------------------------------

@dataclass
class AgentMessage:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    from_agent: str = ""
    to_agent: str = ""
    from_agent_name: str = ""  # Resolved display name
    to_agent_name: str = ""    # Resolved display name
    content: str = ""
    msg_type: str = "task"
    timestamp: float = field(default_factory=time.time)
    status: str = "pending"

    def to_dict(self) -> dict:
        return {
            "id": self.id, "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "from_agent_name": self.from_agent_name,
            "to_agent_name": self.to_agent_name,
            "content": self.content,
            "msg_type": self.msg_type, "timestamp": self.timestamp,
            "status": self.status,
        }
