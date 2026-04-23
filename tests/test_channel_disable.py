"""Channel enable/disable endpoints + test-skip behavior.

Core contract:
  * POST /channels/{id}/disable → enabled=false, poller stopped
  * POST /channels/{id}/enable  → enabled=true (and poller restarts if conditions met)
  * POST /channels/{id}/test on disabled channel → returns skipped=true
    WITHOUT calling adapter.test_connection()
"""
from __future__ import annotations

import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Build an isolated ChannelRouter with one in-memory channel.
    from app.channel import (
        ChannelRouter, ChannelConfig, ChannelType, create_adapter,
    )

    router = ChannelRouter.__new__(ChannelRouter)
    # Bypass the full init path (which tries to load from disk).
    import threading
    router._lock = threading.Lock()
    router._channels = {}
    router._adapters = {}
    router._agent_chat_fn = None
    router._event_log: list = []
    router._get_db = lambda: None
    router._save = lambda: None
    # Pre-seed a channel.
    ch = ChannelConfig(
        id="c-test",
        name="Test TG",
        channel_type=ChannelType.TELEGRAM,
        agent_id="a-alice",
        bot_token="fake",
        mode="polling",
        enabled=True,
    )
    router._channels[ch.id] = ch
    # Stub adapter so test_connection() is observable.
    fake_adapter = MagicMock()
    fake_adapter.is_polling = False
    fake_adapter.supports_polling = False
    fake_adapter.test_connection = MagicMock(return_value={
        "ok": True, "bot": "test_bot", "name": "TestBot",
    })
    fake_adapter.stop_polling = MagicMock()
    fake_adapter.start_polling = MagicMock()
    router._adapters[ch.id] = fake_adapter

    # Patch get_router() to return our isolated instance.
    import app.channel as ch_mod
    monkeypatch.setattr(ch_mod, "get_router", lambda: router)

    # Also patch the create_adapter so update_channel doesn't try to
    # rebuild a real adapter.
    monkeypatch.setattr(ch_mod, "create_adapter", lambda c: fake_adapter)

    # Build minimal FastAPI app with just the channels router.
    from app.api.deps.auth import get_current_user, CurrentUser

    async def _fake_user():
        return CurrentUser(user_id="u", role="superAdmin")

    from app.api.routers import channels as ch_router
    app = FastAPI()
    app.dependency_overrides[get_current_user] = _fake_user
    from app.api.deps.hub import get_hub as _get_hub
    app.dependency_overrides[_get_hub] = lambda: object()
    app.include_router(ch_router.router)

    with TestClient(app) as tc:
        tc.channel_router = router
        tc.fake_adapter = fake_adapter
        yield tc


# ── enable / disable ──────────────────────────────────────────


def test_disable_sets_enabled_false(client):
    r = client.post("/api/portal/channels/c-test/disable")
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert d["channel"]["enabled"] is False
    # Store state flipped.
    assert client.channel_router._channels["c-test"].enabled is False


def test_enable_sets_enabled_true(client):
    # First disable.
    client.post("/api/portal/channels/c-test/disable")
    # Then re-enable.
    r = client.post("/api/portal/channels/c-test/enable")
    assert r.status_code == 200
    assert r.json()["channel"]["enabled"] is True
    assert client.channel_router._channels["c-test"].enabled is True


def test_disable_missing_channel_404(client):
    r = client.post("/api/portal/channels/does-not-exist/disable")
    assert r.status_code == 404


def test_enable_missing_channel_404(client):
    r = client.post("/api/portal/channels/does-not-exist/enable")
    assert r.status_code == 404


# ── test endpoint short-circuit on disabled ──────────────────


def test_test_endpoint_skips_when_disabled(client):
    client.post("/api/portal/channels/c-test/disable")
    # Reset the mock so we can observe it NOT being called.
    client.fake_adapter.test_connection.reset_mock()
    r = client.post("/api/portal/channels/c-test/test")
    assert r.status_code == 200
    d = r.json()
    assert d.get("skipped") is True
    assert d.get("reason") == "channel_disabled"
    # Critical: adapter.test_connection MUST NOT have been called.
    client.fake_adapter.test_connection.assert_not_called()


def test_test_endpoint_runs_when_enabled(client):
    # Channel is enabled by default.
    client.fake_adapter.test_connection.reset_mock()
    r = client.post("/api/portal/channels/c-test/test")
    assert r.status_code == 200
    d = r.json()
    assert d.get("skipped") is not True
    assert d.get("success") is True
    client.fake_adapter.test_connection.assert_called_once()


def test_test_endpoint_after_reenable_resumes_checking(client):
    # Disable → test is skipped.
    client.post("/api/portal/channels/c-test/disable")
    client.fake_adapter.test_connection.reset_mock()
    r1 = client.post("/api/portal/channels/c-test/test")
    assert r1.json().get("skipped") is True
    client.fake_adapter.test_connection.assert_not_called()

    # Re-enable → next test actually runs.
    client.post("/api/portal/channels/c-test/enable")
    client.fake_adapter.test_connection.reset_mock()
    r2 = client.post("/api/portal/channels/c-test/test")
    assert r2.json().get("skipped") is not True
    client.fake_adapter.test_connection.assert_called_once()


# ── poller side-effect: disable stops current poller ─────────


def test_disable_stops_running_poller(client):
    # Simulate a poller currently running.
    client.fake_adapter.is_polling = True
    client.fake_adapter.stop_polling.reset_mock()

    client.post("/api/portal/channels/c-test/disable")
    # update_channel calls stop_polling before re-creating adapter;
    # the restart branch is gated by ch.enabled which is now False.
    client.fake_adapter.stop_polling.assert_called()
