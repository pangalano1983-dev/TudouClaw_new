"""Verifier — Block 2 Review loop 的核心。

每个 step（无论是 ExecutionStep 还是 ProjectTask）可以声明一个 verify
配置。agent 标 complete 时框架自动触发 verifier；verifier 失败则
step 被打回 FAILED 并带上具体失败原因，下一轮 LLM 看 plan_state 自然
会去修。

四种 built-in verifier：

1. RunTestsVerifier        — 跑测试框架（调 run_tests tool）
2. FileExistsVerifier      — 检查 workspace 里有没有预期产物
3. CommandVerifier         — 跑任意 bash 命令，exit 0 = pass
4. LlmJudgeVerifier        — LLM 对照 acceptance 打 pass/fail

每种 verifier 接同样的 (VerifyContext, config) → VerifyResult 接口，
注册在 _VERIFIER_REGISTRY，第三方可以 register_verifier() 扩展。

YAML 声明示例：

    verify:
      kind: run_tests
      config: { paths: "tests/", framework: "pytest" }
      required: true

    verify:
      kind: file_exists
      config: { pattern: "**/*.pptx", min_size_kb: 10, newer_than_start: true }

    verify:
      kind: command
      config: { command: "terraform validate", expected_exit: 0 }

    verify:
      kind: llm_judge
      config: { llm_tier: "reasoning_strong", strict: true }
"""
from __future__ import annotations

import glob as _glob
import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger("tudou.verifier")


# ─── Core types ─────────────────────────────────────────────────────

@dataclass
class VerifyConfig:
    """Declared on ExecutionStep / ProjectTask. Stored as-is in to_dict."""
    kind: str = ""
    config: dict = field(default_factory=dict)
    required: bool = True        # if False, failure is warning not blocker
    timeout_s: float = 300.0

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "config": dict(self.config),
            "required": self.required,
            "timeout_s": self.timeout_s,
        }

    @staticmethod
    def from_dict(d: Any) -> Optional["VerifyConfig"]:
        if not d or not isinstance(d, dict):
            return None
        kind = str(d.get("kind") or "").strip()
        if not kind:
            return None
        return VerifyConfig(
            kind=kind,
            config=dict(d.get("config") or {}),
            required=bool(d.get("required", True)),
            timeout_s=float(d.get("timeout_s", 300.0) or 300.0),
        )


@dataclass
class VerifyContext:
    """Everything a verifier needs, no reaching into globals."""
    workspace_dir: str
    step_started_at: float           # for mtime / "new file" filters
    acceptance: str = ""
    result_summary: str = ""         # what the agent claimed it did
    agent_id: str = ""
    plan_id: str = ""
    step_id: str = ""
    # For LlmJudgeVerifier and anything needing a back-reference to the
    # caller agent's LLM. Injected by the caller; keeps verifier module
    # decoupled from Agent class.
    llm_call: Optional[Callable[[list[dict], dict | None], dict]] = None


@dataclass
class VerifyResult:
    ok: bool
    summary: str = ""                # one-line for UI / result_summary append
    details: dict = field(default_factory=dict)
    error: str = ""
    duration_s: float = 0.0
    verifier_kind: str = ""

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "summary": self.summary[:500],
            "details": self.details,
            "error": self.error[:500],
            "duration_s": round(self.duration_s, 2),
            "verifier_kind": self.verifier_kind,
        }


# Callable signature each verifier implements.
VerifyFn = Callable[[VerifyContext, dict], VerifyResult]


# ─── Registry ───────────────────────────────────────────────────────

_VERIFIER_REGISTRY: dict[str, VerifyFn] = {}


def register_verifier(kind: str, fn: VerifyFn) -> None:
    """Register a verifier implementation. Re-registering replaces."""
    if not kind:
        return
    _VERIFIER_REGISTRY[kind] = fn


def get_verifier(kind: str) -> Optional[VerifyFn]:
    return _VERIFIER_REGISTRY.get(kind)


def list_verifier_kinds() -> list[str]:
    return sorted(_VERIFIER_REGISTRY.keys())


