"""
Shared pytest fixtures for TudouClaw test suite.
"""
import sys
from pathlib import Path

import pytest

# Ensure the project root is on sys.path so `import app` works
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Lightweight stubs — heavy modules (LLM, DB) should never be loaded in
# unit tests.  Fixtures below provide minimal fakes.
# ---------------------------------------------------------------------------

class _StubAgent:
    """Minimal stub satisfying the interface handlers expect."""

    def __init__(self, agent_id: str = "test-agent", **kw):
        self.id = agent_id
        self.name = kw.get("name", "Test Agent")
        self.role = kw.get("role", "general")
        self.model = kw.get("model", "")
        self.provider = kw.get("provider", "")
        self.working_dir = kw.get("working_dir", "/tmp/test")
        self.system_prompt = kw.get("system_prompt", "")
        self.events = []
        self.tasks = []
        self.status = "idle"
        self.profile = type("P", (), {"to_dict": lambda self: {}})()

    def to_dict(self):
        return {"id": self.id, "name": self.name, "role": self.role}


class _StubProject:
    """Minimal project stub."""

    def __init__(self, project_id: str = "test-proj"):
        self.id = project_id
        self.name = "Test Project"
        self.members = []
        self.tasks = []
        self.milestones = []
        self.goals = []
        self.deliverables = []
        self.issues = []
        self.messages = []

    def to_dict(self):
        return {"id": self.id, "name": self.name}


class _StubHub:
    """Hub fake — returns stubs for any get_agent / get_project call."""

    def __init__(self):
        self.node_id = "test-node"
        self.node_name = "TestNode"
        self.agents = {"a1": _StubAgent("a1")}
        self.remote_nodes = {}
        self.projects = {"p1": _StubProject("p1")}

    def create_agent(self, **kw):
        agent = _StubAgent(agent_id=kw.get("name", "new"), **kw)
        self.agents[agent.id] = agent
        return agent

    def get_agent(self, agent_id):
        return self.agents.get(agent_id)

    def get_project(self, project_id):
        return self.projects.get(project_id)

    def list_agents(self):
        return list(self.agents.values())

    def list_projects(self):
        return list(self.projects.values())

    def _save_agents(self):
        pass

    def _save_projects(self):
        pass


@pytest.fixture
def stub_hub():
    return _StubHub()


@pytest.fixture
def stub_agent():
    return _StubAgent()


@pytest.fixture
def stub_project():
    return _StubProject()
