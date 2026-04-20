"""Rule: admin-configured global denylist.

Highest precedence after RED — retires specific tools (e.g. the
deprecated ``create_pptx_advanced``) without editing per-agent profiles.
"""
from __future__ import annotations

from typing import Optional

from .base import ToolCheckContext, Verdict


def rule_global_denylist(ctx: ToolCheckContext) -> Optional[Verdict]:
    if ctx.tool_name in ctx.policy.global_denylist:
        return ("deny", (
            f"🚫 Tool '{ctx.tool_name}' is on the global denylist. "
            "Admin can remove it from 工具与审批 settings."
        ))
    return None
