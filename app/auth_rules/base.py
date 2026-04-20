"""Rule-chain base types for the tool-check policy engine.

Design
======
``ToolPolicy.check_tool`` used to be a 130-line waterfall with 9 distinct
decision rules interleaved with config lookups and one ~80-line inline
bash analyzer. Every new rule added another ``if`` branch somewhere in
the middle and forced the whole file to be re-read.

The rule chain inverts that: each rule is a self-contained callable that
returns either a final ``Verdict`` or ``None`` (abstain → try the next
rule). The order of rules in ``RULES`` is the priority order, which
makes the policy readable at a glance and trivially testable per-rule.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, TYPE_CHECKING, Tuple

if TYPE_CHECKING:
    from ..auth import ToolPolicy


Verdict = Tuple[str, str]
"""(verdict, reason). verdict ∈ {"allow","deny","needs_approval","agent_approvable"}."""


@dataclass
class ToolCheckContext:
    """Everything a rule needs to decide on a single tool call.

    ``policy`` is kept as a back-reference so rules can read (but not
    mutate) ToolPolicy config like ``global_denylist`` / ``deny_patterns``
    / ``auto_approve_moderate`` / ``session_approvals``. We don't copy
    those onto the context because they can change at runtime (admin
    toggles); the rule should see the current value.
    """
    tool_name: str
    arguments: dict
    agent_id: str
    agent_name: str
    agent_priority: int
    risk: str                      # pre-resolved by policy.get_risk()
    policy: "ToolPolicy"


# A rule is a pure function: given a context, return a Verdict or None.
#   None  → abstain, next rule
#   tuple → final decision, chain stops
Rule = Callable[[ToolCheckContext], Optional[Verdict]]
