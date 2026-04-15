"""
Tests for handler dispatch routing logic.

Verifies that try_handle() correctly routes paths to the right handler
functions (or returns False for unknown paths).

These tests use a mock handler/hub/auth so no real server is needed.
"""
import pytest


class FakeHandler:
    """Minimal BaseHTTPRequestHandler stub."""

    def __init__(self):
        self.responses = []
        self.headers = {}
        self.client_address = ("127.0.0.1", 12345)

    def _json(self, data, status=200):
        self.responses.append((data, status))


class FakeAuth:
    def audit(self, *a, **kw):
        pass


@pytest.fixture
def fake():
    return FakeHandler()


@pytest.fixture
def fake_auth():
    return FakeAuth()


# ---------------------------------------------------------------------------
# Handler registry tests (agents)
# ---------------------------------------------------------------------------

class TestAgentsDispatch:
    """Test that agents.try_handle routes known paths."""

    def test_unknown_path_returns_false(self, stub_hub, fake, fake_auth):
        from app.server.handlers.agents import try_handle
        result = try_handle(fake, "/api/portal/foobar", stub_hub, {}, fake_auth, "admin", "admin")
        assert result is False

    def test_create_path_is_handled(self, stub_hub, fake, fake_auth):
        from app.server.handlers.agents import try_handle
        result = try_handle(fake, "/api/portal/agent/create", stub_hub, {}, fake_auth, "admin", "admin")
        assert result is True

    def test_workspace_authorize_path(self, stub_hub, fake, fake_auth):
        from app.server.handlers.agents import try_handle
        result = try_handle(fake, "/api/portal/agent/workspace/authorize", stub_hub, {}, fake_auth, "admin", "admin")
        assert result is True

    def test_workspace_list_path(self, stub_hub, fake, fake_auth):
        from app.server.handlers.agents import try_handle
        result = try_handle(fake, "/api/portal/agent/workspace/list", stub_hub, {}, fake_auth, "admin", "admin")
        assert result is True


# ---------------------------------------------------------------------------
# Handler registry tests (projects)
# ---------------------------------------------------------------------------

class TestProjectsDispatch:
    """Test that projects.try_handle routes known paths."""

    def test_unknown_path_returns_false(self, stub_hub, fake, fake_auth):
        from app.server.handlers.projects import try_handle
        result = try_handle(fake, "/api/unknown/path", stub_hub, {}, fake_auth, "admin", "admin")
        assert result is False

    def test_projects_crud_path(self, stub_hub, fake, fake_auth):
        from app.server.handlers.projects import try_handle
        result = try_handle(fake, "/api/portal/projects", stub_hub, {"action": "create", "name": "test"}, fake_auth, "admin", "admin")
        assert result is True

    def test_projects_members_path(self, stub_hub, fake, fake_auth):
        from app.server.handlers.projects import try_handle
        result = try_handle(fake, "/api/portal/projects/p1/members", stub_hub, {"op": "add", "agent_id": "a1"}, fake_auth, "admin", "admin")
        assert result is True


# ---------------------------------------------------------------------------
# Handler registry tests (__init__)
# ---------------------------------------------------------------------------

class TestHandlerRegistryImports:
    """Verify the handler registry has the expected structure."""

    def test_public_handlers_has_auth(self):
        from app.server.handlers import PUBLIC_HANDLERS
        assert len(PUBLIC_HANDLERS) >= 1
        module_names = [h.__name__ for h in PUBLIC_HANDLERS]
        assert any("auth" in n for n in module_names)

    def test_domain_handlers_count(self):
        from app.server.handlers import DOMAIN_HANDLERS
        # Should have at least: config, hub_sync, channels, scheduler,
        # providers, agents, projects
        assert len(DOMAIN_HANDLERS) >= 7
