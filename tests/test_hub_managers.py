"""
Tests for Hub manager classes — verify they can be instantiated and
have the expected method signatures.
"""
import pytest

from app.hub.types import (
    RemoteNode, NodeConfigItem, NodeConfig,
    AgentConfigPayload, ConfigDeployment, AgentMessage,
)
from app.hub.manager_base import ManagerBase
from app.hub.persistence import PersistenceManager
from app.hub.agent_manager import AgentManager
from app.hub.node_manager import NodeManager
from app.hub.project_manager import ProjectManager
from app.hub.message_bus import MessageBus


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class TestHubTypes:
    def test_remote_node_creation(self):
        node = RemoteNode(node_id="n1", name="Node1", url="http://localhost:8081", secret="s")
        assert node.node_id == "n1"
        assert node.url == "http://localhost:8081"

    def test_agent_message_creation(self):
        msg = AgentMessage(
            from_agent="a1", to_agent="a2",
            content="hello", msg_type="chat",
        )
        assert msg.from_agent == "a1"
        assert msg.to_agent == "a2"

    def test_agent_config_payload(self):
        payload = AgentConfigPayload(agent_id="a1")
        assert payload.agent_id == "a1"


# ---------------------------------------------------------------------------
# Manager base
# ---------------------------------------------------------------------------

class TestManagerBase:
    def test_base_requires_hub(self):
        class FakeHub:
            agents = {}
            remote_nodes = {}
            _lock = None
            _data_dir = "/tmp"
            _db = None

        hub = FakeHub()
        mgr = ManagerBase(hub)
        assert mgr._hub is hub
        assert mgr.agents is hub.agents


# ---------------------------------------------------------------------------
# Manager method existence
# ---------------------------------------------------------------------------

class TestPersistenceManagerMethods:
    def test_has_load_save_agents(self):
        assert callable(getattr(PersistenceManager, "_load_agents", None))
        assert callable(getattr(PersistenceManager, "_save_agents", None))

    def test_has_load_save_projects(self):
        assert callable(getattr(PersistenceManager, "_load_projects", None))
        assert callable(getattr(PersistenceManager, "_save_projects", None))

    def test_has_load_save_nodes(self):
        assert callable(getattr(PersistenceManager, "_load_remote_nodes", None))
        assert callable(getattr(PersistenceManager, "_save_remote_nodes", None))


class TestAgentManagerMethods:
    EXPECTED_METHODS = [
        "create_agent", "get_agent", "remove_agent", "list_agents",
        "apply_persona", "wake_up_agent", "list_agent_pending_tasks",
        "get_agent_cost", "get_agent_history", "get_all_costs",
        "save_agent_session", "load_agent_session",
        "save_engine_session", "restore_engine_session",
        "compact_agent_memory",
    ]

    @pytest.mark.parametrize("method_name", EXPECTED_METHODS)
    def test_method_exists(self, method_name):
        assert callable(getattr(AgentManager, method_name, None)), \
            f"AgentManager missing method: {method_name}"


class TestNodeManagerMethods:
    EXPECTED_METHODS = [
        "register_node", "unregister_node", "list_nodes",
        "find_agent_node", "is_local_agent",
        "refresh_node", "refresh_all_nodes",
        "proxy_remote_agent_get", "proxy_remote_agent_post",
        "dispatch_config", "batch_dispatch_config",
        "proxy_chat", "proxy_chat_sync",
    ]

    @pytest.mark.parametrize("method_name", EXPECTED_METHODS)
    def test_method_exists(self, method_name):
        assert callable(getattr(NodeManager, method_name, None)), \
            f"NodeManager missing method: {method_name}"


class TestProjectManagerMethods:
    EXPECTED_METHODS = [
        "create_project", "get_project", "remove_project", "list_projects",
        "project_chat", "project_assign_task",
        "start_workflow", "abort_workflow", "get_workflow", "list_workflows",
    ]

    @pytest.mark.parametrize("method_name", EXPECTED_METHODS)
    def test_method_exists(self, method_name):
        assert callable(getattr(ProjectManager, method_name, None)), \
            f"ProjectManager missing method: {method_name}"


class TestMessageBusMethods:
    EXPECTED_METHODS = [
        "send_message", "route_message", "broadcast",
        "get_messages", "_deliver_local", "_deliver_remote",
    ]

    @pytest.mark.parametrize("method_name", EXPECTED_METHODS)
    def test_method_exists(self, method_name):
        assert callable(getattr(MessageBus, method_name, None)), \
            f"MessageBus missing method: {method_name}"
