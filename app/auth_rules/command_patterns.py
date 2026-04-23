"""Rule: per-command-CONTENT denylist / approval gate.

Sits right after ``rule_global_denylist`` in the chain. Unlike the
global denylist (which matches by *tool name*, e.g. "ban the whole
bash tool for this agent"), this rule matches by *arguments content* —
e.g. let bash through but reject calls where the command is
``terraform apply``.

Used by:
  * cloud_delivery role preset — deny prod-write IaC patterns.
  * Any future "plan only" role (DBA / security / SRE / finance).
  * Global hard red-lines not covered by DENY_PATTERNS (which are
    hard-coded into ``auth.DENY_PATTERNS`` and cannot be tweaked at
    runtime).

Scope values supported (string on the pattern entry):
  * "global"            — applies to every call regardless of agent.
  * "role:<role>"       — applies when the calling agent's role matches.
  * "agent:<agent_id>"  — applies only to that specific agent.

Pattern matching is performed with ``re.search`` (so anchors like ``^``
must be explicit if you want line-start semantics) and is case-insensitive.
The search is run against the set of "command-like" argument fields —
currently ``command`` / ``script`` / ``cmd`` / ``code``. Arguments that
are not strings are coerced via ``str()`` so ``{"command": ["a", "b"]}``
still gets scanned.
"""
from __future__ import annotations

import re
from typing import Optional

from .base import ToolCheckContext, Verdict


# Fields most likely to hold a shell command. Kept small on purpose —
# broader scanning produces false positives on chat/text arguments.
_COMMAND_FIELDS = ("command", "script", "cmd", "code")


def _scope_applies(scope: str, ctx: ToolCheckContext) -> bool:
    if not scope or scope == "global":
        return True
    if scope.startswith("agent:"):
        return ctx.agent_id == scope.split(":", 1)[1]
    if scope.startswith("role:"):
        # Role is not on the context yet — resolve lazily from the hub.
        target_role = scope.split(":", 1)[1]
        try:
            from ..hub import get_hub
            hub = get_hub()
            agent = hub.agents.get(ctx.agent_id) if hub else None
            role = getattr(agent, "role", "") if agent else ""
            return role == target_role
        except Exception:
            return False
    return False


def _collect_command_text(arguments: dict) -> str:
    """Join all command-like argument values into a single searchable
    blob. Non-string values are str()-coerced."""
    if not isinstance(arguments, dict):
        return ""
    parts: list[str] = []
    for field in _COMMAND_FIELDS:
        v = arguments.get(field)
        if v is None:
            continue
        if isinstance(v, str):
            parts.append(v)
        else:
            try:
                parts.append(str(v))
            except Exception:
                continue
    return "\n".join(parts)


def rule_command_patterns(ctx: ToolCheckContext) -> Optional[Verdict]:
    patterns = getattr(ctx.policy, "command_patterns", None) or []
    if not patterns:
        return None
    cmd_text = _collect_command_text(ctx.arguments)
    if not cmd_text:
        return None
    for cp in patterns:
        try:
            if not _scope_applies(cp.get("scope", "global"), ctx):
                continue
            pat = cp.get("pattern") or ""
            if not pat:
                continue
            if not re.search(pat, cmd_text, re.IGNORECASE):
                continue
            verdict = cp.get("verdict") or "deny"
            if verdict not in ("deny", "needs_approval"):
                verdict = "deny"
            reason = cp.get("reason") or (
                f"matched command pattern {cp.get('label') or pat!r}"
            )
            return (verdict, f"🛡 {reason}")
        except re.error:
            # Corrupt regex — skip, don't crash the chain.
            continue
    return None
