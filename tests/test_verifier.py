"""Verifier unit tests — cover dispatch + 4 built-in kinds + error paths."""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
import pytest

from app.verifier import (
    VerifyConfig, VerifyContext, VerifyResult,
    run_verify, register_verifier, get_verifier, list_verifier_kinds,
)
from app import sandbox as _sandbox


# ─── VerifyConfig / Result ──────────────────────────────────────────

def test_verify_config_roundtrip():
    c = VerifyConfig(kind="run_tests", config={"paths": "tests/"}, required=True)
    d = c.to_dict()
    c2 = VerifyConfig.from_dict(d)
    assert c2 is not None
    assert c2.kind == "run_tests"
    assert c2.config == {"paths": "tests/"}
    assert c2.required is True


def test_verify_config_from_dict_none_or_empty():
    assert VerifyConfig.from_dict(None) is None
    assert VerifyConfig.from_dict({}) is None
    assert VerifyConfig.from_dict({"kind": ""}) is None


def test_verify_config_legacy_tolerant():
    """Missing timeout / required should default, not crash."""
    c = VerifyConfig.from_dict({"kind": "command", "config": {"command": "true"}})
    assert c is not None
    assert c.required is True          # default
    assert c.timeout_s == 300.0         # default


# ─── Dispatch ───────────────────────────────────────────────────────

def test_unknown_verifier_kind_returns_failure_not_exception():
    cfg = VerifyConfig(kind="does_not_exist")
    ctx = VerifyContext(workspace_dir="/tmp", step_started_at=0)
    r = run_verify(cfg, ctx)
    assert r.ok is False
    assert "unknown verifier" in r.summary.lower()
    assert "Available:" in r.error  # tells caller what kinds exist


def test_registry_lists_all_builtins():
    kinds = list_verifier_kinds()
    for expected in ("run_tests", "file_exists", "command", "llm_judge"):
        assert expected in kinds, f"{expected} missing from registry"


def test_verifier_crash_caught_and_reported():
    def _crasher(ctx, cfg):
        raise RuntimeError("boom")
    register_verifier("test_crasher", _crasher)
    try:
        r = run_verify(
            VerifyConfig(kind="test_crasher"),
            VerifyContext(workspace_dir="/tmp", step_started_at=0),
        )
        assert r.ok is False
        assert "crashed" in r.summary.lower()
        assert "boom" in r.error
    finally:
        # Clean up registry so later tests aren't polluted
        from app import verifier as _v
        _v._VERIFIER_REGISTRY.pop("test_crasher", None)


def test_verifier_returning_wrong_type_is_defensive():
    def _bad(ctx, cfg):
        return "not a VerifyResult"  # bug
    register_verifier("test_bad_return", _bad)
    try:
        r = run_verify(
            VerifyConfig(kind="test_bad_return"),
            VerifyContext(workspace_dir="/tmp", step_started_at=0),
        )
        assert r.ok is False
        assert "non-VerifyResult" in r.summary
    finally:
        from app import verifier as _v
        _v._VERIFIER_REGISTRY.pop("test_bad_return", None)


# ─── RunTestsVerifier ──────────────────────────────────────────────

