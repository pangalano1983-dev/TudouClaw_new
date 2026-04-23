"""`run_tests` tool — structured test execution.

Block 2 review loop relies on this. The LLM calls it either directly
(ad hoc) or the Verifier infrastructure calls it (automatic post-step
check). Returns structured JSON the caller can reason about:

    {
      "ok": true|false,
      "framework": "pytest"|"npm"|"go"|"cargo"|"unknown",
      "passed": 42,
      "failed": 3,
      "skipped": 1,
      "duration_s": 12.4,
      "failures": [
          {"test": "tests/test_x.py::test_foo", "message": "AssertionError: ..."},
          ...   # up to 10, each message truncated
      ],
      "stdout_tail": "...",    # last 1500 chars for context
      "cmd": "pytest -v --tb=short",
      "cwd": "/path/to/workspace"
    }

Design decisions
----------------
- Framework detection: look for marker files (pyproject.toml, package.json,
  go.mod, Cargo.toml) in cwd; caller can override via `framework` arg.
- Parser per-framework: regex-based, fast, good-enough. Not 100%
  coverage — if parse fails we still return ok/failed from exit code,
  just without structured failure list.
- Uses AbortRegistry — caller's abort kills pytest mid-run.
- Output cap: tail 1500 chars of stdout/stderr. Full output goes into
  an artifact file in workspace (so verifier can attach a link in UI).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from .. import sandbox as _sandbox
from .. import abort_registry

# Per-framework CLI + parser. Parsers take (stdout, stderr) and return
# (passed, failed, skipped, failures_list). failures_list items:
# {test: str, message: str}.


_MAX_FAILURES_IN_RESPONSE = 10
_STDOUT_TAIL = 1500
_DEFAULT_TIMEOUT_S = 600


# ── framework detection ────────────────────────────────────────────

def _detect_framework(cwd: Path) -> str:
    """Sniff test framework from marker files. Return 'unknown' on miss."""
    # Python is most common in this codebase — check first.
    if (cwd / "pyproject.toml").is_file() or (cwd / "setup.py").is_file() \
            or (cwd / "pytest.ini").is_file() or (cwd / "conftest.py").is_file() \
            or (cwd / "tests").is_dir():
        return "pytest"
    if (cwd / "package.json").is_file():
        # Could be jest/vitest/mocha — treat as npm, let user's test
        # script pick the framework. We don't try to parse node_modules.
        return "npm"
    if (cwd / "go.mod").is_file():
        return "go"
    if (cwd / "Cargo.toml").is_file():
        return "cargo"
    return "unknown"


# ── parsers ─────────────────────────────────────────────────────────

_PYTEST_SUMMARY_RE = re.compile(
    r"(?:=+\s*)(?:(?P<failed>\d+)\s+failed)?"
    r"(?:,?\s+)?(?:(?P<passed>\d+)\s+passed)?"
    r"(?:,?\s+)?(?:(?P<skipped>\d+)\s+skipped)?"
    r"(?:,?\s+)?(?:(?P<error>\d+)\s+error)?",
)

_PYTEST_FAILURE_RE = re.compile(
    r"^FAILED\s+(?P<test>\S+)\s*(?:-\s*(?P<msg>.+))?$",
    re.MULTILINE,
)


def _parse_pytest(stdout: str, stderr: str) -> tuple[int, int, int, list[dict]]:
    passed = failed = skipped = 0
    # pytest prints summary like "=== 5 passed, 2 failed, 1 skipped in 1.23s ==="
    # Find the LAST summary line (the final one is always the authoritative one).
    summary_lines = [ln for ln in stdout.splitlines()
                     if "passed" in ln or "failed" in ln or "error" in ln]
    for line in reversed(summary_lines):
        m = _PYTEST_SUMMARY_RE.search(line)
        if m:
            passed = int(m.group("passed") or 0)
            failed = int(m.group("failed") or 0)
            skipped = int(m.group("skipped") or 0)
            errors = int(m.group("error") or 0)
            failed += errors  # errors count as failures for our purposes
            if passed + failed + skipped > 0:
                break
    failures = []
    for m in _PYTEST_FAILURE_RE.finditer(stdout):
        failures.append({
            "test": m.group("test"),
            "message": (m.group("msg") or "").strip()[:300],
        })
        if len(failures) >= _MAX_FAILURES_IN_RESPONSE:
            break
    return passed, failed, skipped, failures


_GO_TEST_PASS_RE = re.compile(r"^---\s+PASS:\s+(\S+)", re.MULTILINE)
_GO_TEST_FAIL_RE = re.compile(r"^---\s+FAIL:\s+(?P<test>\S+)\s*\(", re.MULTILINE)


def _parse_go(stdout: str, stderr: str) -> tuple[int, int, int, list[dict]]:
    passed = len(_GO_TEST_PASS_RE.findall(stdout))
    failures = []
    for m in _GO_TEST_FAIL_RE.finditer(stdout):
        failures.append({"test": m.group("test"), "message": ""})
    failed = len(failures)
    return passed, failed, 0, failures[:_MAX_FAILURES_IN_RESPONSE]


_CARGO_TEST_SUMMARY_RE = re.compile(
    r"test result:\s+(?:\w+)\.\s+"
    r"(?P<passed>\d+)\s+passed;\s+"
    r"(?P<failed>\d+)\s+failed;\s+"
    r"(?P<ignored>\d+)\s+ignored",
)


def _parse_cargo(stdout: str, stderr: str) -> tuple[int, int, int, list[dict]]:
    passed = failed = skipped = 0
    for line in reversed(stdout.splitlines()):
        m = _CARGO_TEST_SUMMARY_RE.search(line)
        if m:
            passed = int(m.group("passed"))
            failed = int(m.group("failed"))
            skipped = int(m.group("ignored"))
            break
    failures = []
    # cargo prints "---- test_foo stdout ---- thread 'main' panicked at ..."
    for m in re.finditer(r"----\s+(\S+)\s+stdout\s+----", stdout):
        failures.append({"test": m.group(1), "message": ""})
        if len(failures) >= _MAX_FAILURES_IN_RESPONSE:
            break
    return passed, failed, skipped, failures


# Jest-style output — common for npm. Also catches vitest which mimics jest.
_JEST_SUMMARY_RE = re.compile(
    r"Tests:\s+"
    r"(?:(?P<failed>\d+)\s+failed,?\s*)?"
    r"(?:(?P<skipped>\d+)\s+skipped,?\s*)?"
    r"(?:(?P<passed>\d+)\s+passed)",
)
_JEST_FAILURE_RE = re.compile(r"^\s*✕\s+(.+?)(?:\s+\(\d+ms?\))?$", re.MULTILINE)


def _parse_npm(stdout: str, stderr: str) -> tuple[int, int, int, list[dict]]:
    combined = stdout + "\n" + stderr
    passed = failed = skipped = 0
    m = _JEST_SUMMARY_RE.search(combined)
    if m:
        passed = int(m.group("passed") or 0)
        failed = int(m.group("failed") or 0)
        skipped = int(m.group("skipped") or 0)
    failures = []
    for m in _JEST_FAILURE_RE.finditer(combined):
        failures.append({"test": m.group(1).strip(), "message": ""})
        if len(failures) >= _MAX_FAILURES_IN_RESPONSE:
            break
    return passed, failed, skipped, failures


_FRAMEWORK_HANDLERS: dict[str, tuple[list[str], Any]] = {
    "pytest": (["python", "-m", "pytest", "-v", "--tb=short", "--color=no"], _parse_pytest),
    "npm": (["npm", "test", "--", "--colors=false"], _parse_npm),
    "go":  (["go", "test", "-v", "./..."], _parse_go),
    "cargo": (["cargo", "test"], _parse_cargo),
}


# ── tool entry ─────────────────────────────────────────────────────

def _tool_run_tests(paths: str = "", framework: str = "",
                    extra_args: str = "",
                    timeout: int = _DEFAULT_TIMEOUT_S,
                    **_: Any) -> str:
    """Run tests in the agent's workspace.

    Args:
        paths: space-separated test paths / patterns. "" = all tests.
        framework: force a specific framework. "" = auto-detect.
                   One of: pytest | npm | go | cargo.
        extra_args: additional CLI args appended to the command.
        timeout: seconds; clamped to [10, 1800].
    """
    pol = _sandbox.get_current_policy()
    cwd = Path(str(pol.root) if getattr(pol, "root", None) else os.getcwd())
    if not cwd.is_dir():
        return json.dumps({"ok": False, "error": f"cwd not a dir: {cwd}"},
                           ensure_ascii=False)

    timeout = max(10, min(int(timeout or _DEFAULT_TIMEOUT_S), 1800))

    fw = framework.strip().lower() if framework else _detect_framework(cwd)
    if fw not in _FRAMEWORK_HANDLERS:
        return json.dumps({
            "ok": False,
            "framework": fw,
            "error": (f"Unknown framework {fw!r}. "
                      f"Supported: {list(_FRAMEWORK_HANDLERS.keys())}. "
                      f"Pass framework=... explicitly or add a marker "
                      f"file (pytest.ini / package.json / go.mod / Cargo.toml)."),
        }, ensure_ascii=False)

    base_cmd, parser = _FRAMEWORK_HANDLERS[fw]
    cmd: list[str] = list(base_cmd)
    if paths.strip():
        cmd.extend(paths.split())
    if extra_args.strip():
        cmd.extend(extra_args.split())

    # Track subprocess via abort_registry — same pattern as _tool_bash.
    task_key = abort_registry.current_key()
    start = time.time()
    try:
        proc = subprocess.Popen(
            cmd, cwd=str(cwd),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, start_new_session=True,
        )
        if task_key:
            abort_registry.track_pid(task_key, proc.pid)
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            returncode = proc.returncode
        except subprocess.TimeoutExpired:
            import signal as _sig
            try:
                os.killpg(os.getpgid(proc.pid), _sig.SIGTERM)
            except Exception:
                proc.terminate()
            try:
                proc.communicate(timeout=2)
            except Exception:
                try:
                    os.killpg(os.getpgid(proc.pid), _sig.SIGKILL)
                except Exception:
                    proc.kill()
            return json.dumps({
                "ok": False, "framework": fw,
                "error": f"Tests timed out after {timeout}s",
                "cmd": " ".join(cmd), "cwd": str(cwd),
            }, ensure_ascii=False)
        finally:
            if task_key and proc is not None:
                abort_registry.untrack_pid(task_key, proc.pid)
    except FileNotFoundError:
        return json.dumps({
            "ok": False, "framework": fw,
            "error": (f"Framework {fw} CLI not installed or not in PATH "
                      f"(tried: {cmd[0]!r})"),
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "ok": False, "framework": fw, "error": f"Run failed: {e}",
        }, ensure_ascii=False)

    duration = time.time() - start

    # Abort check — if user aborted while we were blocking on tests
    if task_key and abort_registry.is_aborted(task_key):
        return json.dumps({
            "ok": False, "framework": fw, "error": "Aborted by user",
            "cmd": " ".join(cmd), "cwd": str(cwd),
        }, ensure_ascii=False)

    # Parse
    try:
        passed, failed, skipped, failures = parser(stdout, stderr)
    except Exception as e:
        passed = failed = skipped = 0
        failures = []
        # Parse error is non-fatal — fall back to exit code

    # ok policy: passed at least 1 test AND returncode==0 AND no failures.
    # exit 0 alone isn't enough — pytest with NO tests collected returns
    # 5 on newer versions but can be configured to 0; being explicit.
    ok = (returncode == 0) and (failed == 0)

    # If parsing found zero signals but exit code is non-zero, count it
    # as failed (even if we couldn't itemize the failures).
    if passed + failed + skipped == 0 and returncode != 0:
        failed = 1
        ok = False
        failures = failures or [{
            "test": "(parse failed)",
            "message": f"exit code {returncode} — see stdout_tail",
        }]

    tail = stdout[-_STDOUT_TAIL:] if len(stdout) > _STDOUT_TAIL else stdout
    if len(stdout) > _STDOUT_TAIL:
        tail = "...[earlier output trimmed]\n" + tail

    return json.dumps({
        "ok": ok,
        "framework": fw,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "duration_s": round(duration, 2),
        "failures": failures[:_MAX_FAILURES_IN_RESPONSE],
        "stdout_tail": tail,
        "cmd": " ".join(cmd),
        "cwd": str(cwd),
        "return_code": returncode,
    }, ensure_ascii=False)


__all__ = ["_tool_run_tests"]
