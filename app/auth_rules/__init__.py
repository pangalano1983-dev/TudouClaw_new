"""Tool-check policy engine — rule chain.

The priority order IS the file order below. Changing priorities = moving
rules in this list. No ``if`` branch surgery elsewhere.

Anyone adding a new rule:
  1. Create ``app/auth_rules/<verb_noun>.py`` with a single public
     function of type ``Rule``.
  2. Append it to ``RULES`` at the correct priority.
  3. Add a rule-level unit test asserting (abstain case, hit case).

Don't import this package in anything other than ``app.auth``. It's
internal to the ToolPolicy.
"""
from __future__ import annotations

from typing import Tuple

from .base import Rule, ToolCheckContext, Verdict
from .global_denylist import rule_global_denylist
from .red_line import rule_red_line
from .low_risk_allow import rule_low_risk_allow
from .granted_skill import rule_covered_by_granted_skill
from .session_approved import rule_session_approved
from .bash_analyzer import rule_bash_analyzer
from .sensitive_path import rule_sensitive_path
from .moderate_gate import rule_moderate_gate
from .high_default import rule_high_default


# Order matters — this is the policy priority.
# Must preserve the original check_tool waterfall:
#   1. global_denylist      — admin killswitch
#   2. red_line             — unconditional deny
#   3. low_risk_allow       — baseline read-only tools
#   4. granted_skill        — skill grant implies tool approval
#   5. session_approved     — "approve for session" button
#   6. bash_analyzer        — per-subcommand analysis; may delegate
#                              high-risk bash to moderate/high rules
#   7. sensitive_path       — write/edit to /etc/, ~/.ssh/, .env, ...
#   8. moderate_gate        — MODERATE → allow / agent_approvable
#   9. high_default         — terminal; always returns a verdict
RULES: list[Rule] = [
    rule_global_denylist,
    rule_red_line,
    rule_low_risk_allow,
    rule_covered_by_granted_skill,
    rule_session_approved,
    rule_bash_analyzer,
    rule_sensitive_path,
    rule_moderate_gate,
    rule_high_default,
]


def run_rules(ctx: ToolCheckContext) -> Verdict:
    """Run the chain; first rule that returns non-None wins.

    ``rule_high_default`` is terminal and always returns, so we're
    guaranteed to produce a verdict. The ``RuntimeError`` fallback is
    defensive — it should only fire if someone removes the terminal
    rule without adding a new one.
    """
    for rule in RULES:
        verdict = rule(ctx)
        if verdict is not None:
            return verdict
    raise RuntimeError(
        "auth_rules: no rule produced a verdict. "
        "Did someone remove rule_high_default?"
    )


__all__ = [
    "Rule", "ToolCheckContext", "Verdict",
    "RULES", "run_rules",
    # Individual rules exported for unit tests
    "rule_global_denylist", "rule_red_line", "rule_low_risk_allow",
    "rule_covered_by_granted_skill", "rule_session_approved",
    "rule_bash_analyzer", "rule_sensitive_path",
    "rule_moderate_gate", "rule_high_default",
]
