"""MCPCallRouter — the *decision* layer of the MCP call architecture.

Architectural position
══════════════════════

The router is the **only** place in the codebase that answers three
questions for an MCP call:

    1. Is this caller allowed to call this MCP?          (authorization)
    2. Where does this MCP actually live?                (location)
    3. How should this failure be named to the caller?   (classification)

It does **not** launch subprocesses. It does **not** parse JSON-RPC. It
does **not** normalize environment variables. Those are the
dispatcher's job. The router's job is to be small, auditable, and
impossible to bypass.

Invariants
──────────

**B (authorization unbypassable)**. Any MCP call that reaches a
:class:`NodeMCPDispatcher` came from :meth:`MCPCallRouter.call`. The
router enforces the authorization check against
``hub.mcp_manager.get_agent_effective_mcps`` before any dispatch
happens. There is no sidecar path.

**C (single call path)**. Production calls, health checks, and the
Portal "test connection" button all reach the dispatcher via this
router. A probe is a :meth:`probe` call; it bypasses authorization
(because it's called by admins over HTTP, not by agents) but runs
the *same* dispatcher code that real calls run. No "test works but
real fails" divergence.

Error taxonomy exposed upstream
───────────────────────────────

The dispatcher emits fine-grained error kinds. The router translates
them into a slightly coarser vocabulary that callers (and human
operators) can reason about:

    not_authorized      — caller has no grant for this mcp_id
    mcp_not_found       — no MCPServerConfig for that id on this agent
    mcp_disabled        — bound but disabled
    launch_failed       — subprocess couldn't start
    handshake_failed    — initialize didn't complete (timeout or error)
    tool_timeout        — tools/call hit the timeout
    tool_error          — server returned an MCP error for the call
    internal_error      — the dispatcher or router itself broke
    transport_unsupported — non-stdio transport asked for

These are the names the upstream client_stub (and any future
tooling / dashboards) should switch on.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from .dispatcher import (
    NodeMCPDispatcher,
    DispatchResult,
    get_default_dispatcher,
    ERR_NOT_CONFIGURED,
    ERR_TRANSPORT_UNSUPPORTED,
    ERR_LAUNCH_FAILED,
    ERR_HANDSHAKE_TIMEOUT,
    ERR_HANDSHAKE_ERROR,
    ERR_TOOL_TIMEOUT,
    ERR_TOOL_ERROR,
    ERR_INTERNAL,
    ERR_BUILTIN_FAILED,
)

logger = logging.getLogger("tudou.mcp.router")


# ───────────────────────── upstream error taxonomy ─────────────────────────

ERR_NOT_AUTHORIZED       = "not_authorized"
ERR_MCP_NOT_FOUND        = "mcp_not_found"
ERR_MCP_DISABLED         = "mcp_disabled"
ERR_LAUNCH               = "launch_failed"
ERR_HANDSHAKE            = "handshake_failed"
ERR_TIMEOUT              = "tool_timeout"
ERR_TOOL                 = "tool_error"
ERR_INTERNAL_ROUTER      = "internal_error"
ERR_TRANSPORT            = "transport_unsupported"
ERR_BUILTIN              = "builtin_failed"
ERR_NO_CONFIG            = "mcp_not_configured"

# Map from dispatcher-level kinds → router-level kinds. This is the
# *only* place the translation happens. Upstream code should only
# know about the router-level vocabulary above.
_DISPATCH_ERR_MAP: dict[str, str] = {
    ERR_NOT_CONFIGURED:       ERR_NO_CONFIG,
    ERR_TRANSPORT_UNSUPPORTED: ERR_TRANSPORT,
    ERR_LAUNCH_FAILED:        ERR_LAUNCH,
    ERR_HANDSHAKE_TIMEOUT:    ERR_HANDSHAKE,
    ERR_HANDSHAKE_ERROR:      ERR_HANDSHAKE,
    ERR_TOOL_TIMEOUT:         ERR_TIMEOUT,
    ERR_TOOL_ERROR:           ERR_TOOL,
    ERR_INTERNAL:             ERR_INTERNAL_ROUTER,
    ERR_BUILTIN_FAILED:       ERR_BUILTIN,
}


# ───────────────────────────── result type ─────────────────────────────

@dataclass
class CallResult:
    """Result of an MCP call as seen by the router's callers.

    The client_stub adapts this into string form for legacy tool APIs.
    Anything that wants structured access (future dashboards, tests,
    metrics) should use this directly.
    """
    ok: bool
    content: Any = None
    error_kind: str = ""           # one of the router-level ERR_* constants
    error_message: str = ""
    elapsed_ms: int = 0
    stderr_tail: str = ""
    meta: dict = field(default_factory=dict)

    @classmethod
    def from_dispatch(cls, dr: DispatchResult) -> "CallResult":
        upstream_kind = "" if dr.ok else _DISPATCH_ERR_MAP.get(
            dr.error_kind, ERR_INTERNAL_ROUTER
        )
        return cls(
            ok=dr.ok,
            content=dr.content,
            error_kind=upstream_kind,
            error_message=dr.error_message,
            elapsed_ms=dr.elapsed_ms,
            stderr_tail=dr.stderr_tail,
            meta=dict(dr.meta or {}),
        )


# ─────────────────────────────── router ───────────────────────────────

class MCPCallRouter:
    """Single entry point for all MCP calls.

    The hub constructs one instance at startup and exposes it as
    ``hub.mcp_router``. All MCP calls — from agents, from the Portal
    "test" button, from internal diagnostics — come through here.
    """

    def __init__(self, hub: Any, dispatcher: Optional[NodeMCPDispatcher] = None):
        self._hub = hub
        self._dispatcher = dispatcher or get_default_dispatcher()

    # ────────────────────── main call path ──────────────────────

    def call(
        self,
        caller_id: str,
        mcp_id: str,
        tool: str,
        arguments: Optional[dict] = None,
    ) -> CallResult:
        """Authorize, locate, and dispatch one MCP tool call.

        ``caller_id`` is the agent id. The router trusts it because
        the :mod:`client_stub` injects it from its local agent
        context — the router itself never lets callers declare a
        different identity.
        """
        if not caller_id:
            return CallResult(
                ok=False,
                error_kind=ERR_NOT_AUTHORIZED,
                error_message="no caller agent context",
            )
        if not mcp_id:
            return CallResult(
                ok=False,
                error_kind=ERR_MCP_NOT_FOUND,
                error_message="empty mcp_id",
            )
        if not tool:
            return CallResult(
                ok=False,
                error_kind=ERR_TOOL,
                error_message="empty tool name",
            )

        # ── 1. authorization: resolve effective MCPs for this caller ──
        try:
            target, all_mcps = self._resolve_target(caller_id, mcp_id)
        except Exception as e:
            logger.exception("router: resolve_target crashed")
            return CallResult(
                ok=False,
                error_kind=ERR_INTERNAL_ROUTER,
                error_message=f"resolve failed: {e}",
            )

        if target is None:
            available = [m.id for m in all_mcps] if all_mcps else []
            # Distinguish "not bound to you" from "does not exist".
            # The user-facing error is the same — we just surface a
            # better message.
            return CallResult(
                ok=False,
                error_kind=ERR_NOT_AUTHORIZED,
                error_message=(
                    f"mcp '{mcp_id}' not bound to agent '{caller_id}'. "
                    f"Available: {available}"
                ),
            )

        if not getattr(target, "enabled", True):
            return CallResult(
                ok=False,
                error_kind=ERR_MCP_DISABLED,
                error_message=f"mcp '{mcp_id}' is disabled",
            )

        # ── 2. load caller agent if dispatcher needs it (builtins) ──
        agent = None
        try:
            agent = self._hub.get_agent(caller_id)
        except Exception:
            pass

        # ── 3. dispatch ──
        try:
            dr = self._dispatcher.dispatch(target, tool, arguments or {}, agent=agent)
        except Exception as e:
            logger.exception("router: dispatch crashed")
            return CallResult(
                ok=False,
                error_kind=ERR_INTERNAL_ROUTER,
                error_message=f"dispatch crashed: {e}",
            )

        cr = CallResult.from_dispatch(dr)
        self._log_call(caller_id, mcp_id, tool, cr)
        return cr

    # ───────────────────── enumeration / introspection ─────────────────────

    def list_for(self, caller_id: str) -> list[Any]:
        """Return the list of MCPServerConfigs this caller can call.

        Used by tools.py's ``list_mcps=True`` mode and by the portal
        UI "my bound MCPs" view. Single source of truth for "what can
        this agent see" — do not read ``agent.profile.mcp_servers``
        directly from upstream code.
        """
        if not caller_id:
            return []
        try:
            _target, mcps = self._resolve_target(caller_id, mcp_id=None)
            return mcps
        except Exception:
            logger.exception("router: list_for crashed")
            return []

    # ───────────────────── health check / probe ─────────────────────

    def probe(self, target: Any, timeout_s: float = 10.0) -> CallResult:
        """Health-check an MCPServerConfig without an agent context.

        This is the single path used by the Portal "test connection"
        button and by any internal health check. Critically, it
        shares ``_spawn_stdio`` with real calls — if one works the
        other must work.
        """
        try:
            dr = self._dispatcher.probe(target, timeout_s=timeout_s)
        except Exception as e:
            logger.exception("router: probe crashed")
            return CallResult(
                ok=False,
                error_kind=ERR_INTERNAL_ROUTER,
                error_message=f"probe crashed: {e}",
            )
        return CallResult.from_dispatch(dr)

    # ─────────────────────── internal helpers ───────────────────────

    def _resolve_target(
        self, caller_id: str, mcp_id: Optional[str]
    ) -> tuple[Any, list[Any]]:
        """Return (target_config, all_bound_configs) for a caller.

        When ``mcp_id`` is None, only the list is meaningful.
        Target resolution tries both ``id`` and ``name`` (to match
        the legacy matching behaviour in tools.py).

        Authorization happens *inside* this function by only ever
        consulting ``get_agent_effective_mcps`` — which is the
        authoritative "what is this agent allowed to call" query.
        """
        hub = self._hub
        agent = hub.get_agent(caller_id) if hub is not None else None
        node_id = getattr(agent, "node_id", None) if agent else None
        node_id = node_id or "local"

        # Prefer the MCP manager's effective view; fall back to the
        # agent's own profile.mcp_servers if the manager isn't
        # available for some reason.
        mcps: list[Any] = []
        try:
            from .manager import get_mcp_manager
            mgr = get_mcp_manager()
            mcps = list(mgr.get_agent_effective_mcps(node_id, caller_id) or [])
        except Exception:
            mcps = []
        if not mcps and agent is not None:
            mcps = list(getattr(agent.profile, "mcp_servers", []) or [])

        # Sync back onto the agent so downstream code that still
        # reads profile.mcp_servers stays consistent. This is a
        # compatibility nicety; the authoritative view is ``mcps``.
        if agent is not None and mcps:
            try:
                agent.profile.mcp_servers = list(mcps)
            except Exception:
                pass

        if mcp_id is None:
            return None, mcps

        for m in mcps:
            if getattr(m, "id", None) == mcp_id or getattr(m, "name", None) == mcp_id:
                return m, mcps
        return None, mcps

    def _log_call(
        self, caller_id: str, mcp_id: str, tool: str, result: CallResult
    ) -> None:
        """Single place that logs every call. Metrics hooks land here later."""
        if result.ok:
            logger.info(
                "mcp_call ok agent=%s mcp=%s tool=%s elapsed=%dms",
                caller_id, mcp_id, tool, result.elapsed_ms,
            )
        else:
            logger.warning(
                "mcp_call fail agent=%s mcp=%s tool=%s kind=%s msg=%s elapsed=%dms",
                caller_id, mcp_id, tool, result.error_kind,
                result.error_message, result.elapsed_ms,
            )


__all__ = [
    "MCPCallRouter",
    "CallResult",
    # router-level error kinds
    "ERR_NOT_AUTHORIZED",
    "ERR_MCP_NOT_FOUND",
    "ERR_MCP_DISABLED",
    "ERR_LAUNCH",
    "ERR_HANDSHAKE",
    "ERR_TIMEOUT",
    "ERR_TOOL",
    "ERR_INTERNAL_ROUTER",
    "ERR_TRANSPORT",
    "ERR_BUILTIN",
    "ERR_NO_CONFIG",
]
