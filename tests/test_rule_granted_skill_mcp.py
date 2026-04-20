"""Unit tests for rule_covered_by_granted_skill_mcp.

Matches the pattern in tests/test_auth_rule_chain.py — each new rule
gets its own focused file with: hit cases, abstain cases, and at
least one chain-level interaction test (to prove the rule was wired
into RULES correctly).
"""
from __future__ import annotations

import sys
import types

import pytest


@pytest.fixture
def policy():
    from app.auth import ToolPolicy
    return ToolPolicy()


def _ctx(policy, tool_name, *, agent_id="", arguments=None, risk=None):
    from app.auth_rules import ToolCheckContext
    return ToolCheckContext(
        tool_name=tool_name,
        arguments=arguments or {},
        agent_id=agent_id,
        agent_name="",
        agent_priority=3,
        risk=(risk if risk is not None else policy.get_risk(tool_name)),
        policy=policy,
    )


def _fake_hub(agent_id, mcp_id, tools, skill_name="my-skill"):
    """Build a stand-in hub with one granted skill declaring a single MCP dep."""
    class FakeDep:
        def __init__(self, i, ts):
            self.id = i
            self.tools = ts
    class FakeManifest:
        def __init__(self, name, dep):
            self.name = name
            self.tools = []                              # empty tool whitelist
            self.depends_on_mcp = [dep] if dep else []
    class FakeInstall:
        def __init__(self, manifest):
            self.manifest = manifest
    class FakeReg:
        def __init__(self, mapping): self._m = mapping
        def list_for_agent(self, aid): return self._m.get(aid, [])
    dep = FakeDep(mcp_id, tools)
    install = FakeInstall(FakeManifest(skill_name, dep))
    reg = FakeReg({agent_id: [install]})
    llm_mod = sys.modules.setdefault("app.llm", types.ModuleType("app.llm"))
    llm_mod._active_hub = type("H", (), {"skill_registry": reg})
    return llm_mod


def _clear_hub():
    mod = sys.modules.get("app.llm")
    if mod is not None:
        mod._active_hub = None


# ── Happy path ──────────────────────────────────────────────────────

def test_mcp_whitelist_hit(policy):
    """skill.depends_on_mcp declares (srv, [tool]) → mcp_call allow."""
    from app.auth_rules import rule_covered_by_granted_skill_mcp
    _fake_hub("agent_A", "srv-1", ["submit_task", "poll_task"])
    try:
        v = rule_covered_by_granted_skill_mcp(_ctx(
            policy, "mcp_call", agent_id="agent_A",
            arguments={"mcp_id": "srv-1", "tool": "submit_task"},
        ))
        assert v and v[0] == "allow"
        assert "my-skill" in v[1] and "srv-1" in v[1]
    finally:
        _clear_hub()


def test_mcp_wildcard_empty_tools_hits(policy):
    """Empty tools list = wildcard: any tool on this MCP is allowed."""
    from app.auth_rules import rule_covered_by_granted_skill_mcp
    _fake_hub("agent_A", "srv-1", [])  # no tool whitelist
    try:
        v = rule_covered_by_granted_skill_mcp(_ctx(
            policy, "mcp_call", agent_id="agent_A",
            arguments={"mcp_id": "srv-1", "tool": "anything_the_server_exposes"},
        ))
        assert v and v[0] == "allow"
    finally:
        _clear_hub()


# ── Abstain paths ───────────────────────────────────────────────────

def test_non_mcp_call_abstains(policy):
    from app.auth_rules import rule_covered_by_granted_skill_mcp
    _fake_hub("agent_A", "srv-1", ["submit_task"])
    try:
        # Not mcp_call — this rule must stay out
        v = rule_covered_by_granted_skill_mcp(_ctx(
            policy, "bash", agent_id="agent_A",
            arguments={"command": "ls"},
        ))
        assert v is None
    finally:
        _clear_hub()


def test_no_agent_id_abstains(policy):
    from app.auth_rules import rule_covered_by_granted_skill_mcp
    _fake_hub("agent_A", "srv-1", ["submit_task"])
    try:
        v = rule_covered_by_granted_skill_mcp(_ctx(
            policy, "mcp_call", agent_id="",
            arguments={"mcp_id": "srv-1", "tool": "submit_task"},
        ))
        assert v is None
    finally:
        _clear_hub()


