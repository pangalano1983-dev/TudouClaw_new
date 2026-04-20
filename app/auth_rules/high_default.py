"""Rule: default / HIGH risk → needs admin approval.

The terminal rule in the chain. Runs last and always returns a verdict
(so ``check_tool`` is guaranteed to get one). Any tool that wasn't
allowed, denied, or caught by an earlier rule falls through here.
"""
from __future__ import annotations

from typing import Optional

from .base import ToolCheckContext, Verdict


def rule_high_default(ctx: ToolCheckContext) -> Optional[Verdict]:
    return ("needs_approval",
            f"⚠️ 高风险: Tool '{ctx.tool_name}' requires admin approval (risk: HIGH)")