# ─── Orchestrator ───────────────────────────────────────────────────

def run_verify(cfg: VerifyConfig, context: VerifyContext) -> VerifyResult:
    """Dispatch to the right verifier, enforce timeout, catch exceptions.

    Never raises — returns a VerifyResult even on crash (ok=False, error=…).
    """
    start = time.time()
    fn = get_verifier(cfg.kind)
    if fn is None:
        return VerifyResult(
            ok=False, verifier_kind=cfg.kind,
            summary=f"unknown verifier kind {cfg.kind!r}",
            error=(f"Verifier {cfg.kind!r} not registered. "
                   f"Available: {list_verifier_kinds()}"),
            duration_s=0.0,
        )
    try:
        result = fn(context, cfg.config)
        if not isinstance(result, VerifyResult):
            # Defensive — verifier author returned the wrong type
            result = VerifyResult(
                ok=False, verifier_kind=cfg.kind,
                summary="verifier returned non-VerifyResult",
                error=repr(result)[:200],
            )
        result.verifier_kind = cfg.kind
        result.duration_s = time.time() - start
        return result
    except Exception as e:
        logger.warning("verifier %s crashed: %s", cfg.kind, e)
        return VerifyResult(
            ok=False, verifier_kind=cfg.kind,
            summary=f"verifier crashed: {type(e).__name__}",
            error=str(e)[:500],
            duration_s=time.time() - start,
        )


# ═══════════════════════════════════════════════════════════════════
# Built-in verifiers
# ═══════════════════════════════════════════════════════════════════

# ─── 1. RunTestsVerifier ───────────────────────────────────────────

def _v_run_tests(ctx: VerifyContext, config: dict) -> VerifyResult:
    """Invoke the run_tests tool and translate its result into VerifyResult.

    config keys (all optional):
        paths: str           — test paths/patterns
        framework: str       — override auto-detect
        extra_args: str      — CLI tail
        timeout: int         — seconds
        min_passed: int      — required minimum pass count (default: 1)
    """
    from .tools_split.test_runner import _tool_run_tests
    # Run in the step's workspace. run_tests uses sandbox policy's root,
    # which callers set via sandbox_scope before invoking us.
    raw = _tool_run_tests(
        paths=str(config.get("paths", "")),
        framework=str(config.get("framework", "")),
        extra_args=str(config.get("extra_args", "")),
        timeout=int(config.get("timeout", 600) or 600),
    )
    try:
        r = json.loads(raw)
    except Exception:
        return VerifyResult(
            ok=False, summary="run_tests returned non-JSON",
            error=raw[:500],
        )

    if not r.get("ok", False):
        top_fail = ""
        fails = r.get("failures") or []
        if fails:
            top_fail = f"{fails[0].get('test','?')}: {fails[0].get('message','')}"
        return VerifyResult(
            ok=False,
            summary=(f"{r.get('failed', 0)}/{r.get('passed', 0) + r.get('failed', 0)} "
                     f"tests failed" if r.get('failed') else
                     r.get("error", "tests did not pass")),
            details=r,
            error=top_fail or r.get("error", "tests failed"),
        )

    min_passed = int(config.get("min_passed", 1))
    if r.get("passed", 0) < min_passed:
        return VerifyResult(
            ok=False,
            summary=f"only {r.get('passed',0)} tests passed, required ≥ {min_passed}",
            details=r,
            error="insufficient test coverage",
        )

    return VerifyResult(
        ok=True,
        summary=f"{r.get('passed', 0)} tests passed",
        details=r,
    )


register_verifier("run_tests", _v_run_tests)


# ─── 2. FileExistsVerifier ─────────────────────────────────────────

