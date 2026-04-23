"""Agent abort button — user-visible feedback + both abort signals flipped.

The old ``agentAbort`` JS just silently posted to the backend and
``console.log``'d the kill count. Users saw no bubble, no progress-bar
change, and (because the server only flipped ``abort_registry`` but
not ``chat_task.aborted``) the LLM loop kept running for 20-60s more.

This pass locks:
  * Backend endpoint flips BOTH ``abort_registry`` AND every active
    ``ChatTask``'s aborted flag owned by the agent.
  * Endpoint returns an honest summary (``killed_pids`` +
    ``chat_tasks_aborted``) so the UI can render "killed N subprocs".
  * Already-terminal tasks (completed/failed/aborted) are skipped.
  * Frontend agentAbort has the four things that were missing: an
    immediate system card, SSE/progress-bar teardown, a POST to the
    per-task /abort, and an updated card on response.
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ── Backend: /agent/{id}/abort flips BOTH signals ────────────────


def _make_app(agent_id, active_tasks):
    """Spin up a tiny FastAPI app with the real agents router."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.routers.agents import router
    from app.api.deps.auth import get_current_user, CurrentUser
    from app.api.deps.hub import get_hub as _get_hub

    agent = SimpleNamespace(id=agent_id, name="test")
    hub = SimpleNamespace(
        get_agent=lambda aid: agent if aid == agent_id else None,
        agents={agent_id: agent},
    )

    async def fake_user():
        return CurrentUser(user_id="u", role="superAdmin")

    app = FastAPI()
    app.dependency_overrides[get_current_user] = fake_user
    app.dependency_overrides[_get_hub] = lambda: hub
    app.include_router(router)
    return app, active_tasks


def _fake_chat_task(tid, status="streaming"):
    """Mutable stub — tracks whether abort() was called."""
    from app.chat_task import ChatTaskStatus
    t = SimpleNamespace(
        id=tid,
        status={
            "queued": ChatTaskStatus.QUEUED,
            "thinking": ChatTaskStatus.THINKING,
            "streaming": ChatTaskStatus.STREAMING,
            "tool_exec": ChatTaskStatus.TOOL_EXEC,
            "completed": ChatTaskStatus.COMPLETED,
            "failed": ChatTaskStatus.FAILED,
            "aborted": ChatTaskStatus.ABORTED,
        }[status],
        aborted=False,
    )
    def _do_abort():
        t.aborted = True
        t.status = ChatTaskStatus.ABORTED
    t.abort = _do_abort
    return t


def test_agent_abort_flips_both_abort_registry_and_chat_tasks():
    """The endpoint must call abort_registry.abort AND task.abort() on
    every active chat task. Without the task-level flip the LLM loop
    keeps running for one whole iteration."""
    from fastapi.testclient import TestClient
    from unittest.mock import patch

    app, _ = _make_app("a1", [])
    t1 = _fake_chat_task("task-aaa", "streaming")
    t2 = _fake_chat_task("task-bbb", "thinking")

    fake_mgr = SimpleNamespace(
        get_agent_tasks=lambda aid: [t1, t2] if aid == "a1" else [],
    )

    registry_called_with = {}
    def fake_abort(key, grace_s=2.0):
        registry_called_with["key"] = key
        return {"key": key, "found": True,
                "killed_pids": [1234, 5678],
                "failed_pids": [], "aborted_now": True}

    with patch("app.abort_registry.abort", side_effect=fake_abort), \
         patch("app.abort_registry.agent_key",
               side_effect=lambda aid: "agent:" + aid), \
         patch("app.chat_task.get_chat_task_manager",
               return_value=fake_mgr), \
         TestClient(app) as c:
        r = c.post("/api/portal/agent/a1/abort")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] is True
    # abort_registry called with the agent key
    assert registry_called_with["key"] == "agent:a1"
    # killed_pids propagated
    assert len(d["abort"]["killed_pids"]) == 2
    # BOTH active chat tasks were aborted
    assert set(d["chat_tasks_aborted"]) == {"task-aaa", "task-bbb"}
    assert t1.aborted is True
    assert t2.aborted is True


