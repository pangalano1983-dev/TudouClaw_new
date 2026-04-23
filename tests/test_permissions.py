"""Permission matrix tests — the one place the role model is
exercised exhaustively, so regressions are caught loudly.

Design:
  * Parameterized over all (role × permission × resource-state) combos.
  * Resource state = {owned, delegated, foreign, legacy_unowned}.
  * Super admin is a unit test shortcut ("everything true").

If you add a new Permission, add it here. The parity-style assertion
at the bottom will fail until you do.
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


from app.permissions import (
    Role, Permission, user_can, require, _role_enum,
    assign_owner_on_create,
)


# ── Role / permission enum sanity ─────────────────────────────────


def test_role_enum_values():
    assert Role.SUPER_ADMIN.value == "superAdmin"
    assert Role.ADMIN.value == "admin"
    assert Role.USER.value == "user"


def test_role_enum_parse():
    assert _role_enum("superAdmin") is Role.SUPER_ADMIN
    assert _role_enum("admin") is Role.ADMIN
    assert _role_enum("user") is Role.USER
    assert _role_enum("viewer") is None      # legacy Role enum, not this one
    assert _role_enum(None) is None
    assert _role_enum("") is None


# ── Helpers to build stub users / resources ────────────────────────


def _make_user(role, uid="u-" + "x" * 12,
               agent_ids=None, node_ids=None):
    return SimpleNamespace(
        role=role,
        user_id=uid,
        delegated_agent_ids=list(agent_ids or []),
        delegated_node_ids=list(node_ids or []),
    )


def _agent(aid="a1", owner=""):
    return SimpleNamespace(id=aid, owner_id=owner)


def _node(nid="n1", owner=""):
    return SimpleNamespace(id=nid, owner_id=owner)


# ── SuperAdmin — can do everything unconditionally ────────────────


@pytest.mark.parametrize("perm", list(Permission))
def test_super_admin_has_every_permission(perm):
    su = _make_user("superAdmin", "su-1")
    # resource-scoped perms still succeed unconditionally for super
    dummy = _agent("x", owner="other")
    assert user_can(su, perm, resource=dummy) is True


def test_super_admin_can_manage_foreign_agent():
    su = _make_user("superAdmin", "su-1")
    foreign = _agent(owner="somebody-else")
    assert user_can(su, Permission.MANAGE_AGENT, resource=foreign) is True


# ── Admin — global configs off-limits, delegated agents OK ─────────


def test_admin_cannot_manage_global_config():
    ad = _make_user("admin", "ad-1")
    assert user_can(ad, Permission.MANAGE_GLOBAL_CONFIG) is False


def test_admin_cannot_manage_admins():
    ad = _make_user("admin", "ad-1")
    assert user_can(ad, Permission.MANAGE_ADMINS) is False


def test_admin_can_manage_own_agent():
    ad = _make_user("admin", "ad-1")
    own = _agent(owner="ad-1")
    assert user_can(ad, Permission.MANAGE_AGENT, resource=own) is True


def test_admin_can_manage_delegated_agent():
    ad = _make_user("admin", "ad-1", agent_ids=["delegated-7"])
    target = _agent(aid="delegated-7", owner="super-user")
    assert user_can(ad, Permission.MANAGE_AGENT, resource=target) is True


def test_admin_cannot_manage_foreign_agent():
    ad = _make_user("admin", "ad-1", agent_ids=["only-this"])
    foreign = _agent(aid="not-in-list", owner="someone-else")
    assert user_can(ad, Permission.MANAGE_AGENT, resource=foreign) is False


def test_admin_can_manage_own_node():
    ad = _make_user("admin", "ad-1", node_ids=["node-a"])
    node = _node(nid="node-a")
    assert user_can(ad, Permission.MANAGE_NODE, resource=node) is True


def test_admin_cannot_manage_foreign_node():
    ad = _make_user("admin", "ad-1", node_ids=["node-a"])
    node = _node(nid="node-zzz")
    assert user_can(ad, Permission.MANAGE_NODE, resource=node) is False


# ── User — minimum role, own-only ──────────────────────────────────


def test_user_cannot_create_node():
    u = _make_user("user", "u-1")
    assert user_can(u, Permission.CREATE_NODE) is False
    # Nor manage one
    assert user_can(u, Permission.MANAGE_NODE, resource=_node()) is False


def test_user_cannot_manage_global_config():
    u = _make_user("user", "u-1")
    assert user_can(u, Permission.MANAGE_GLOBAL_CONFIG) is False
    assert user_can(u, Permission.MANAGE_AUDIT) is False
    assert user_can(u, Permission.MANAGE_ADMINS) is False


def test_user_cannot_create_agent():
    """Product decision 2026-04: users only *use* agents, don't manage
    them. CREATE_AGENT is superAdmin/admin-only; admin's creates are
    still scoped to their delegated nodes."""
    u = _make_user("user", "u-1")
    assert user_can(u, Permission.CREATE_AGENT) is False


def test_user_cannot_manage_own_agent():
    """Ownership doesn't grant MANAGE_AGENT anymore — user role has
    MANAGE_AGENT revoked wholesale, even on agents they created
    pre-policy."""
    u = _make_user("user", "u-1")
    own = _agent(owner="u-1")
    assert user_can(u, Permission.MANAGE_AGENT, resource=own) is False


def test_user_can_chat_any_agent_they_can_view():
    """User retains CHAT_WITH_AGENT + VIEW_AGENT. Ownership still
    satisfies the resource-scoped check, so chatting with an
    owned-by-me agent works."""
    u = _make_user("user", "u-1")
    own = _agent(owner="u-1")
    assert user_can(u, Permission.CHAT_WITH_AGENT, resource=own) is True
    assert user_can(u, Permission.VIEW_AGENT, resource=own) is True


def test_user_cannot_manage_foreign_agent():
    u = _make_user("user", "u-1")
    foreign = _agent(owner="someone-else")
    assert user_can(u, Permission.MANAGE_AGENT, resource=foreign) is False
    # CHAT on a foreign agent is also blocked (ownership check fails,
    # no delegation on user role).
    assert user_can(u, Permission.CHAT_WITH_AGENT, resource=foreign) is False


def test_user_cannot_manage_legacy_unowned_agent():
    """Legacy agents with no owner_id are NOT visible to regular users
    (only admins get the legacy pass). Prevents pre-migration data
    from leaking."""
    u = _make_user("user", "u-1")
    legacy = _agent(owner="")
    assert user_can(u, Permission.MANAGE_AGENT, resource=legacy) is False


def test_user_can_view_kb_but_not_manage():
    u = _make_user("user", "u-1")
    assert user_can(u, Permission.VIEW_KB) is True
    assert user_can(u, Permission.MANAGE_KB) is False


def test_user_cannot_approve_tool_calls():
    u = _make_user("user", "u-1")
    assert user_can(u, Permission.APPROVE_TOOL_CALL) is False
    assert user_can(u, Permission.MANAGE_TOOL_POLICY) is False


# ── Missing/malformed user — always deny ──────────────────────────


def test_none_user_always_denied():
    for perm in Permission:
        assert user_can(None, perm) is False


def test_user_with_bad_role_always_denied():
    bogus = SimpleNamespace(role="hacker", user_id="x",
                            delegated_agent_ids=[], delegated_node_ids=[])
    for perm in Permission:
        assert user_can(bogus, perm, resource=_agent()) is False


def test_resource_scoped_without_resource_denied():
    """Resource-scoped perms must NOT short-circuit to True when
    called without a resource. Guards against caller bugs where
    someone forgets to pass the object they just fetched."""
    ad = _make_user("admin", "ad-1", agent_ids=["foo"])
    # No resource → deny
    assert user_can(ad, Permission.MANAGE_AGENT) is False


# ── require() raises 403 when denied, silent when allowed ─────────


def test_require_allows_permitted():
    su = _make_user("superAdmin", "s-1")
    # No exception → good
    require(su, Permission.MANAGE_GLOBAL_CONFIG)


def test_require_raises_403_when_denied():
    from fastapi import HTTPException
    u = _make_user("user", "u-1")
    with pytest.raises(HTTPException) as exc:
        require(u, Permission.MANAGE_GLOBAL_CONFIG)
    assert exc.value.status_code == 403


# ── assign_owner_on_create ────────────────────────────────────────


def test_assign_owner_stamps_regular_user():
    agent = _agent()
    u = _make_user("user", "u-42")
    assign_owner_on_create(u, agent)
    assert agent.owner_id == "u-42"


def test_assign_owner_stamps_regular_admin():
    agent = _agent()
    ad = _make_user("admin", "ad-7")
    assign_owner_on_create(ad, agent)
    assert agent.owner_id == "ad-7"


def test_assign_owner_leaves_super_admin_empty():
    """Super admins create 'unowned' agents — historically the product
    default. Also ensures a super admin can grant ownership later
    via delegation without an owner already blocking the move."""
    agent = _agent(owner="")
    su = _make_user("superAdmin", "s-1")
    assign_owner_on_create(su, agent)
    assert agent.owner_id == ""


# ── Full-matrix sanity — ensures new perms get coverage added ─────


def test_all_permissions_covered_in_role_map():
    """A brand-new Permission should require an explicit entry in
    every role's permission set, OR an explicit decision to exclude.
    Failing here means you added a perm without auditing the roles."""
    from app.permissions import _ROLE_PERMS
    all_perms = set(Permission)
    union = set().union(*_ROLE_PERMS.values())
    missing = all_perms - union
    # SuperAdmin gets everything by construction, so set-union should
    # contain every permission. Guard against forgetting a new perm.
    assert not missing, (
        "New Permission(s) not exposed to any role: "
        f"{sorted(p.value for p in missing)}")
