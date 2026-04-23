"""Centralized permission model — the single source of truth for
*who can do what to which resource*.

Design
------
Three roles (``superAdmin``, ``admin``, ``user``) and a flat
permission enum. Each role maps to a set of permissions. Some
permissions are *resource-scoped* — for those, a check also consults
the delegation lists on ``AdminUser`` (``agent_ids`` / ``node_ids``)
or the resource's own ``owner_id`` field.

Why a separate module (not stuffed into auth.py):
  * auth.py already does JWT, session, password hashing, audit log.
    It's huge. Mixing role-based access control into it makes the
    permission surface hard to see. This file is tiny and greppable.
  * Route handlers import one symbol: ``require(perm, resource=…)``
    or call ``user_can(user, perm, resource=…)``. That's the whole API.
  * Tests can exercise the matrix in isolation.

Usage
-----
    from app.permissions import Permission, require, user_can

    @router.post("/agent/{agent_id}/delete")
    async def del_agent(agent_id, user=Depends(get_current_user), hub=...):
        agent = hub.get_agent(agent_id) or raise 404
        require(user, Permission.MANAGE_AGENT, resource=agent)
        ...

    if user_can(user, Permission.MANAGE_GLOBAL_CONFIG):
        # show admin-only UI
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger("tudou.permissions")


# ---------------------------------------------------------------------------
# Role + Permission enums
# ---------------------------------------------------------------------------

class Role(str, Enum):
    SUPER_ADMIN = "superAdmin"
    ADMIN = "admin"
    USER = "user"


class Permission(str, Enum):
    # Global configuration — only superAdmin.
    MANAGE_GLOBAL_CONFIG = "manage_global_config"       # providers, MCP, LLM tiers, audit, tokens
    MANAGE_AUDIT = "manage_audit"                       # view audit logs
    MANAGE_ADMINS = "manage_admins"                     # create/delete admin users + delegation

    # Node lifecycle — superAdmin can create/delete; admin can manage
    # ONLY those node_ids delegated to them; user cannot touch nodes.
    CREATE_NODE = "create_node"
    MANAGE_NODE = "manage_node"                         # resource-scoped
    MANAGE_NODE_CONFIG = "manage_node_config"           # resource-scoped
    VIEW_NODE = "view_node"                             # resource-scoped

    # Agent lifecycle — superAdmin: anything; admin: delegated agents +
    # their own creations; user: only their own creations.
    CREATE_AGENT = "create_agent"
    MANAGE_AGENT = "manage_agent"                       # resource-scoped (owner + delegation)
    VIEW_AGENT = "view_agent"                           # resource-scoped
    CHAT_WITH_AGENT = "chat_with_agent"                 # resource-scoped

    # Knowledge / RAG — global resource, admin can write, user read-only
    MANAGE_KB = "manage_kb"
    VIEW_KB = "view_kb"

    # Tool approvals / denylist — admin
    MANAGE_TOOL_POLICY = "manage_tool_policy"
    APPROVE_TOOL_CALL = "approve_tool_call"


# Baseline permission set per role. Resource-scoped permissions are
# *potentially* granted to a role here — the runtime check narrows
# to the specific resource (see user_can below).
_ROLE_PERMS: dict[Role, frozenset[Permission]] = {
    Role.SUPER_ADMIN: frozenset(Permission),  # everything
    Role.ADMIN: frozenset({
        Permission.CREATE_NODE,            # but only scoped by delegation
        Permission.MANAGE_NODE,
        Permission.MANAGE_NODE_CONFIG,
        Permission.VIEW_NODE,
        Permission.CREATE_AGENT,
        Permission.MANAGE_AGENT,
        Permission.VIEW_AGENT,
        Permission.CHAT_WITH_AGENT,
        Permission.MANAGE_KB,
        Permission.VIEW_KB,
        Permission.MANAGE_TOOL_POLICY,
        Permission.APPROVE_TOOL_CALL,
        Permission.MANAGE_AUDIT,           # admin can view audit
    }),
    Role.USER: frozenset({
        # User can ONLY use agents — no management privileges.
        # Revoked 2026-04: CREATE_AGENT / MANAGE_AGENT per product decision
        # ("user 只能使用 agent，不能管理").
        Permission.VIEW_AGENT,
        Permission.CHAT_WITH_AGENT,
        Permission.VIEW_KB,                # read-only
    }),
}


# Permissions whose grant depends on the resource (ownership / delegation)
_RESOURCE_SCOPED = {
    Permission.MANAGE_NODE,
    Permission.MANAGE_NODE_CONFIG,
    Permission.VIEW_NODE,
    Permission.MANAGE_AGENT,
    Permission.VIEW_AGENT,
    Permission.CHAT_WITH_AGENT,
}


# ---------------------------------------------------------------------------
# Helpers to normalize role + resource ownership
# ---------------------------------------------------------------------------

def _role_enum(value: Any) -> Optional[Role]:
    if value is None:
        return None
    if isinstance(value, Role):
        return value
    try:
        return Role(str(value))
    except ValueError:
        return None


def _owner_id_of(resource: Any) -> str:
    """Pull owner_id off a resource (agent / node / dict). Return ""
    when the resource has no owner info yet — legacy objects created
    before the owner_id field existed. They're treated as owner="" and
    only superAdmin can touch them until migrated."""
    if resource is None:
        return ""
    if isinstance(resource, dict):
        return str(resource.get("owner_id") or "")
    return str(getattr(resource, "owner_id", "") or "")


def _resource_id(resource: Any) -> str:
    if resource is None:
        return ""
    if isinstance(resource, dict):
        return str(resource.get("id") or "")
    return str(getattr(resource, "id", "") or "")


# ---------------------------------------------------------------------------
# Public check API
# ---------------------------------------------------------------------------

def user_can(user: Any, perm: Permission, resource: Any = None) -> bool:
    """True iff ``user`` is allowed to do ``perm`` on ``resource``.

    ``user`` is a CurrentUser-ish object with .role and .user_id. It
    may optionally expose ``.delegated_agent_ids`` / ``.delegated_node_ids``.
    If absent, we fall back to looking the user up via the admin manager.
    """
    if user is None:
        return False

    role = _role_enum(getattr(user, "role", None))
    if role is None:
        return False

    # Super admin: unconditional yes.
    if role is Role.SUPER_ADMIN:
        return True

    perms = _ROLE_PERMS.get(role, frozenset())
    if perm not in perms:
        return False

    # Non-scoped permission — role grant is enough.
    if perm not in _RESOURCE_SCOPED:
        return True

    # Resource-scoped: need to own OR be delegated the resource.
    if resource is None:
        # Scoped perm with no resource context → deny (caller bug-guard).
        return False

    user_id = getattr(user, "user_id", "") or ""

    # Ownership grants everything the role allows.
    owner = _owner_id_of(resource)
    if owner and owner == user_id:
        return True

    # Delegation: admin users can have node ids assigned. All admin
    # access (agents + configs) derives from **node ownership** — an
    # admin can manage agents that run on their delegated nodes, plus
    # the configs on those nodes. There is no separate per-agent
    # delegation list (product decision 2026-04: admin's boundary =
    # their nodes).
    if role is Role.ADMIN:
        rid = _resource_id(resource)
        if not rid:
            return False
        delegated_nodes = _delegated_nodes(user)
        # Agent-class: look up the agent's node_id, check if admin owns
        # that node.
        if perm in {Permission.MANAGE_AGENT, Permission.VIEW_AGENT,
                    Permission.CHAT_WITH_AGENT}:
            agent_node_id = _agent_node_id(resource)
            if agent_node_id and agent_node_id in delegated_nodes:
                return True
            # Back-compat fallback: legacy deployments may still carry
            # a per-agent delegation list. Honor it if present, but do
            # not encourage new data through it (UI no longer sets it).
            return rid in _delegated_agents(user)
        # Node-class: direct node id membership
        if perm in {Permission.MANAGE_NODE, Permission.MANAGE_NODE_CONFIG,
                    Permission.VIEW_NODE}:
            return rid in delegated_nodes

    return False


def _agent_node_id(resource: Any) -> str:
    """Pull node_id off an Agent-ish resource. Used by the admin
    node-scoped check. Returns "" when the resource has no node
    info (not an agent, or legacy record)."""
    if resource is None:
        return ""
    if isinstance(resource, dict):
        return str(resource.get("node_id") or "")
    return str(getattr(resource, "node_id", "") or "")


def require(user: Any, perm: Permission, resource: Any = None) -> None:
    """Raise FastAPI 403 when user_can returns False. Meant to be
    called from inside route handlers once they've fetched the
    resource (so a 404 vs 403 is disambiguated correctly).
    """
    if user_can(user, perm, resource):
        return
    from fastapi import HTTPException, status
    role = str(getattr(user, "role", "?"))
    uid = str(getattr(user, "user_id", "?"))[:12]
    rid = _resource_id(resource) or "-"
    logger.info("permission denied: user=%s (role=%s) perm=%s resource=%s",
                uid, role, perm.value, rid)
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Permission denied: {perm.value}",
    )


# ---------------------------------------------------------------------------
# Delegation helpers — resolve the user's delegated resource lists.
# CurrentUser may carry them on .claims; if not, look them up in
# the admin manager so stale tokens still get live delegation.
# ---------------------------------------------------------------------------

def _delegated_agents(user: Any) -> set[str]:
    direct = getattr(user, "delegated_agent_ids", None)
    if direct is not None:
        return set(direct)
    return _lookup_admin_lists(user).get("agent_ids", set())


def _delegated_nodes(user: Any) -> set[str]:
    direct = getattr(user, "delegated_node_ids", None)
    if direct is not None:
        return set(direct)
    return _lookup_admin_lists(user).get("node_ids", set())


def _lookup_admin_lists(user: Any) -> dict[str, set[str]]:
    """Fallback lookup via the admin manager. Cached per-call on the
    user object to avoid repeat manager hits during one request."""
    cached = getattr(user, "_perm_cache", None)
    if cached is not None:
        return cached
    uid = getattr(user, "user_id", "") or ""
    out: dict[str, set[str]] = {"agent_ids": set(), "node_ids": set()}
    if not uid:
        try:
            setattr(user, "_perm_cache", out)
        except Exception:
            pass
        return out
    try:
        from .auth import get_auth
        admin = get_auth().admin_mgr.get_admin(uid)
        if admin is not None:
            out["agent_ids"] = set(admin.agent_ids or [])
            out["node_ids"] = set(admin.node_ids or [])
    except Exception as e:
        logger.debug("admin lookup for permission check failed: %s", e)
    try:
        setattr(user, "_perm_cache", out)
    except Exception:
        pass
    return out


# ---------------------------------------------------------------------------
# Agent ownership helper — used by agent-creation handlers.
# ---------------------------------------------------------------------------

def assign_owner_on_create(user: Any, agent: Any) -> None:
    """Stamp an owner_id on a freshly-created agent.

    Super admins create "unowned" agents (``owner_id=""``) — historically
    the product's defaults. When a regular admin or user creates an
    agent, it's pinned to their user_id so ``MANAGE_AGENT`` only
    succeeds for them (or whoever gets delegated explicitly).
    """
    if agent is None or user is None:
        return
    role = _role_enum(getattr(user, "role", None))
    if role is Role.SUPER_ADMIN:
        # Let it stay "" so any admin inheriting the delegation can
        # manage it. Super admin retains implicit full access anyway.
        return
    uid = getattr(user, "user_id", "") or ""
    if not uid:
        return
    try:
        setattr(agent, "owner_id", uid)
    except Exception:
        # dataclass has no owner_id yet — fine, migration will add it.
        pass