def test_wrong_mcp_id_abstains(policy):
    """Agent has skill for srv-1 but is trying srv-2 → abstain (moderate gate handles)."""
    from app.auth_rules import rule_covered_by_granted_skill_mcp
    _fake_hub("agent_A", "srv-1", ["submit_task"])
    try:
        v = rule_covered_by_granted_skill_mcp(_ctx(
            policy, "mcp_call", agent_id="agent_A",
            arguments={"mcp_id": "srv-2", "tool": "submit_task"},
        ))
        assert v is None
    finally:
        _clear_hub()


def test_tool_not_in_whitelist_abstains(policy):
    """mcp_id matches but tool isn't whitelisted → abstain."""
    from app.auth_rules import rule_covered_by_granted_skill_mcp
    _fake_hub("agent_A", "srv-1", ["submit_task"])
    try:
        v = rule_covered_by_granted_skill_mcp(_ctx(
            policy, "mcp_call", agent_id="agent_A",
            arguments={"mcp_id": "srv-1", "tool": "admin_reset_db"},
        ))
        assert v is None
    finally:
        _clear_hub()


def test_missing_mcp_id_abstains(policy):
    """Caller forgot mcp_id — we can't match; let downstream validation fail."""
    from app.auth_rules import rule_covered_by_granted_skill_mcp
    _fake_hub("agent_A", "srv-1", ["submit_task"])
    try:
        v = rule_covered_by_granted_skill_mcp(_ctx(
            policy, "mcp_call", agent_id="agent_A",
            arguments={"tool": "submit_task"},  # no mcp_id
        ))
        assert v is None
    finally:
        _clear_hub()


def test_no_hub_abstains(policy):
    """Registry unavailable (tests without a hub) → abstain, don't crash."""
    from app.auth_rules import rule_covered_by_granted_skill_mcp
    _clear_hub()  # ensure no hub
    v = rule_covered_by_granted_skill_mcp(_ctx(
        policy, "mcp_call", agent_id="agent_A",
        arguments={"mcp_id": "srv-1", "tool": "submit_task"},
    ))
    assert v is None


# ── Chain-level: priority is respected ──────────────────────────────

def test_chain_denylist_still_beats_mcp_grant(policy):
    """Admin put mcp_call on global denylist → deny even if skill grants it."""
    _fake_hub("agent_A", "srv-1", ["submit_task"])
    policy.global_denylist.add("mcp_call")
    try:
        verdict, reason = policy.check_tool(
            "mcp_call",
            {"mcp_id": "srv-1", "tool": "submit_task"},
            agent_id="agent_A",
        )
        assert verdict == "deny"
        assert "denylist" in reason.lower()
    finally:
        _clear_hub()


def test_chain_moderate_gate_runs_when_not_covered(policy):
    """mcp_call without a matching skill grant falls to moderate gate."""
    policy.auto_approve_moderate = False
    _fake_hub("agent_A", "srv-1", ["submit_task"])
    try:
        # Different mcp_id → rule_covered_by_granted_skill_mcp abstains
        verdict, _ = policy.check_tool(
            "mcp_call",
            {"mcp_id": "srv-OTHER", "tool": "submit_task"},
            agent_id="agent_A",
        )
        # mcp_call is MODERATE by default → agent_approvable
        assert verdict == "agent_approvable"
    finally:
        _clear_hub()


def test_chain_mcp_rule_position_in_RULES():
    """Invariant: granted_skill_mcp runs BEFORE session_approved + moderate_gate.

    If someone moves it later the shortcut stops working (moderate
    gate captures mcp_call first).
    """
    from app.auth_rules import (
        RULES, rule_covered_by_granted_skill_mcp,
        rule_session_approved, rule_moderate_gate,
    )
    idx_mcp = RULES.index(rule_covered_by_granted_skill_mcp)
    idx_session = RULES.index(rule_session_approved)
    idx_moderate = RULES.index(rule_moderate_gate)
    assert idx_mcp < idx_session
    assert idx_mcp < idx_moderate
