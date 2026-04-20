"""Rule: session-scoped pre-approval.

When the admin clicks "Approve for this session" on a pending approval
dialog, the (agent_id, tool_name) pair is added to
``ToolPolicy.session_approvals``. Subsequent calls for that pair bypass
the risk gate entirely for the session lifetime.
"""
from __future__ import annotations

from typing import Optional

from .base import ToolCheckContext, Verdict


def rule_session_approved(ctx: ToolCheckContext) -> Optional[Verdict]:
    if not ctx.agent_id:
        return None
    if (ctx.agent_id, ctx.tool_name) in ctx.policy.session_approvals:
        return ("allow", "Session-approved")
    return None
