"""MCPClientStub — the *caller* layer of the MCP call architecture.

Architectural position
══════════════════════

This is what agent-level code (``app.tools``, skills, workflow
actions) sees when it wants to invoke an MCP tool. It is intentionally
thin:

- it does **not** know how to launch subprocesses
- it does **not** know how to parse JSON-RPC
- it does **not** know which node an MCP lives on
- it does **not** know what credentials the MCP needs

All it knows is how to locate the router and forward the call.
Everything else is the router's and the dispatcher's job.

Why a separate layer (if it's so thin)?
───────────────────────────────────────
Two reasons:

1. **Stable API for upstream code.** ``app.tools._tool_mcp_call`` used
   to be 260 lines of subprocess + env + protocol code. Now it is
   one call: ``client_stub.call(...)``. When we later pool
   subprocesses, add remote-node routing, or move credentials out of
   worker processes, ``app.tools`` never has to change.

2. **The seam for out-of-process routing.** Today every caller lives
   in the same process as the hub, so :meth:`call` does a direct
   Python call into :class:`MCPCallRouter`. Tomorrow when agent
   workers live in subprocesses and cannot see the hub directly,
   this stub is the file that gains an RPC transport — and
   *nothing upstream has to change*. That's the whole point of
   having a client/router split.

Return shape
────────────
For the legacy ``tools.py`` API we return a string (historical
contract). Structured callers can use :meth:`call_structured` to get
the :class:`CallResult` directly and inspect ``error_kind``, etc.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger("tudou.mcp.client")


# ───────────────────────── router locator ─────────────────────────
#
# In-process today: grab the router from the hub singleton. The seam
# for out-of-process calls lives here — replace this helper with an
# RPC client when we add a worker↔hub channel, and nothing else
# changes.

def _get_router():
    try:
        from .. import hub as _hub_mod  # noqa: F401
    except Exception:
        pass
    try:
        # Prefer explicit hub singleton
        from ..hub import get_hub  # type: ignore
        h = get_hub()
        router = getattr(h, "mcp_router", None)
        if router is not None:
            return router
    except Exception:
        pass
    # Fallback: construct a router on demand. Only used in tests /
    # smoke-imports; real runs should always have hub.mcp_router set.
    try:
        from .router import MCPCallRouter
        return MCPCallRouter(hub=None)
    except Exception as e:
        logger.error("client_stub: unable to locate router: %s", e)
        return None


# ─────────────────────────── public API ───────────────────────────

def call_structured(
    caller_id: str,
    mcp_id: str,
    tool: str,
    arguments: Optional[dict] = None,
):
    """Make an MCP call and return the structured :class:`CallResult`.

    Prefer this over :func:`call` for any new code. The string return
    of :func:`call` exists only to preserve the legacy tool-function
    contract used by ``app.tools``.
    """
    router = _get_router()
    if router is None:
        # Lazy import so this module doesn't hard-depend on router at
        # import time (important for circular-import safety during
        # hub bootstrap).
        from .router import CallResult, ERR_INTERNAL_ROUTER
        return CallResult(
            ok=False,
            error_kind=ERR_INTERNAL_ROUTER,
            error_message="router not available",
        )
    return router.call(
        caller_id=caller_id,
        mcp_id=mcp_id,
        tool=tool,
        arguments=arguments or {},
    )


def call(
    caller_id: str,
    mcp_id: str,
    tool: str,
    arguments: Optional[dict] = None,
) -> str:
    """Legacy string-return API, for :mod:`app.tools` compatibility.

    Renders a :class:`CallResult` into the same string shapes the old
    :func:`_tool_mcp_call` produced. Keep the formatting stable — it
    is what agent LLM prompts have been trained to read.
    """
    cr = call_structured(caller_id, mcp_id, tool, arguments)
    if cr.ok:
        content = cr.content
        if isinstance(content, (dict, list)):
            return json.dumps(content, ensure_ascii=False)
        return "" if content is None else str(content)

    # Error formatting mirrors the legacy ``_tool_mcp_call`` strings
    # so any LLM-facing error parsing keeps working.
    from .router import (
        ERR_NOT_AUTHORIZED, ERR_MCP_NOT_FOUND, ERR_MCP_DISABLED,
        ERR_HANDSHAKE, ERR_TIMEOUT, ERR_TOOL, ERR_LAUNCH,
        ERR_TRANSPORT, ERR_NO_CONFIG,
    )
    kind = cr.error_kind
    msg = cr.error_message or kind
    if kind == ERR_NOT_AUTHORIZED:
        return f"Error: {msg}"
    if kind in (ERR_MCP_NOT_FOUND, ERR_NO_CONFIG):
        return f"Error: MCP '{mcp_id}' is not configured: {msg}"
    if kind == ERR_MCP_DISABLED:
        return f"Error: MCP '{mcp_id}' is disabled."
    if kind == ERR_LAUNCH:
        tail = f"\nstderr: {cr.stderr_tail}" if cr.stderr_tail else ""
        return f"Error: MCP '{mcp_id}' failed to launch: {msg}{tail}"
    if kind == ERR_HANDSHAKE:
        tail = f"\nstderr: {cr.stderr_tail}" if cr.stderr_tail else ""
        return f"Error: MCP '{mcp_id}' handshake failed: {msg}{tail}"
    if kind == ERR_TIMEOUT:
        return f"Error: MCP '{mcp_id}' tool '{tool}' timed out: {msg}"
    if kind == ERR_TOOL:
        return f"MCP error: {msg}"
    if kind == ERR_TRANSPORT:
        return f"Error: {msg}"
    return f"Error: MCP '{mcp_id}' tool '{tool}' failed ({kind}): {msg}"


def list_mcps(caller_id: str) -> str:
    """Return the human-readable list of MCPs bound to ``caller_id``.

    For each bound MCP the output includes the tool manifest read
    from the :class:`ToolManifestCache` on the MCP manager. The
    contract with upstream agent prompts is: tool names shown here
    are authoritative, never guessed.
    """
    router = _get_router()
    if router is None:
        return "Error: MCP router not available."
    mcps = router.list_for(caller_id) or []
    if not mcps:
        return ("No MCPs are bound to this agent. "
                "Ask the admin to bind an MCP (e.g. email, slack, github) "
                "via Portal → MCP Manager.")

    try:
        from .manager import get_mcp_manager as _gmm
        _mgr = _gmm()
    except Exception:
        _mgr = None

    lines = ["Bound MCPs for this agent:", ""]
    for m in mcps:
        mid = getattr(m, "id", "?")
        lines.append(
            f"- {getattr(m, 'name', '') or mid} "
            f"(id={mid}, transport={getattr(m, 'transport', '?')}, "
            f"enabled={getattr(m, 'enabled', True)})"
        )
        entry = None
        if _mgr is not None:
            try:
                entry = _mgr.get_tool_manifest(mid)
            except Exception:
                entry = None
        if entry is None or not entry.tools:
            if entry is not None and entry.error:
                lines.append(f"    tools: (discovery failed: {entry.error})")
            else:
                lines.append("    tools: (not yet discovered)")
        else:
            for t in entry.tools:
                tname = str(t.get("name") or "").replace("`", "")
                if not tname:
                    continue
                desc = str(t.get("description") or "").replace("`", "").strip()
                schema = t.get("inputSchema") or {}
                props = schema.get("properties") if isinstance(schema, dict) else None
                required = set(schema.get("required") or []) if isinstance(schema, dict) else set()
                if isinstance(props, dict) and props:
                    parts = []
                    for pname in list(props.keys())[:6]:
                        pname_clean = str(pname).replace("`", "")
                        parts.append(pname_clean if pname in required else f"{pname_clean}?")
                    if len(props) > 6:
                        parts.append("...")
                    sig = "(" + ", ".join(parts) + ")"
                else:
                    sig = "()"
                desc_short = (desc[:120] + "…") if len(desc) > 120 else desc
                suffix = f" — {desc_short}" if desc_short else ""
                lines.append(f"    - {tname}{sig}{suffix}")
        lines.append("")
    lines.append(
        "Usage: mcp_call(mcp_id=<id from above>, tool=<tool name from list>, arguments={...})"
    )
    return "\n".join(lines)


__all__ = ["call", "call_structured", "list_mcps"]
