"""Task abort — central registry + subprocess kill.

Covers the minimum viable abort surface:
- mark / is_aborted / abort / clear lifecycle
- Multiple keys don't cross-contaminate
- abort() returns found=False for unknown keys (no-op, no crash)
- Track / untrack pids; abort SIGTERM's tracked pids
- AbortScope context manager sets thread-local current_key
- bash tool tracks its own subprocess pid and removes on completion
"""
from __future__ import annotations

import os
import signal
import subprocess
import threading
import time

import pytest

from app import abort_registry as _ar


# ── registry core ──────────────────────────────────────────────────

def test_mark_and_clear():
    k = "test:mark-clear"
    _ar.mark(k)
    assert _ar.is_aborted(k) is False
    _ar.clear(k)
    # After clear, state is gone — is_aborted returns False for unknown keys too
    assert _ar.is_aborted(k) is False


def test_abort_flips_flag():
    k = "test:abort-flag"
    _ar.mark(k)
    result = _ar.abort(k)
    assert result["found"] is True
    assert result["aborted_now"] is True
    assert _ar.is_aborted(k) is True
    _ar.clear(k)


def test_abort_unknown_key_is_noop():
    k = "test:never-marked"
    result = _ar.abort(k)
    assert result["found"] is False
    assert result["killed_pids"] == []


def test_abort_idempotent():
    k = "test:idempotent"
    _ar.mark(k)
    r1 = _ar.abort(k)
    r2 = _ar.abort(k)
    assert r1["aborted_now"] is True
    assert r2["aborted_now"] is False  # already aborted
    assert _ar.is_aborted(k) is True
    _ar.clear(k)


def test_keys_are_isolated():
    _ar.mark("test:a")
    _ar.mark("test:b")
    _ar.abort("test:a")
    assert _ar.is_aborted("test:a") is True
    assert _ar.is_aborted("test:b") is False
    _ar.clear("test:a")
    _ar.clear("test:b")


# ── pid tracking ───────────────────────────────────────────────────

def test_track_untrack_pid():
    k = "test:pids"
    _ar.mark(k)
    _ar.track_pid(k, 99991)
    _ar.track_pid(k, 99992)
    state = _ar.get_state(k)
    assert state is not None
    assert set(state["pids"]) == {99991, 99992}
    _ar.untrack_pid(k, 99991)
    state = _ar.get_state(k)
    assert set(state["pids"]) == {99992}
    _ar.clear(k)


def test_abort_sigterm_real_subprocess():
    """End-to-end: spawn a real subprocess (sleep 60), track its pid,
    abort() the key, verify the pid no longer exists."""
    k = "test:real-kill"
    _ar.mark(k)
    proc = subprocess.Popen(
        ["sleep", "60"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        _ar.track_pid(k, proc.pid)
        # Subprocess should still be alive at this point
        assert proc.poll() is None

        result = _ar.abort(k)
        assert result["found"] is True
        assert proc.pid in result["killed_pids"]

        # The subprocess should exit quickly (SIGTERM respected by sleep)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            # If sleep somehow didn't die, the abort grace will have
            # SIGKILL'd it — give it one more moment.
            proc.wait(timeout=3)
        assert proc.returncode is not None
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        _ar.clear(k)


# ── AbortScope ─────────────────────────────────────────────────────

def test_abort_scope_sets_thread_local():
    k = "test:scope"
    assert _ar.current_key() == ""  # baseline
    with _ar.AbortScope(k, thread=threading.current_thread()):
        assert _ar.current_key() == k
    # Cleared on exit
    assert _ar.current_key() == ""


def test_abort_scope_nests():
    outer = "test:outer"
    inner = "test:inner"
    with _ar.AbortScope(outer):
        assert _ar.current_key() == outer
        with _ar.AbortScope(inner):
            assert _ar.current_key() == inner
        # Nested scope restores outer
        assert _ar.current_key() == outer
    assert _ar.current_key() == ""


def test_abort_scope_clears_registry_on_exit():
    k = "test:scope-cleanup"
    with _ar.AbortScope(k):
        assert _ar.get_state(k) is not None
    assert _ar.get_state(k) is None


# ── key helpers ────────────────────────────────────────────────────

def test_key_helpers_format():
    assert _ar.agent_key("abc") == "agent:abc"
    assert _ar.meeting_key("m1") == "meeting:m1"
    assert _ar.project_key("p1") == "project:p1"
    assert _ar.project_task_key("p1", "t1") == "project:p1:task:t1"


# ── bash tool integration ──────────────────────────────────────────

def test_bash_tool_tracks_subprocess_and_honors_abort():
    """Real integration: bash tool runs a long sleep inside an AbortScope;
    we call abort() from another thread and verify bash returns an
    'ABORTED by user' result quickly (not after the full timeout)."""
    from app.tools_split.system import _tool_bash
    from app import sandbox as _sandbox

    # Install a permissive sandbox policy so the bash invocation
    # isn't rejected at the command-check stage.
    pol = _sandbox.SandboxPolicy(
        root=os.getcwd(), mode="off", allow_list=[],
    )
    token = _sandbox.sandbox_scope(pol)
    token.__enter__()
    k = "test:bash-abort"
    _ar.mark(k)
    try:
        result_holder: dict = {}
        def _run():
            # thread-local _current_key lives per-thread; bash consults
            # it to learn which task to register pids under. Set it here
            # (in production this happens automatically via AbortScope
            # when an agent.chat call enters its scope).
            _ar._current_key.key = k
            result_holder["out"] = _tool_bash(command="sleep 30", timeout=60)

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        # Give bash a moment to spawn the subprocess and register its pid
        time.sleep(0.8)
        st = _ar.get_state(k)
        assert st is not None
        assert len(st["pids"]) == 1, f"expected 1 tracked pid, got {st}"

        # Abort from "outside"
        abort_result = _ar.abort(k)
        assert abort_result["found"] is True
        assert len(abort_result["killed_pids"]) == 1

        # Bash thread should complete fast now
        t.join(timeout=8)
        assert not t.is_alive(), "bash thread didn't exit after abort"
        out = result_holder.get("out", "")
        # The bash tool surfaces either its "ABORTED" message or a negative
        # exit code — either way the user knows it was stopped, not a
        # silent "success".
        assert ("ABORTED" in out or "exit code: -" in out), out
    finally:
        _ar.clear(k)
        token.__exit__(None, None, None)