def test_agent_abort_skips_already_terminal_tasks():
    """Completed / failed / aborted tasks must not be re-aborted.
    Flipping aborted on a completed task corrupts the history tab."""
    from fastapi.testclient import TestClient
    from unittest.mock import patch

    app, _ = _make_app("a1", [])
    t_live = _fake_chat_task("live", "streaming")
    t_done = _fake_chat_task("done", "completed")
    t_failed = _fake_chat_task("failed", "failed")
    t_aborted = _fake_chat_task("already", "aborted")

    fake_mgr = SimpleNamespace(
        get_agent_tasks=lambda aid: [t_live, t_done, t_failed, t_aborted],
    )
    with patch("app.abort_registry.abort",
               return_value={"key": "agent:a1", "found": True,
                             "killed_pids": [], "failed_pids": [],
                             "aborted_now": True}), \
         patch("app.abort_registry.agent_key",
               side_effect=lambda aid: "agent:" + aid), \
         patch("app.chat_task.get_chat_task_manager",
               return_value=fake_mgr), \
         TestClient(app) as c:
        r = c.post("/api/portal/agent/a1/abort")
    d = r.json()
    # Only the live task was flipped.
    assert d["chat_tasks_aborted"] == ["live"]
    assert t_live.aborted is True
    # Terminal tasks untouched.
    assert t_done.aborted is False
    assert t_failed.aborted is False


def test_agent_abort_endpoint_returns_200_even_when_nothing_to_abort():
    """A zero-state abort is a no-op success, not an error. Important
    for the UI: it always shows '已终止' even if the agent happened to
    be idle when the user clicked."""
    from fastapi.testclient import TestClient
    from unittest.mock import patch

    app, _ = _make_app("a1", [])
    with patch("app.abort_registry.abort",
               return_value={"key": "agent:a1", "found": False,
                             "killed_pids": [], "failed_pids": [],
                             "aborted_now": False}), \
         patch("app.abort_registry.agent_key",
               side_effect=lambda aid: "agent:" + aid), \
         patch("app.chat_task.get_chat_task_manager",
               return_value=SimpleNamespace(get_agent_tasks=lambda aid: [])), \
         TestClient(app) as c:
        r = c.post("/api/portal/agent/a1/abort")
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert d["chat_tasks_aborted"] == []
    assert d["abort"]["killed_pids"] == []


def test_agent_abort_tolerates_chat_task_manager_failure():
    """If chat_task import / lookup crashes for any reason, the
    abort_registry path must still succeed. Defense in depth."""
    from fastapi.testclient import TestClient
    from unittest.mock import patch

    app, _ = _make_app("a1", [])
    with patch("app.abort_registry.abort",
               return_value={"key": "agent:a1", "found": True,
                             "killed_pids": [99], "failed_pids": [],
                             "aborted_now": True}), \
         patch("app.abort_registry.agent_key",
               side_effect=lambda aid: "agent:" + aid), \
         patch("app.chat_task.get_chat_task_manager",
               side_effect=RuntimeError("manager unavailable")), \
         TestClient(app) as c:
        r = c.post("/api/portal/agent/a1/abort")
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    # Sub-process kill still happened via abort_registry
    assert d["abort"]["killed_pids"] == [99]
    # chat_tasks defaults to empty — not a 500.
    assert d["chat_tasks_aborted"] == []


def test_agent_abort_404_for_unknown_agent():
    from fastapi.testclient import TestClient
    app, _ = _make_app("a1", [])
    with TestClient(app) as c:
        r = c.post("/api/portal/agent/nope/abort")
    assert r.status_code == 404


# ── Frontend: JS contract ────────────────────────────────────────


def test_agentAbort_has_system_card_and_progress_teardown():
    """Source-level assertion — the JS implementation must do the four
    things the old code was missing. Keeps future refactors honest."""
    import pathlib
    js = pathlib.Path(_ROOT) / "app/server/static/js/portal_bundle.js"
    src = js.read_text()
    assert "_appendChatSystemCard" in src, \
        "missing system-card helper for action feedback"
    # agentAbort body must reference: card creation, stream teardown,
    # per-task abort, and an updated card on response.
    import re
    m = re.search(
        r"async function agentAbort\(agentId\) \{([\s\S]+?)\n\}", src)
    assert m, "agentAbort function not found"
    body = m.group(1)
    assert "_appendChatSystemCard" in body, \
        "agentAbort must insert a system card"
    assert "_activeTaskStreams" in body, \
        "agentAbort must tear down the SSE stream state"
    assert "chat-task/' + stream.taskId + '/abort" in body, \
        "agentAbort must also POST per-task /abort so chat_task.aborted flips"
    assert "_removeProgressBar" in body or "chat-progress-" in body, \
        "agentAbort must remove the progress bar"
    # Card's 'success' branch — confirmation after server response.
    assert "killed" in body, \
        "agentAbort must surface kill count on confirmation"