def _v_file_exists(ctx: VerifyContext, config: dict) -> VerifyResult:
    """Check the workspace has file(s) matching a glob pattern.

    config:
        pattern: str                — required. glob pattern relative to workspace_dir
                                       (e.g. "**/*.pptx", "reports/*.md")
        min_size_bytes: int         — each match must be at least this big
        min_count: int              — at least this many matches (default 1)
        newer_than_start: bool      — only count files with mtime > step_started_at
                                       (default True — ensures agent produced fresh ones)
    """
    pattern = str(config.get("pattern", "")).strip()
    if not pattern:
        return VerifyResult(
            ok=False, summary="file_exists verify needs 'pattern'",
            error="missing config.pattern",
        )
    workspace = Path(ctx.workspace_dir) if ctx.workspace_dir else None
    if workspace is None or not workspace.is_dir():
        return VerifyResult(
            ok=False,
            summary=f"workspace_dir does not exist: {ctx.workspace_dir!r}",
            error="no workspace",
        )
    min_size = int(config.get("min_size_bytes", 0))
    min_count = int(config.get("min_count", 1))
    newer_than_start = bool(config.get("newer_than_start", True))

    full_pattern = str(workspace / pattern)
    matches = _glob.glob(full_pattern, recursive=True)
    # Filter
    qualifying: list[dict] = []
    for m in matches:
        p = Path(m)
        if not p.is_file():
            continue
        try:
            stat = p.stat()
        except OSError:
            continue
        if stat.st_size < min_size:
            continue
        if newer_than_start and ctx.step_started_at > 0 and \
                stat.st_mtime < ctx.step_started_at:
            continue
        qualifying.append({
            "path": str(p.relative_to(workspace)),
            "size": stat.st_size,
            "mtime": stat.st_mtime,
        })
    if len(qualifying) < min_count:
        return VerifyResult(
            ok=False,
            summary=(f"expected ≥{min_count} file(s) matching "
                     f"{pattern!r}, found {len(qualifying)}"),
            details={
                "pattern": pattern,
                "qualifying": qualifying,
                "all_matches": [str(Path(m).relative_to(workspace))
                                for m in matches if Path(m).is_file()][:20],
                "newer_than_start_filter": newer_than_start,
            },
            error=(f"agent claimed completion but no fresh file matching "
                   f"{pattern!r} found in workspace"),
        )
    return VerifyResult(
        ok=True,
        summary=f"found {len(qualifying)} file(s) matching {pattern!r}",
        details={"qualifying": qualifying},
    )


register_verifier("file_exists", _v_file_exists)


# ─── 3. CommandVerifier ────────────────────────────────────────────

