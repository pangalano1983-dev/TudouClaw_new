"""通用门禁 Day 1 — tool_policy.command_patterns.

Covers:
  * add / remove / list admin APIs on ToolPolicy
  * regex + label validation
  * rule_command_patterns verdict behavior (deny, needs_approval, abstain)
  * scope matching (global / role:<name> / agent:<id>)
  * command field scanning (command / script / cmd / code)
  * chain priority — runs AFTER global_denylist, BEFORE red_line/low_risk
  * persistence across restart via set_persist_path
"""
from __future__ import annotations

import os
import sys
import tempfile

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


from app.auth import ToolPolicy  # noqa: E402
from app.auth_rules.base import ToolCheckContext  # noqa: E402
from app.auth_rules.command_patterns import rule_command_patterns  # noqa: E402


# ── tiny helpers ────────────────────────────────────────────────────


def _ctx(tp: ToolPolicy, tool="bash", arguments=None,
         agent_id="a-alice", agent_priority=3,
         risk="moderate") -> ToolCheckContext:
    return ToolCheckContext(
        tool_name=tool,
        arguments=arguments or {},
        agent_id=agent_id,
        agent_name="Alice",
        agent_priority=agent_priority,
        risk=risk,
        policy=tp,
    )


@pytest.fixture
def tp() -> ToolPolicy:
    return ToolPolicy()


# ── admin API ───────────────────────────────────────────────────────


def test_add_command_pattern_minimal(tp):
    e = tp.add_command_pattern(
        pattern=r"^terraform\s+apply",
        reason="prod write blocked",
        label="tf_apply",
    )
    assert e["pattern"].startswith("^terraform")
    assert e["scope"] == "global"
    assert e["verdict"] == "deny"
    assert e["label"] == "tf_apply"
    assert tp.list_command_patterns() == [e]


def test_add_command_pattern_auto_label_when_missing(tp):
    e = tp.add_command_pattern(pattern=r"^helm install")
    assert e["label"].startswith("cp_")
    assert len(e["label"]) >= 5


def test_add_command_pattern_overwrites_same_label(tp):
    tp.add_command_pattern(pattern=r"^foo", label="x")
    tp.add_command_pattern(pattern=r"^bar", label="x")
    patterns = tp.list_command_patterns()
    assert len(patterns) == 1
    assert patterns[0]["pattern"] == r"^bar"


def test_add_command_pattern_invalid_regex_raises(tp):
    with pytest.raises(ValueError):
        tp.add_command_pattern(pattern=r"(unclosed", label="bad")


def test_add_command_pattern_rejects_bad_verdict(tp):
    with pytest.raises(ValueError):
        tp.add_command_pattern(pattern=r"^x", verdict="nope")


def test_add_command_pattern_rejects_malformed_scope(tp):
    with pytest.raises(ValueError):
        tp.add_command_pattern(pattern=r"^x", scope="weird")


def test_remove_command_pattern(tp):
    tp.add_command_pattern(pattern=r"^x", label="ok")
    assert tp.remove_command_pattern("ok") is True
    assert tp.remove_command_pattern("ok") is False
    assert tp.list_command_patterns() == []


def test_remove_command_pattern_empty_label(tp):
    assert tp.remove_command_pattern("") is False


def test_list_command_patterns_filter_scope(tp):
    tp.add_command_pattern(pattern=r"^a", label="g", scope="global")
    tp.add_command_pattern(pattern=r"^b", label="r",
                           scope="role:cloud_delivery")
    assert len(tp.list_command_patterns()) == 2
    assert len(tp.list_command_patterns(scope="global")) == 1
    assert tp.list_command_patterns(scope="role:cloud_delivery")[0]["label"] == "r"


# ── rule verdict ────────────────────────────────────────────────────


def test_rule_no_patterns_abstains(tp):
    v = rule_command_patterns(_ctx(tp, arguments={"command": "terraform apply"}))
    assert v is None


def test_rule_no_command_args_abstains(tp):
    tp.add_command_pattern(pattern=r"^anything", label="x")
    # arguments has no command-like key → rule abstains (not blocks).
    v = rule_command_patterns(_ctx(tp, arguments={"note": "terraform apply"}))
    assert v is None


def test_rule_matching_pattern_denies(tp):
    tp.add_command_pattern(
        pattern=r"^terraform\s+apply",
        reason="prod write blocked",
        label="tf_apply",
    )
    v = rule_command_patterns(
        _ctx(tp, arguments={"command": "terraform apply -auto-approve"}))
    assert v is not None
    verdict, reason = v
    assert verdict == "deny"
    assert "prod write blocked" in reason


def test_rule_matching_pattern_needs_approval(tp):
    tp.add_command_pattern(
        pattern=r"^helm\s+install",
        verdict="needs_approval",
        reason="prod helm install — ask a human",
        label="helm_ins",
    )
    v = rule_command_patterns(
        _ctx(tp, arguments={"command": "helm install myapp ./chart"}))
    assert v is not None
    verdict, reason = v
    assert verdict == "needs_approval"
    assert "helm install" in reason


def test_rule_non_matching_command_abstains(tp):
    tp.add_command_pattern(pattern=r"^terraform\s+apply", label="x")
    v = rule_command_patterns(
        _ctx(tp, arguments={"command": "terraform plan"}))
    assert v is None


