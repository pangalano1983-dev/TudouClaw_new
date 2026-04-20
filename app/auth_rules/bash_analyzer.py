"""Rule: ``bash`` tool — multi-stage command analysis.

This was the single largest inline block inside the old ``check_tool``.
Lifted verbatim here so diff review is trivial. Logic order (preserved):

  1. Absolute-deny patterns (``ToolPolicy.deny_patterns``)
  2. Command-injection structural check (backticks / ``$()`` against
     sensitive tokens)
  3. Environment exfiltration (``env | curl`` etc.)
  4. Obfuscation (base64 -d / xxd -r / python -c exec / eval) →
     needs_approval (doesn't deny outright — admin may have reason)
  5. Delete-class commands (rm / xargs rm / find -delete / -exec rm) →
     deny
  6. ``analyze_bash_command`` dispatch on subcommand risk:
       low      → allow
       moderate → allow (if auto_approve_moderate) else agent_approvable
       high     → abstain (fall through to the moderate / high risk rule)

The rule ONLY applies when ``tool_name == "bash"``. For any other tool
it abstains immediately.
"""
from __future__ import annotations

import re
from typing import Optional

from .base import ToolCheckContext, Verdict


# Import analyze_bash_command lazily to avoid a circular import at
# package load time (auth.py imports auth_rules, which would otherwise
# re-import auth.py here).
def _analyze_bash_command(cmd: str):
    from ..auth import analyze_bash_command
    return analyze_bash_command(cmd)


_INJECTION_SENSITIVE = (
    "secret", "password", "token", "key", "credential",
    "/etc/shadow", "/etc/passwd", "ssh", ".env", "aws", "api_key",
)

_EXFIL_RE = re.compile(
    r'\b(env|printenv|set)\b.*\|\s*(curl|wget|nc)', re.IGNORECASE)

_OBFUSCATE_RE = re.compile(
    r'(base64\s+-d|xxd\s+-r|python.*-c.*exec|eval\s)', re.IGNORECASE)


def rule_bash_analyzer(ctx: ToolCheckContext) -> Optional[Verdict]:
    if ctx.tool_name != "bash":
        return None

    cmd = ctx.arguments.get("command", "")

    # Step 1: Absolute deny patterns
    for pattern in ctx.policy.deny_patterns:
        if re.search(pattern, cmd, re.IGNORECASE):
            return ("deny", f"🚫 Command matches blocked pattern: {pattern}")

    # Step 2: Command-injection structural check
    if re.search(r'`[^`]+`', cmd) or re.search(r'\$\([^)]+\)', cmd):
        inner = re.findall(r'`([^`]+)`|\$\(([^)]+)\)', cmd)
        for groups in inner:
            subcmd = groups[0] or groups[1]
            sub_low = subcmd.lower()
            if any(kw in sub_low for kw in _INJECTION_SENSITIVE):
                return ("deny",
                        f"Command injection accessing sensitive data: {subcmd}")

    # Step 3: Env exfiltration
    if _EXFIL_RE.search(cmd):
        return ("deny", "Environment variable exfiltration attempt")

    # Step 4: Obfuscation — admin needs to eyeball
    if _OBFUSCATE_RE.search(cmd):
        return ("needs_approval",
                "Command uses encoding/eval that may obfuscate intent")

    # Step 5: Delete-class — red line
    if re.search(r'\brm\s+', cmd):
        return ("deny", "🚫 红线: rm (delete) commands are blocked by default")
    if re.search(r'\bxargs\s+rm\b', cmd):
        return ("deny", "🚫 红线: xargs rm (piped delete) is blocked by default")
    if re.search(r'-delete\b', cmd):
        return ("deny", "🚫 红线: find -delete is blocked by default")
    if re.search(r'-exec\s+rm\b', cmd):
        return ("deny", "🚫 红线: find -exec rm is blocked by default")

    # Step 6: Subcommand dispatch
    cmd_risk, cmd_reason = _analyze_bash_command(cmd)
    if cmd_risk == "low":
        return ("allow", f"Bash auto-approved: {cmd_reason}")
    if cmd_risk == "moderate":
        if ctx.policy.auto_approve_moderate:
            return ("allow", f"Bash moderate auto-approved: {cmd_reason}")
        return ("agent_approvable", f"Bash moderate: {cmd_reason}")
    # cmd_risk == "high" → abstain; next rule (moderate_gate / high_default)
    # handles it under the tool's own risk level.
    return None