def _v_command(ctx: VerifyContext, config: dict) -> VerifyResult:
    """Run a shell command; exit code matching expected_exit = pass.

    config:
        command: str           — required
        expected_exit: int     — default 0
        timeout_s: float       — default 60
    """
    cmd = str(config.get("command", "")).strip()
    if not cmd:
        return VerifyResult(
            ok=False, summary="command verify needs 'command'",
            error="missing config.command",
        )
    expected = int(config.get("expected_exit", 0))
    timeout = float(config.get("timeout_s", 60) or 60)
    try:
        proc = subprocess.run(
            cmd, shell=True, cwd=ctx.workspace_dir or None,
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return VerifyResult(
            ok=False, summary=f"command timed out after {timeout}s",
            error=f"timeout: {cmd[:80]}",
        )
    except Exception as e:
        return VerifyResult(
            ok=False, summary=f"command execution failed: {type(e).__name__}",
            error=str(e)[:200],
        )

    ok = proc.returncode == expected
    tail_out = (proc.stdout or "")[-500:]
    tail_err = (proc.stderr or "")[-500:]
    return VerifyResult(
        ok=ok,
        summary=(f"command exit={proc.returncode}" +
                 ("" if ok else f" (expected {expected})")),
        details={
            "cmd": cmd, "return_code": proc.returncode,
            "expected_exit": expected,
            "stdout_tail": tail_out, "stderr_tail": tail_err,
        },
        error=("" if ok else f"exit {proc.returncode} != {expected}"),
    )


register_verifier("command", _v_command)


# ─── 4. LlmJudgeVerifier ───────────────────────────────────────────

_LLM_JUDGE_PROMPT = """You are a strict technical verifier. Judge whether a step's \
result satisfies its acceptance criterion. Answer with a SINGLE JSON object \
(no prose before or after):

{{"ok": true|false, "reason": "<one sentence explanation>"}}

Be strict. If the result is vague ("done", "完成", "OK") when acceptance asked \
for specifics, mark ok=false. If result cites concrete evidence (file paths, \
counts, identifiers) matching acceptance, mark ok=true.

Acceptance criterion:
---
{acceptance}
---

Agent's claimed result:
---
{result}
---

Your JSON verdict:"""


def _v_llm_judge(ctx: VerifyContext, config: dict) -> VerifyResult:
    """LLM-as-judge. Config is mostly about when to be strict.

    config:
        strict: bool       — default True. If False, tolerate minor vagueness.
        prompt_override: str — custom prompt template (advanced)

    Requires ctx.llm_call to be set — caller injects this because the
    verifier module doesn't know about the Agent class directly.
    """
    if not ctx.acceptance or not ctx.result_summary:
        return VerifyResult(
            ok=False, summary="llm_judge needs acceptance + result_summary",
            error=("missing acceptance or result_summary on step; "
                   "cannot judge"),
        )
    if ctx.llm_call is None:
        return VerifyResult(
            ok=False, summary="llm_judge needs ctx.llm_call injected",
            error=("caller did not provide an LLM callable — wire via "
                   "VerifyContext.llm_call in the agent hook"),
        )
    prompt_template = str(config.get("prompt_override") or _LLM_JUDGE_PROMPT)
    try:
        prompt = prompt_template.format(
            acceptance=ctx.acceptance[:1500],
            result=ctx.result_summary[:2000],
        )
    except Exception as e:
        return VerifyResult(
            ok=False, summary="llm_judge prompt template invalid",
            error=str(e)[:200],
        )

    messages = [
        {"role": "system",
         "content": "You verify task completion strictly and output JSON only."},
        {"role": "user", "content": prompt},
    ]
    try:
        # Caller supplies an llm_call(messages, options) -> dict shape
        # matching llm.chat_no_stream: {"message": {"content": "..."}}
        resp = ctx.llm_call(messages, None)
    except Exception as e:
        return VerifyResult(
            ok=False, summary="llm_judge LLM call failed",
            error=str(e)[:500],
        )
    content = ""
    if isinstance(resp, dict):
        content = ((resp.get("message") or {}).get("content") or "").strip()
    elif isinstance(resp, str):
        content = resp.strip()
    if not content:
        return VerifyResult(
            ok=False, summary="llm_judge got empty LLM response",
            error="empty content",
        )
    # Try to parse JSON. Some models wrap in code blocks.
    _content = content
    if "```" in _content:
        parts = _content.split("```")
        if len(parts) >= 2:
            _content = parts[1]
            if _content.startswith("json"):
                _content = _content[4:]
    _content = _content.strip()
    try:
        verdict = json.loads(_content)
    except Exception:
        # Fallback: look for "ok": true/false substring
        lower = _content.lower()
        if '"ok"' in lower and "true" in lower:
            verdict = {"ok": True, "reason": _content[:200]}
        else:
            return VerifyResult(
                ok=False, summary="llm_judge response not JSON",
                error=_content[:400],
            )

    if not isinstance(verdict, dict):
        return VerifyResult(
            ok=False, summary="llm_judge verdict not an object",
            error=str(verdict)[:200],
        )

    ok = bool(verdict.get("ok", False))
    reason = str(verdict.get("reason", "")).strip()[:300]
    return VerifyResult(
        ok=ok,
        summary=(reason or ("accepted" if ok else "rejected")),
        details={"verdict": verdict, "raw": content[:800]},
        error=("" if ok else reason or "llm_judge rejected"),
    )


register_verifier("llm_judge", _v_llm_judge)


__all__ = [
    "VerifyConfig", "VerifyContext", "VerifyResult",
    "run_verify", "register_verifier", "get_verifier",
    "list_verifier_kinds",
]