def test_rule_case_insensitive(tp):
    tp.add_command_pattern(pattern=r"^terraform\s+apply", label="x")
    v = rule_command_patterns(
        _ctx(tp, arguments={"command": "TERRAFORM APPLY"}))
    assert v is not None
    assert v[0] == "deny"


def test_rule_scans_multiple_command_fields(tp):
    tp.add_command_pattern(pattern=r"kubectl\s+apply", label="k8s")
    # 'code' field (e.g. python_exec tool args) is scanned.
    v = rule_command_patterns(
        _ctx(tp, tool="python_exec",
             arguments={"code": "os.system('kubectl apply -f x.yaml')"}))
    assert v is not None
    assert v[0] == "deny"


def test_rule_non_string_command_is_coerced(tp):
    tp.add_command_pattern(pattern=r"dangerous", label="d")
    # Even a list-typed command gets str()-coerced and scanned.
    v = rule_command_patterns(
        _ctx(tp, arguments={"command": ["dangerous", "chain"]}))
    assert v is not None


def test_rule_skips_corrupt_regex(tp):
    # Sneak a malformed pattern past the API by mutating the list directly.
    tp.add_command_pattern(pattern=r"^valid", label="v",
                           verdict="deny", reason="ok")
    tp.command_patterns.append({
        "pattern": "(unclosed",
        "scope": "global", "verdict": "deny",
        "reason": "bad", "label": "bad_rx",
    })
    # Good rule still fires; bad one does not blow up the chain.
    v = rule_command_patterns(
        _ctx(tp, arguments={"command": "valid now"}))
    assert v is not None
    assert v[0] == "deny"


# ── scope matching ──────────────────────────────────────────────────


def test_rule_scope_agent_matches_exact_id(tp):
    tp.add_command_pattern(
        pattern=r"^kubectl\s+apply",
        scope="agent:a-alice",
        label="alice_only",
    )
    # Alice hits the pattern.
    v = rule_command_patterns(
        _ctx(tp, agent_id="a-alice",
             arguments={"command": "kubectl apply -f x"}))
    assert v is not None
    # Bob (different agent) is NOT affected by this pattern.
    v2 = rule_command_patterns(
        _ctx(tp, agent_id="a-bob",
             arguments={"command": "kubectl apply -f x"}))
    assert v2 is None


def test_rule_scope_global_matches_anyone(tp):
    tp.add_command_pattern(pattern=r"rm\s+-rf", label="rmrf",
                           scope="global")
    for aid in ("a-alice", "a-bob", "a-carol"):
        v = rule_command_patterns(
            _ctx(tp, agent_id=aid,
                 arguments={"command": "rm -rf /tmp/x"}))
        assert v is not None
        assert v[0] == "deny"


# ── chain integration via policy.check_tool ─────────────────────────


def test_check_tool_command_pattern_after_global_denylist(tp):
    tp.global_denylist.add("bash")
    tp.add_command_pattern(pattern=r"^ls", label="ls_block")
    # global_denylist rule fires first; command_patterns never gets
    # a chance.
    verdict, reason = tp.check_tool(
        "bash", {"command": "ls"}, agent_id="a-alice",
    )
    assert verdict == "deny"
    assert "global denylist" in reason.lower()


def test_check_tool_command_pattern_blocks_low_risk_tool(tp):
    """Even a LOW-risk tool (bash ls) is blocked when a pattern matches."""
    tp.add_command_pattern(
        pattern=r"^ls",
        label="temp_ls_block",
        reason="sandbox: ls temporarily banned",
    )
    verdict, reason = tp.check_tool(
        "bash", {"command": "ls /tmp"}, agent_id="a-alice",
    )
    assert verdict == "deny"
    assert "sandbox" in reason


def test_check_tool_without_pattern_still_allows_ls(tp):
    # Sanity: no pattern added → low-risk bash goes through.
    verdict, _ = tp.check_tool(
        "bash", {"command": "ls /tmp"}, agent_id="a-alice",
    )
    assert verdict == "allow"


# ── persistence ─────────────────────────────────────────────────────


def test_patterns_persist_across_restart():
    tmpdir = tempfile.mkdtemp(prefix="cp_persist_")
    path = os.path.join(tmpdir, "tool_approvals.json")

    tp1 = ToolPolicy()
    tp1.set_persist_path(path)
    tp1.add_command_pattern(
        pattern=r"^terraform\s+apply", label="tf_apply",
        reason="prod write",
    )
    # New instance, same path → loads same patterns.
    tp2 = ToolPolicy()
    tp2.set_persist_path(path)
    labels = [p["label"] for p in tp2.list_command_patterns()]
    assert "tf_apply" in labels


def test_corrupt_regex_in_persistence_skipped():
    tmpdir = tempfile.mkdtemp(prefix="cp_corrupt_")
    path = os.path.join(tmpdir, "tool_approvals.json")
    # Write a malformed file directly.
    import json as _json
    cp_path = os.path.join(tmpdir, "command_patterns.json")
    with open(cp_path, "w") as f:
        _json.dump({"patterns": [
            {"pattern": "(unclosed", "label": "bad"},
            {"pattern": r"^ok", "label": "good"},
        ]}, f)
    tp = ToolPolicy()
    tp.set_persist_path(path)
    labels = [p["label"] for p in tp.list_command_patterns()]
    assert labels == ["good"]
