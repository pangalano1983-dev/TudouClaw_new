"""Tests for the rule-chain architecture.

These are ADDITIONAL to the existing policy regression tests. They
verify:
  1. Each rule is testable in isolation (no hidden coupling to check_tool).
  2. The chain respects declared priority order.
  3. Adding a new rule is a one-line change.

If any of these break, someone has coupled rules in a way that
reintroduces the waterfall. Push back.
"""
from __future__ import annotations

import sys
import types

import pytest


# ── Fixture: clean context + policy ─────────────────────────────────

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


# ── Individual rules: each decides alone ────────────────────────────

def test_rule_global_denylist_hit(policy):
    from app.auth_rules import rule_global_denylist
    policy.global_denylist.add("evil_tool")
    verdict = rule_global_denylist(_ctx(policy, "evil_tool"))
    assert verdict and verdict[0] == "deny"
    assert "global denylist" in verdict[1].lower()


def test_rule_global_denylist_abstains(policy):
    from app.auth_rules import rule_global_denylist
    assert rule_global_denylist(_ctx(policy, "read_file")) is None


def test_rule_red_line(policy):
    from app.auth_rules import rule_red_line
    verdict = rule_red_line(_ctx(policy, "delete_file", risk="red"))
    assert verdict and verdict[0] == "deny"
    assert "红线" in verdict[1] or "RED" in verdict[1]
    assert rule_red_line(_ctx(policy, "read_file", risk="low")) is None


def test_rule_low_risk_allow(policy):
    from app.auth_rules import rule_low_risk_allow
    assert rule_low_risk_allow(_ctx(policy, "read_file", risk="low")) == ("allow", "")
    assert rule_low_risk_allow(_ctx(policy, "bash", risk="high")) is None


def test_rule_session_approved(policy):
    from app.auth_rules import rule_session_approved
    policy.session_approvals.add(("agent_A", "http_request"))
    hit = rule_session_approved(_ctx(policy, "http_request", agent_id="agent_A"))
    assert hit and hit[0] == "allow" and "Session" in hit[1]
    # no agent → no check
    assert rule_session_approved(_ctx(policy, "http_request")) is None
    # different agent → no hit
    assert rule_session_approved(_ctx(policy, "http_request", agent_id="agent_B")) is None


def test_rule_sensitive_path(policy):
    from app.auth_rules import rule_sensitive_path
    v = rule_sensitive_path(_ctx(policy, "write_file", arguments={"path": "/etc/hosts"}))
    assert v and v[0] == "needs_approval" and "/etc/hosts" in v[1]
    # other tools abstain
    assert rule_sensitive_path(_ctx(policy, "read_file", arguments={"path": "/etc/hosts"})) is None
    # non-sensitive path abstains
    assert rule_sensitive_path(_ctx(policy, "write_file", arguments={"path": "/tmp/x"})) is None


def test_rule_moderate_gate_auto_approve(policy):
    from app.auth_rules import rule_moderate_gate
    policy.auto_approve_moderate = True
    assert rule_moderate_gate(_ctx(policy, "http_request", risk="moderate")) == ("allow", "")


def test_rule_moderate_gate_needs_agent_approval(policy):
    from app.auth_rules import rule_moderate_gate
    policy.auto_approve_moderate = False
    v = rule_moderate_gate(_ctx(policy, "http_request", risk="moderate"))
    assert v and v[0] == "agent_approvable"


def test_rule_high_default_always_fires(policy):
    from app.auth_rules import rule_high_default
    v = rule_high_default(_ctx(policy, "anything", risk="high"))
    assert v and v[0] == "needs_approval"


# ── Chain-level invariants ──────────────────────────────────────────

def test_chain_is_terminal(policy):
    """The last rule must ALWAYS return a verdict (chain invariant)."""
    from app.auth_rules import rule_high_default
    assert rule_high_default(_ctx(policy, "anything")) is not None


def test_chain_priority_denylist_beats_granted_skill(policy):
    """Global denylist wins even if a granted skill would have allowed."""
    # Build a fake hub: skill_X grants tool "banned_tool"
    class FakeManifest:
        name = "skill_X"
        tools = ["banned_tool"]
    class FakeInstall:
        manifest = FakeManifest()
    class FakeReg:
        def list_for_agent(self, aid): return [FakeInstall()]
    llm_mod = sys.modules.setdefault("app.llm", types.ModuleType("app.llm"))
    llm_mod._active_hub = type("H", (), {"skill_registry": FakeReg()})
    # Also put it on denylist
    policy.global_denylist.add("banned_tool")

    verdict, reason = policy.check_tool(
        "banned_tool", {}, agent_id="agent_A",
    )
    assert verdict == "deny"
    assert "global denylist" in reason.lower()


def test_chain_priority_red_beats_skill_grant(policy):
    """RED risk ignores skill-grant shortcut."""
    class FakeManifest:
        name = "my-skill"
        tools = ["delete_file"]
    class FakeInstall:
        manifest = FakeManifest()
    class FakeReg:
        def list_for_agent(self, aid): return [FakeInstall()]
    llm_mod = sys.modules.setdefault("app.llm", types.ModuleType("app.llm"))
    llm_mod._active_hub = type("H", (), {"skill_registry": FakeReg()})

    verdict, reason = policy.check_tool(
        "delete_file", {}, agent_id="agent_A",
    )
    assert verdict == "deny"
    assert "RED" in reason or "红线" in reason


def test_rules_are_callables():
    """Basic sanity: every item in RULES is callable and takes ctx."""
    from app.auth_rules import RULES
    assert len(RULES) >= 5, "too few rules — someone broke the chain"
    for rule in RULES:
        assert callable(rule), f"non-callable in RULES: {rule}"


def test_adding_a_rule_does_not_require_check_tool_changes(policy):
    """Demonstrate the main selling point of the refactor.

    A rule added to the RULES list (typically in __init__.py) takes
    effect immediately without any surgery on check_tool. We prove it
    by monkey-patching a sentinel rule onto the chain.
    """
    from app.auth_rules import RULES
    sentinel_called = {"n": 0}
    def rule_sentinel(ctx):
        sentinel_called["n"] += 1
        return ("allow", "sentinel-hit") if ctx.tool_name == "sentinel_tool" else None

    RULES.insert(0, rule_sentinel)
    try:
        verdict, reason = policy.check_tool("sentinel_tool", {})
        assert verdict == "allow"
        assert reason == "sentinel-hit"
        assert sentinel_called["n"] == 1
    finally:
        RULES.remove(rule_sentinel)  # cleanup so other tests aren't affected
