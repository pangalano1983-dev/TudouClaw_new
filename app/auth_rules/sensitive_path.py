"""Rule: write_file / edit_file targeting a sensitive path → needs_approval.

We don't outright deny — admin may legitimately need to edit .env or
~/.ssh/config — but we force a human eyeball on those calls.
"""
from __future__ import annotations

from typing import Optional

from .base import ToolCheckContext, Verdict


_SENSITIVE_FRAGMENTS = (
    "/etc/", "/usr/", "/bin/", "/sbin/", "/boot/",
    "/sys/", "/proc/", "~/.ssh/", "~/.bashrc",
    ".env", "credentials", "secret", "password",
)


def rule_sensitive_path(ctx: ToolCheckContext) -> Optional[Verdict]:
    if ctx.tool_name not in ("write_file", "edit_file"):
        return None
    path = (ctx.arguments.get("path") or "").lower()
    for frag in _SENSITIVE_FRAGMENTS:
        if frag in path:
            return ("needs_approval",
                    f"Writing to sensitive path: {ctx.arguments.get('path', '')}")
    return None
