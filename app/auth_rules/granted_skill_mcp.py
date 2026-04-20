"""Rule: mcp_call covered by a granted skill's ``depends_on_mcp`` → auto-allow.

Why
===
Companion to ``rule_covered_by_granted_skill`` (which handles plain
tools). Manifests declare MCP dependencies as::

    depends_on_mcp:
      - id: my-mcp-server
        tools: [submit_task, poll_task]

Granting the skill to an agent IS an admin approval for those
MCP-level calls. Without this rule, every ``mcp_call`` would hit the
MODERATE risk gate and re-prompt.

Match semantics
===============
Only fires for ``tool_name == "mcp_call"``. Extracts the target
``(mcp_id, tool)`` from ``arguments`` and looks for a granted skill
whose manifest has a matching dependency. Two sub-cases:

  * ``tools=[]`` on the dependency  → the skill author opted for
    "any tool on this MCP" (wildcard). We allow, but the skill's
    author carries responsibility for the MCP's scope.
  * non-empty ``tools``            → strict whitelist; tool must be
    in the list.

Abstains (returns ``None``) for anything else so the next rule in
the chain handles it.
"""
from __future__ import annotations

import sys as _sys
from typing import Optional

from .base import ToolCheckContext, Verdict


def rule_covered_by_granted_skill_mcp(ctx: ToolCheckContext) -> Optional[Verdict]:
    if ctx.tool_name != "mcp_call":
        return None
    if not ctx.agent_id:
        return None

    target_mcp = (ctx.arguments.get("mcp_id") or "").strip()
    target_tool = (ctx.arguments.get("tool") or "").strip()
    if not target_mcp:
        return None  # malformed call — let validation fail downstream

    try:
        llm_mod = _sys.modules.get("app.llm")
        hub = getattr(llm_mod, "_active_hub", None) if llm_mod else None
        reg = getattr(hub, "skill_registry", None) if hub else None
        if reg is None or not hasattr(reg, "list_for_agent"):
            return None

        for inst in reg.list_for_agent(ctx.agent_id):
            for dep in getattr(inst.manifest, "depends_on_mcp", []) or []:
                if dep.id != target_mcp:
                    continue
                allowed = list(getattr(dep, "tools", []) or [])
                # Empty allowed list = wildcard for this MCP (skill author's call).
                if not allowed or target_tool in allowed:
                    return ("allow", (
                        f"Covered by granted skill "
                        f"'{inst.manifest.name}' → MCP '{target_mcp}'"
                    ))
    except Exception:
        # Registry hiccup — fall through so the moderate gate still gates.
        return None
    return None
