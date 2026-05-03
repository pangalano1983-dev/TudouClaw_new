"""Tests for multi-node agent creation.

Covers the proxy path: master receives /agent/create with node_id
pointing at a worker, forwards POST to that worker, returns the
worker's response. The single-master path (no node_id, or local) is
covered indirectly — these tests verify it's untouched.

Tests use mocked workers (no real HTTP), validating that the right
URL / headers / body get sent.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Cluster-secret resolution
# ---------------------------------------------------------------------------


def test_cluster_secret_prefers_upstream_hub_secret():
    """Worker side: upstream_hub_secret wins."""
    from app.hub._core import Hub
    hub = Hub.__new__(Hub)  # bypass __init__ — we just want the method
    hub.upstream_hub_secret = "from-upstream"
    with patch.dict("os.environ", {"TUDOU_SECRET": "from-env"}):
        assert hub._get_cluster_secret() == "from-upstream"


def test_cluster_secret_falls_back_to_env():
    """Master side: TUDOU_SECRET env is used."""
    from app.hub._core import Hub
    hub = Hub.__new__(Hub)
    hub.upstream_hub_secret = ""
    with patch.dict("os.environ", {"TUDOU_SECRET": "from-env-2"}):
        assert hub._get_cluster_secret() == "from-env-2"


def test_cluster_secret_falls_back_to_auth_singleton(monkeypatch):
    """Last resort: auth._shared_secret."""
    from app.hub._core import Hub
    hub = Hub.__new__(Hub)
    hub.upstream_hub_secret = ""
    monkeypatch.delenv("TUDOU_SECRET", raising=False)

    fake_auth = MagicMock()
    fake_auth._shared_secret = "from-auth"
    with patch("app.auth.get_auth", return_value=fake_auth):
        assert hub._get_cluster_secret() == "from-auth"


# ---------------------------------------------------------------------------
# proxy_create_agent — happy path + error cases
# ---------------------------------------------------------------------------


def test_proxy_create_agent_forwards_to_worker():
    """Master calls hub.proxy_create_agent → POST to worker URL with
    X-Hub-Secret header, body without node_id."""
    from app.hub._core import Hub
    from app.hub.types import RemoteNode

    hub = Hub.__new__(Hub)
    hub.upstream_hub_secret = ""
    hub.remote_nodes = {
        "worker-01": RemoteNode(
            node_id="worker-01",
            name="Shanghai Worker",
            url="http://worker-01.example.com:9090",
            agents=[],
            last_seen=1234567890.0,
            secret="",
        ),
    }
    # refresh_node not relevant here — stub it out
    hub.refresh_node = MagicMock()

    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {"ok": True, "agent": {"id": "a1", "name": "测试"}}

    with patch.dict("os.environ", {"TUDOU_SECRET": "cluster-secret"}), \
         patch("app.hub._core.http_requests.post", return_value=fake_resp) as mock_post:
        result = hub.proxy_create_agent(
            "worker-01",
            {"node_id": "worker-01", "name": "测试", "role": "general"},
        )

    assert result == {"ok": True, "agent": {"id": "a1", "name": "测试"}}
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    # URL points at worker
    assert call_args[0][0] == "http://worker-01.example.com:9090/api/portal/agent/create"
    # X-Hub-Secret header set
    assert call_args.kwargs["headers"]["X-Hub-Secret"] == "cluster-secret"
    # Body stripped of node_id (worker shouldn't recursively proxy)
    assert "node_id" not in call_args.kwargs["json"]
    assert call_args.kwargs["json"]["name"] == "测试"


def test_proxy_create_agent_unknown_node_raises_404():
    """Asking to create on a node that's not registered → HTTPException 404."""
    from app.hub._core import Hub
    from fastapi import HTTPException

    hub = Hub.__new__(Hub)
    hub.upstream_hub_secret = ""
    hub.remote_nodes = {}

    with pytest.raises(HTTPException) as exc:
        hub.proxy_create_agent("ghost-node", {"name": "x"})
    assert exc.value.status_code == 404