def _make_pytest_workspace(tmp_path: Path, *, fail_test: bool = False) -> Path:
    """Create a minimal pytest workspace that either passes or fails."""
    (tmp_path / "pytest.ini").write_text("[pytest]\npython_files = test_*.py\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "__init__.py").write_text("")
    body = "def test_pass(): assert 1 == 1"
    if fail_test:
        body += "\ndef test_fail(): assert False, 'deliberate'"
    (tmp_path / "tests" / "test_smoke.py").write_text(body)
    return tmp_path


def test_run_tests_verifier_passes_when_tests_pass(tmp_path):
    ws = _make_pytest_workspace(tmp_path, fail_test=False)
    pol = _sandbox.SandboxPolicy(root=str(ws), mode="off")
    with _sandbox.sandbox_scope(pol):
        r = run_verify(
            VerifyConfig(kind="run_tests", config={"paths": "tests/"}),
            VerifyContext(workspace_dir=str(ws), step_started_at=0),
        )
    assert r.ok is True, f"expected pass, got {r}"
    assert "passed" in r.summary
    assert r.details.get("passed") >= 1


def test_run_tests_verifier_fails_when_test_fails(tmp_path):
    ws = _make_pytest_workspace(tmp_path, fail_test=True)
    pol = _sandbox.SandboxPolicy(root=str(ws), mode="off")
    with _sandbox.sandbox_scope(pol):
        r = run_verify(
            VerifyConfig(kind="run_tests", config={"paths": "tests/"}),
            VerifyContext(workspace_dir=str(ws), step_started_at=0),
        )
    assert r.ok is False
    # Summary should cite the failure count
    assert "fail" in r.summary.lower()
    assert r.details.get("failed") >= 1


def test_run_tests_verifier_min_passed_threshold(tmp_path):
    """Tests pass but too few → verifier still fails."""
    ws = _make_pytest_workspace(tmp_path, fail_test=False)  # 1 passing test
    pol = _sandbox.SandboxPolicy(root=str(ws), mode="off")
    with _sandbox.sandbox_scope(pol):
        r = run_verify(
            VerifyConfig(
                kind="run_tests",
                config={"paths": "tests/", "min_passed": 5},
            ),
            VerifyContext(workspace_dir=str(ws), step_started_at=0),
        )
    assert r.ok is False
    assert "required ≥ 5" in r.summary or "insufficient" in r.error


# ─── FileExistsVerifier ────────────────────────────────────────────

def test_file_exists_verifier_finds_matching_file(tmp_path):
    # Create a .pptx-like file
    (tmp_path / "report.pptx").write_bytes(b"PK\x03\x04" + b"x" * 12000)
    r = run_verify(
        VerifyConfig(
            kind="file_exists",
            config={"pattern": "*.pptx", "min_size_bytes": 1000,
                    "newer_than_start": False},
        ),
        VerifyContext(workspace_dir=str(tmp_path), step_started_at=0),
    )
    assert r.ok is True
    assert "report.pptx" in str(r.details.get("qualifying", []))


def test_file_exists_verifier_fails_when_pattern_unmatched(tmp_path):
    (tmp_path / "other.md").write_text("hi")
    r = run_verify(
        VerifyConfig(
            kind="file_exists",
            config={"pattern": "*.pptx", "newer_than_start": False},
        ),
        VerifyContext(workspace_dir=str(tmp_path), step_started_at=0),
    )
    assert r.ok is False
    assert "expected ≥1 file(s)" in r.summary


def test_file_exists_verifier_newer_than_start_filter(tmp_path):
    """File exists but was created BEFORE step started → should not count."""
    old_file = tmp_path / "old.pptx"
    old_file.write_bytes(b"PK" + b"x" * 12000)
    # Force mtime to be older
    old_time = time.time() - 3600
    os.utime(str(old_file), (old_time, old_time))

    # Step "started" 10 minutes ago — old file is too old
    started = time.time() - 600
    r = run_verify(
        VerifyConfig(
            kind="file_exists",
            config={"pattern": "*.pptx", "newer_than_start": True},
        ),
        VerifyContext(workspace_dir=str(tmp_path), step_started_at=started),
    )
    assert r.ok is False
    # The UI "all_matches" debug list should show the old file
    assert any("old.pptx" in m for m in r.details.get("all_matches", []))


def test_file_exists_verifier_min_count_threshold(tmp_path):
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.txt").write_text("b")
    r = run_verify(
        VerifyConfig(
            kind="file_exists",
            config={"pattern": "*.txt", "min_count": 3,
                    "newer_than_start": False},
        ),
        VerifyContext(workspace_dir=str(tmp_path), step_started_at=0),
    )
    assert r.ok is False
    assert "expected ≥3" in r.summary


def test_file_exists_verifier_missing_pattern_errors_cleanly():
    r = run_verify(
        VerifyConfig(kind="file_exists", config={}),
        VerifyContext(workspace_dir="/tmp", step_started_at=0),
    )
    assert r.ok is False
    assert "pattern" in r.summary.lower()


def test_file_exists_verifier_recursive_pattern(tmp_path):
    (tmp_path / "nested").mkdir()
    deep = tmp_path / "nested" / "deep" / "sub"
    deep.mkdir(parents=True)
    (deep / "buried.pptx").write_bytes(b"PK" + b"x" * 12000)
    r = run_verify(
        VerifyConfig(
            kind="file_exists",
            config={"pattern": "**/*.pptx", "newer_than_start": False},
        ),
        VerifyContext(workspace_dir=str(tmp_path), step_started_at=0),
    )
    assert r.ok is True
    assert len(r.details.get("qualifying", [])) == 1


# ─── CommandVerifier ───────────────────────────────────────────────

def test_command_verifier_passes_on_exit_0(tmp_path):
    r = run_verify(
        VerifyConfig(kind="command", config={"command": "echo ok"}),
        VerifyContext(workspace_dir=str(tmp_path), step_started_at=0),
    )
    assert r.ok is True
    assert "exit=0" in r.summary
    assert "ok" in r.details.get("stdout_tail", "")


def test_command_verifier_fails_on_nonzero(tmp_path):
    r = run_verify(
        VerifyConfig(kind="command", config={"command": "exit 7"}),
        VerifyContext(workspace_dir=str(tmp_path), step_started_at=0),
    )
    assert r.ok is False
    assert "exit=7" in r.summary
    assert r.details.get("return_code") == 7


def test_command_verifier_custom_expected_exit(tmp_path):
    """Some commands signal success with non-zero exit (e.g. grep)."""
    r = run_verify(
        VerifyConfig(kind="command",
                     config={"command": "exit 3", "expected_exit": 3}),
        VerifyContext(workspace_dir=str(tmp_path), step_started_at=0),
    )
    assert r.ok is True


def test_command_verifier_timeout(tmp_path):
    r = run_verify(
        VerifyConfig(kind="command",
                     config={"command": "sleep 30", "timeout_s": 0.5}),
        VerifyContext(workspace_dir=str(tmp_path), step_started_at=0),
    )
    assert r.ok is False
    assert "timed out" in r.summary


def test_command_verifier_missing_command():
    r = run_verify(
        VerifyConfig(kind="command", config={}),
        VerifyContext(workspace_dir="/tmp", step_started_at=0),
    )
    assert r.ok is False
    assert "command" in r.summary.lower()


# ─── LlmJudgeVerifier ──────────────────────────────────────────────

def test_llm_judge_needs_acceptance_and_result():
    r = run_verify(
        VerifyConfig(kind="llm_judge"),
        VerifyContext(workspace_dir="/tmp", step_started_at=0,
                      acceptance="", result_summary=""),
    )
    assert r.ok is False
    assert "acceptance" in r.summary.lower() or "result_summary" in r.summary.lower()


def test_llm_judge_needs_llm_call_injected():
    r = run_verify(
        VerifyConfig(kind="llm_judge"),
        VerifyContext(
            workspace_dir="/tmp", step_started_at=0,
            acceptance="do the thing",
            result_summary="I did the thing",
            llm_call=None,  # not injected
        ),
    )
    assert r.ok is False
    assert "llm_call" in r.error or "llm_call" in r.summary


def test_llm_judge_accepts_positive_verdict():
    def fake_llm(messages, _options):
        return {"message": {"content": '{"ok": true, "reason": "specifics cited"}'}}
    r = run_verify(
        VerifyConfig(kind="llm_judge"),
        VerifyContext(
            workspace_dir="/tmp", step_started_at=0,
            acceptance="Produce report.pptx with ≥5 slides",
            result_summary="created report.pptx, opened fine, 7 slides verified",
            llm_call=fake_llm,
        ),
    )
    assert r.ok is True
    assert "specifics" in r.summary


def test_llm_judge_rejects_negative_verdict():
    def fake_llm(messages, _options):
        return {"message": {"content": '{"ok": false, "reason": "vague, no specifics"}'}}
    r = run_verify(
        VerifyConfig(kind="llm_judge"),
        VerifyContext(
            workspace_dir="/tmp", step_started_at=0,
            acceptance="Produce report.pptx with ≥5 slides",
            result_summary="done",
            llm_call=fake_llm,
        ),
    )
    assert r.ok is False
    assert "vague" in r.summary


def test_llm_judge_tolerates_markdown_wrapped_json():
    def fake_llm(messages, _options):
        return {"message": {"content": '```json\n{"ok": true, "reason": "ok"}\n```'}}
    r = run_verify(
        VerifyConfig(kind="llm_judge"),
        VerifyContext(
            workspace_dir="/tmp", step_started_at=0,
            acceptance="x", result_summary="y",
            llm_call=fake_llm,
        ),
    )
    assert r.ok is True


def test_llm_judge_fallback_when_not_json():
    def fake_llm(messages, _options):
        return {"message": {"content": 'The answer is "ok": true, looks good.'}}
    r = run_verify(
        VerifyConfig(kind="llm_judge"),
        VerifyContext(
            workspace_dir="/tmp", step_started_at=0,
            acceptance="x", result_summary="y",
            llm_call=fake_llm,
        ),
    )
    # fallback parser accepts "ok": true somewhere
    assert r.ok is True


def test_llm_judge_handles_empty_response():
    def fake_llm(messages, _options):
        return {"message": {"content": ""}}
    r = run_verify(
        VerifyConfig(kind="llm_judge"),
        VerifyContext(
            workspace_dir="/tmp", step_started_at=0,
            acceptance="x", result_summary="y",
            llm_call=fake_llm,
        ),
    )
    assert r.ok is False
    assert "empty" in r.error.lower()


def test_llm_judge_handles_llm_exception():
    def fake_llm(messages, _options):
        raise ConnectionError("LLM provider down")
    r = run_verify(
        VerifyConfig(kind="llm_judge"),
        VerifyContext(
            workspace_dir="/tmp", step_started_at=0,
            acceptance="x", result_summary="y",
            llm_call=fake_llm,
        ),
    )
    assert r.ok is False
    assert "LLM call failed" in r.summary or "LLM provider down" in r.error


# ─── register_verifier extension point ─────────────────────────────

def test_custom_verifier_can_be_registered():
    calls = []
    def _my_v(ctx, config):
        calls.append((ctx, config))
        return VerifyResult(ok=True, summary="custom")
    register_verifier("test_custom_v", _my_v)
    try:
        r = run_verify(
            VerifyConfig(kind="test_custom_v", config={"foo": "bar"}),
            VerifyContext(workspace_dir="/tmp", step_started_at=0),
        )
        assert r.ok is True
        assert r.summary == "custom"
        assert calls  # verifier was invoked
        assert calls[0][1] == {"foo": "bar"}
    finally:
        from app import verifier as _v
        _v._VERIFIER_REGISTRY.pop("test_custom_v", None)
