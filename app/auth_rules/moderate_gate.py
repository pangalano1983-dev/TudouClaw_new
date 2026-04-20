"""Rule: MODERATE risk → allow (if auto-approve) or agent_approvable.

Auto-approve is an admin toggle. When off, a moderate-risk call can be
approved by an authorized agent (CXO/PM) instead of requiring an admin.
"""
from __future__ import annotations

from typing import Optional

from .base import ToolCheckContext, Verdict


def rule_moderate_gate(ctx: ToolCheckContext) -> Optional[Verdict]:
    if ctx.risk != "moderate":
        return None
    if ctx.policy.auto_approve_moderate:
        return ("allow", "")
    return ("agent_approvable",
            f"Tool '{ctx.tool_name}' is moderate risk — "
            "agent approval or admin approval needed")
