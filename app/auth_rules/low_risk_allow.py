"""Rule: LOW-risk tools are always allowed.

Baseline read-only / bookkeeping tools (read_file, web_search, glob_files,
datetime_calc, get_skill_guide, knowledge_lookup, ...). See
``DEFAULT_TOOL_RISK`` in app/auth.py.
"""
from __future__ import annotations

from typing import Optional

from .base import ToolCheckContext, Verdict


def rule_low_risk_allow(ctx: ToolCheckContext) -> Optional[Verdict]:
    if ctx.risk == "low":
        return ("allow", "")
    return None
