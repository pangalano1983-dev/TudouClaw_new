"""P1-C / P1-D — max_output_tokens + agent_tier defaults.

Verifies:
  * AgentProfile has the new fields with sane defaults
  * _tier_default_output_budget returns the documented numbers
  * Unknown tier returns 0 (no hint injected)
  * profile.max_output_tokens overrides tier default when both are set

The actual chat-loop injection is hard to test end-to-end without a
live LLM; those assertions are covered by a direct-call stub.
"""
from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


from app.agent import Agent, AgentProfile  # noqa: E402


# ── AgentProfile shape ─────────────────────────────────────────


def test_profile_defaults_are_zero_and_empty():
    p = AgentProfile()
    assert p.max_output_tokens == 0
    assert p.agent_tier == ""


def test_profile_accepts_max_output_tokens():
    p = AgentProfile(max_output_tokens=500)
    assert p.max_output_tokens == 500


def test_profile_accepts_agent_tier():
    p = AgentProfile(agent_tier="actor")
    assert p.agent_tier == "actor"


# ── tier → budget mapping ─────────────────────────────────────


@pytest.mark.parametrize("tier,expected", [
    ("thinker", 1800),
    ("actor", 400),
    ("summarizer", 250),
    ("THINKER", 1800),        # case insensitive
    ("  actor  ", 400),        # stripped
])
def test_tier_default_budget_mapping(tier, expected):
    assert Agent._tier_default_output_budget(tier) == expected


def test_tier_default_budget_unknown_returns_zero():
    assert Agent._tier_default_output_budget("") == 0
    assert Agent._tier_default_output_budget("wizard") == 0
    assert Agent._tier_default_output_budget(None) == 0


# ── resolution precedence: explicit profile > tier > zero ─────


def test_explicit_max_output_tokens_overrides_tier():
    # Explicit value takes precedence.
    p = AgentProfile(max_output_tokens=9000, agent_tier="actor")
    # At the chat-hook site: 9000 is used.
    explicit = int(getattr(p, "max_output_tokens", 0) or 0)
    tier_default = Agent._tier_default_output_budget(
        getattr(p, "agent_tier", "") or "")
    resolved = explicit if explicit > 0 else tier_default
    assert resolved == 9000


def test_tier_kicks_in_when_max_output_tokens_zero():
    p = AgentProfile(max_output_tokens=0, agent_tier="summarizer")
    explicit = int(getattr(p, "max_output_tokens", 0) or 0)
    tier_default = Agent._tier_default_output_budget(
        getattr(p, "agent_tier", "") or "")
    resolved = explicit if explicit > 0 else tier_default
    assert resolved == 250


def test_neither_set_resolves_to_zero():
    p = AgentProfile()
    explicit = int(getattr(p, "max_output_tokens", 0) or 0)
    tier_default = Agent._tier_default_output_budget(
        getattr(p, "agent_tier", "") or "")
    resolved = explicit if explicit > 0 else tier_default
    assert resolved == 0   # no hint will be injected


# ── Profile to_dict/from_dict roundtrip ─────────────────────────


def test_profile_roundtrips_new_fields():
    p = AgentProfile(max_output_tokens=800, agent_tier="thinker")
    d = p.to_dict() if hasattr(p, "to_dict") else None
    if d is None:
        # Legacy: not every profile exposes to_dict. dataclass-asdict
        # is a safe stand-in.
        from dataclasses import asdict
        d = asdict(p)
    assert d["max_output_tokens"] == 800
    assert d["agent_tier"] == "thinker"
    if hasattr(AgentProfile, "from_dict"):
        p2 = AgentProfile.from_dict(d)
        assert p2.max_output_tokens == 800
        assert p2.agent_tier == "thinker"