def test_proxy_create_agent_worker_error_propagates_status():
    """Worker returns 4xx/5xx → master returns same code."""
    from app.hub._core import Hub
    from app.hub.types import RemoteNode
    from fastapi import HTTPException

    hub = Hub.__new__(Hub)
    hub.upstream_hub_secret = ""
    hub.remote_nodes = {
        "worker-01": RemoteNode(
            node_id="worker-01", name="W", url="http://w:9090",
            agents=[], last_seen=1.0, secret="",
        ),
    }
    hub.refresh_node = MagicMock()

    fake_resp = MagicMock()
    fake_resp.status_code = 400
    fake_resp.text = "name too generic"

    with patch.dict("os.environ", {"TUDOU_SECRET": "s"}), \
         patch("app.hub._core.http_requests.post", return_value=fake_resp):
        with pytest.raises(HTTPException) as exc:
            hub.proxy_create_agent("worker-01", {"name": "claw"})

    assert exc.value.status_code == 400
    assert "name too generic" in exc.value.detail


def test_proxy_create_agent_unreachable_worker_raises_502():
    """Network error → 502 Bad Gateway."""
    from app.hub._core import Hub
    from app.hub.types import RemoteNode
    from fastapi import HTTPException

    hub = Hub.__new__(Hub)
    hub.upstream_hub_secret = ""
    hub.remote_nodes = {
        "worker-01": RemoteNode(
            node_id="worker-01", name="W", url="http://unreachable:9090",
            agents=[], last_seen=1.0, secret="",
        ),
    }
    hub.refresh_node = MagicMock()

    with patch.dict("os.environ", {"TUDOU_SECRET": "s"}), \
         patch(
             "app.hub._core.http_requests.post",
             side_effect=ConnectionError("DNS failed"),
         ):
        with pytest.raises(HTTPException) as exc:
            hub.proxy_create_agent("worker-01", {"name": "x"})

    assert exc.value.status_code == 502


# ---------------------------------------------------------------------------
# Dual auth dep
# ---------------------------------------------------------------------------


def test_dual_auth_jwt_path_unchanged(monkeypatch):
    """When Bearer token present, get_user_or_hub_proxy delegates to
    get_current_user (existing behaviour preserved)."""
    import asyncio
    from app.api.deps.dual_auth import get_user_or_hub_proxy
    from app.api.deps.auth import CurrentUser
    from fastapi.security import HTTPAuthorizationCredentials

    fake_user = CurrentUser(user_id="real_user", role="admin")
    fake_request = MagicMock()
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="some-jwt")

    async def fake_get_current_user(request, credentials):
        return fake_user

    with patch(
        "app.api.deps.dual_auth.get_current_user",
        side_effect=fake_get_current_user,
    ):
        result = asyncio.run(get_user_or_hub_proxy(fake_request, creds))

    assert result is fake_user


def test_dual_auth_hub_secret_path_returns_proxy_user(monkeypatch):
    """No JWT, valid X-Hub-Secret → returns synthetic hub_proxy user."""
    import asyncio
    from app.api.deps.dual_auth import get_user_or_hub_proxy

    fake_request = MagicMock()
    fake_request.headers = {"X-Hub-Secret": "cluster-secret"}

    async def fake_verify(request):
        return "hub_node"

    with patch(
        "app.api.deps.dual_auth.verify_hub_secret",
        side_effect=fake_verify,
    ):
        result = asyncio.run(get_user_or_hub_proxy(fake_request, None))

    assert result.user_id == "hub_proxy"
    assert result.role == "admin"  # never superAdmin
    assert result.claims.get("hub_proxy") is True


def test_dual_auth_no_creds_no_secret_raises_401():
    """No JWT, no X-Hub-Secret → 401."""
    import asyncio
    from app.api.deps.dual_auth import get_user_or_hub_proxy
    from fastapi import HTTPException

    fake_request = MagicMock()
    fake_request.headers = {}  # no X-Hub-Secret

    with pytest.raises(HTTPException) as exc:
        asyncio.run(get_user_or_hub_proxy(fake_request, None))
    assert exc.value.status_code == 401
