"""Rule: RED-risk tools are unconditionally blocked.

RED is the "red-line" tier — delete_file / rm_rf / drop_table / truncate
etc. Admin must explicitly re-classify to a lower tier before they can
be used. The rule is short but sits high in the chain because no
skill-grant or session approval should be able to bypass it.
"""
from __future__ import annotations

from typing import Optional

from .base import ToolCheckContext, Verdict


def rule_red_line(ctx: ToolCheckContext) -> Optional[Verdict]:
    if ctx.risk == "red":
        return ("deny",
                f"🚫 红线操作: '{ctx.tool_name}' is permanently blocked (risk: RED)")
    return None
