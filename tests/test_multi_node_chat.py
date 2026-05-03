"""Tests for cross-node chat: proxy POST + SSE stream proxy.

The flow under test:

    UI                    Master                       Worker
    ──                    ──────                       ──────
    POST /chat ─────────► detects remote agent
                          POST /chat ─────────────────► creates ChatTask
                          ◄──────────── {"task_id":"abc"}
                          wraps as "n:worker-01:abc"
    ◄──── {"task_id":"n:..."}

    GET /stream/n:... ──► sees prefix
                          opens upstream SSE ──────────► stream events
                          ◄──── data: {...}
    ◄──── data: {...}     forwards chunks
                          ...
                          ◄──── data: [DONE]
    ◄──── data: [DONE]

These tests mock the worker (no real HTTP), validating prefix
construction, header propagation, and stream chunk forwarding.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Task-id prefix utilities
# ---------------------------------------------------------------------------


def test_split_remote_task_id_recognises_prefix():
    from app.api.routers.chat import _split_remote_task_id

    assert _split_remote_task_id("n:worker-01:abc123") == ("worker-01", "abc123")
    # Worker IDs may have hyphens / underscores
    assert _split_remote_task_id("n:node_shanghai_01:xyz") == ("node_shanghai_01", "xyz")


def test_split_remote_task_id_rejects_non_prefixed():
    from app.api.routers.chat import _split_remote_task_id

    assert _split_remote_task_id("plain_task_id") is None
    assert _split_remote_task_id("other:prefix:value") is None
    assert _split_remote_task_id("n:") is None        # malformed
    assert _split_remote_task_id("n::") is None       # empty parts
    assert _split_remote_task_id("n:worker:") is None # missing raw id


# ---------------------------------------------------------------------------
# _proxy_chat_to_worker — POST forwarding + task_id wrapping
# ---------------------------------------------------------------------------


def test_proxy_chat_wraps_task_id_with_node_prefix():
    """Master receives chat for a remote agent → forwards POST → wraps the
    returned task_id with ``n:<node_id>:`` so the SSE endpoint can route."""
    from app.api.routers.agents import _proxy_chat_to_worker

    fake_hub = MagicMock()
    fake_hub._get_cluster_secret = MagicMock(return_value="cluster-secret")
    fake_node = MagicMock()
    fake_node.node_id = "worker-01"
    fake_node.url = "http://worker-01:9090"

    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {
        "task_id": "raw_abc123",
        "status": "running",
        "attachments_saved": [],
    }

    with patch(
        "app.api.routers.agents._requests" if False else "requests.post",
        return_value=fake_resp,
    ) as mock_post:
        result = _proxy_chat_to_worker(
            fake_hub, fake_node, "agent_xyz",
            {"message": "hi", "extra_field": "v"},
        )

    # task_id wrapped with prefix
    assert result["task_id"] == "n:worker-01:raw_abc123"
    # node_id annotated for client awareness
    assert result["node_id"] == "worker-01"
    # Other fields untouched
    assert result["status"] == "running"

    # POST went to the worker's chat endpoint with the cluster secret
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "http://worker-01:9090/api/portal/agent/agent_xyz/chat"
    assert kwargs["headers"]["X-Hub-Secret"] == "cluster-secret"
    # Body forwarded as-is
    assert kwargs["json"]["message"] == "hi"
    assert kwargs["json"]["extra_field"] == "v"


def test_proxy_chat_passes_through_worker_error_status():
    """Worker 4xx → master raises HTTPException with the same code."""
    from app.api.routers.agents import _proxy_chat_to_worker
    from fastapi import HTTPException

    fake_hub = MagicMock()
    fake_hub._get_cluster_secret = MagicMock(return_value="s")
    fake_node = MagicMock()
    fake_node.node_id = "worker-01"
    fake_node.url = "http://w:9090"

    fake_resp = MagicMock()
    fake_resp.status_code = 409
    fake_resp.json.return_value = {"code": "NO_LLM_CONFIGURED", "message": "x"}

    with patch("requests.post", return_value=fake_resp):
        with pytest.raises(HTTPException) as exc:
            _proxy_chat_to_worker(fake_hub, fake_node, "a", {"message": "m"})

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "NO_LLM_CONFIGURED"


def test_proxy_chat_unreachable_worker_502():
    from app.api.routers.agents import _proxy_chat_to_worker
    from fastapi import HTTPException

    fake_hub = MagicMock()
    fake_hub._get_cluster_secret = MagicMock(return_value="s")
    fake_node = MagicMock()
    fake_node.node_id = "worker-01"
    fake_node.url = "http://unreachable:9090"

    with patch("requests.post", side_effect=ConnectionError("nope")):
        with pytest.raises(HTTPException) as exc:
            _proxy_chat_to_worker(fake_hub, fake_node, "a", {"message": "m"})

    assert exc.value.status_code == 502


def test_proxy_chat_no_task_id_in_response_does_not_break():
    """If the worker returns 200 but no task_id (unusual), don't crash;
    just pass through whatever shape the worker returned."""
    from app.api.routers.agents import _proxy_chat_to_worker

    fake_hub = MagicMock()
    fake_hub._get_cluster_secret = MagicMock(return_value="")
    fake_node = MagicMock()
    fake_node.node_id = "worker-01"
    fake_node.url = "http://w:9090"

    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {"status": "running"}  # no task_id

    with patch("requests.post", return_value=fake_resp):
        result = _proxy_chat_to_worker(fake_hub, fake_node, "a", {})

    # No task_id → no prefix wrap; node_id NOT added (client can't use it)
    assert "task_id" not in result
    assert "node_id" not in result
    assert result["status"] == "running"


# ---------------------------------------------------------------------------
# SSE stream proxy
# ---------------------------------------------------------------------------


def test_proxy_sse_stream_unknown_node_404():
    """Asking to stream from a node that's not registered → 404."""
    import asyncio
    from app.api.routers.chat import _proxy_sse_stream
    from fastapi import HTTPException

    fake_hub = MagicMock()
    fake_hub.remote_nodes = {}  # empty
    fake_hub._get_cluster_secret = MagicMock(return_value="s")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(_proxy_sse_stream(fake_hub, "ghost-node", "raw_id", 0))
    assert exc.value.status_code == 404
