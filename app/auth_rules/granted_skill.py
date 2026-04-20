"""Rule: tool call covered by an already-granted skill → auto-allow.

Semantics
=========
Granting a skill to an agent via 技能商店 IS an admin approval for the
set of tools (and MCPs) that skill's manifest declares. Re-asking for
approval on every call is noise: admin already said yes once.

Implementation reads the live ``hub.skill_registry``. If the registry
isn't available (tests without a hub, startup race), the rule abstains
and lets the chain fall through to the risk-based rules.

Future extension: MCP shortcut — a sibling rule can check
``inst.manifest.mcps`` for the mcp_call target. That's a 10-line file,
not another branch here.
"""
from __future__ import annotations

import sys as _sys
from typing import Optional

from .base import ToolCheckContext, Verdict


def rule_covered_by_granted_skill(ctx: ToolCheckContext) -> Optional[Verdict]:
    if not ctx.agent_id:
        return None  # no agent context → can't check grants
    try:
        llm_mod = _sys.modules.get("app.llm")
        hub = getattr(llm_mod, "_active_hub", None) if llm_mod else None
        reg = getattr(hub, "skill_registry", None) if hub else None
        if reg is None or not hasattr(reg, "list_for_agent"):
            return None
        for inst in reg.list_for_agent(ctx.agent_id):
            whitelist = set(getattr(inst.manifest, "tools", []) or [])
            if ctx.tool_name in whitelist:
                return ("allow",
                        f"Covered by granted skill '{inst.manifest.name}'")
    except Exception:
        # Registry blew up — safer to fall through than to break the
        # whole tool pipeline.
        return None
    return None
