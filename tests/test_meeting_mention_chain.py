"""Regression: agent-to-agent @ mentions inside a meeting.

Bug history: user observed in a meeting that 小土 posted "@小安 请
验证..." but 小安 never got triggered — no typing indicator, no
reply. Meeting auto-reply was only triggered on USER posts, never on
agent posts that @-mentioned another participant.

Fix: scan each agent reply for @<participant-name> and queue the
mentioned participant into the current round's reply sequence.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.meeting import (
    Meeting,
    MeetingRegistry,
    MeetingStatus,
    _find_at_mentioned_agents,
    meeting_agent_reply,
)


def _fake_agent(aid: str, name: str):
    return SimpleNamespace(id=aid, name=name, role="general", events=[])


def _make_meeting(participant_ids, status=MeetingStatus.ACTIVE) -> Meeting:
    m = Meeting(
        id="m-test",
        title="test",
        participants=list(participant_ids),
        status=status,
    )
    return m


# ── _find_at_mentioned_agents ────────────────────────────────────────

def test_mention_finds_participant_by_name():
    m = _make_meeting(["a1", "a2"])
    agents = {"a1": _fake_agent("a1", "小土"),
              "a2": _fake_agent("a2", "小安")}
    found = _find_at_mentioned_agents(
        "@小安 请验证之前的数据",
        meeting=m,
        agent_lookup_fn=agents.get,
    )
    assert found == ["a2"]


def test_mention_ignores_self_mention():
    """Agent @-ing themselves is a parsing artifact / noise, not a
    real inter-agent mention."""
    m = _make_meeting(["a1", "a2"])
    agents = {"a1": _fake_agent("a1", "小土"),
              "a2": _fake_agent("a2", "小安")}
    # Speaker is a1 (小土), who wrote '@小土 do X'
    found = _find_at_mentioned_agents(
        "@小土 notes: ...",
        meeting=m,
        agent_lookup_fn=agents.get,
        exclude_agent_id="a1",
    )
    assert found == []


def test_mention_with_trailing_punctuation():
    m = _make_meeting(["a1", "a2"])
    agents = {"a1": _fake_agent("a1", "Alice"),
              "a2": _fake_agent("a2", "Bob")}
    for content in ["@Bob, please verify.",
                    "@Bob: 请验证",
                    "@Bob。这件事",
                    "@Bob 请验证",
                    "I'll ask @Bob later"]:
        found = _find_at_mentioned_agents(
            content, m, agents.get)
        assert found == ["a2"], f"failed for {content!r}"


def test_mention_multiple_participants():
    m = _make_meeting(["a1", "a2", "a3"])
    agents = {"a1": _fake_agent("a1", "Alice"),
              "a2": _fake_agent("a2", "Bob"),
              "a3": _fake_agent("a3", "Carol")}
    found = _find_at_mentioned_agents(
        "@Bob 提报, @Carol 复核",
        m, agents.get,
    )
    assert found == ["a2", "a3"] or found == ["a3", "a2"]


def test_mention_dedup_on_duplicate_references():
    m = _make_meeting(["a1", "a2"])
    agents = {"a1": _fake_agent("a1", "Alice"),
              "a2": _fake_agent("a2", "Bob")}
    found = _find_at_mentioned_agents(
        "@Bob 先做, 然后 @Bob 再做",
        m, agents.get,
    )
    assert found == ["a2"]


def test_mention_prefers_longer_name_over_shorter_prefix():
    """If two participants are '小安' and '小安安', '@小安安' should
    resolve to 小安安 (not 小安 which is a prefix)."""
    m = _make_meeting(["a1", "a2"])
    agents = {"a1": _fake_agent("a1", "小安"),
              "a2": _fake_agent("a2", "小安安")}
    found = _find_at_mentioned_agents(
        "@小安安 please check",
        m, agents.get,
    )
    assert found == ["a2"]


def test_mention_on_non_participant_returns_empty():
    m = _make_meeting(["a1"])
    agents = {"a1": _fake_agent("a1", "Alice")}
    found = _find_at_mentioned_agents(
        "@Bob 请验证",
        m, agents.get,
    )
    assert found == []


def test_mention_empty_content():
    m = _make_meeting(["a1"])
    agents = {"a1": _fake_agent("a1", "Alice")}
    assert _find_at_mentioned_agents("", m, agents.get) == []
    assert _find_at_mentioned_agents(None, m, agents.get) == []


# ── Integration: meeting_agent_reply schedules the @'d agent ─────────

def test_reply_loop_queues_mentioned_agent():
    """End-to-end: agent A replies with @B, agent B should speak next
    in the same reply round."""
    m = _make_meeting(["a1", "a2"])
    agents = {"a1": _fake_agent("a1", "Alice"),
              "a2": _fake_agent("a2", "Bob")}

    # Track which agents actually got invoked via agent_chat_fn.
    invocations: list[str] = []

    def chat_fn(aid: str, _prompt) -> str:
        invocations.append(aid)
        # Alice's reply @s Bob; Bob's reply is plain.
        if aid == "a1":
            return "I'll defer to @Bob for verification."
        return "Verification done."

    reg = MagicMock(spec=MeetingRegistry)
    meeting_agent_reply(
        meeting=m,
        registry=reg,
        agent_chat_fn=chat_fn,
        agent_lookup_fn=agents.get,
        user_msg="kickoff",
        target_agent_ids=["a1"],  # user @s only a1
        auto_promote_primary=False,  # test isolates @-chain, not Phase-2
    )

    # Both agents replied — a1 first, a2 queued by mention detection.
    assert invocations == ["a1", "a2"]


def test_reply_loop_no_chaining_when_no_mention():
    m = _make_meeting(["a1", "a2"])
    agents = {"a1": _fake_agent("a1", "Alice"),
              "a2": _fake_agent("a2", "Bob")}

    invocations: list[str] = []

    def chat_fn(aid: str, _prompt) -> str:
        invocations.append(aid)
        return "No mentions here."

    reg = MagicMock(spec=MeetingRegistry)
    meeting_agent_reply(
        meeting=m,
        registry=reg,
        agent_chat_fn=chat_fn,
        agent_lookup_fn=agents.get,
        user_msg="kickoff",
        target_agent_ids=["a1"],
    )
    # Only a1 replies; a2 never pulled in.
    assert invocations == ["a1"]


def test_reply_loop_allows_bounded_ping_pong():
    """Alice @s Bob, Bob replies and @s Alice back, Alice @s Bob again,
    and so on — each agent is allowed up to max_replies_per_agent turns.

    Prior guard was over-aggressive (seen-once-forever), so a meeting
    died after one pass. Now bounded ping-pong is allowed — letting
    real back-and-forth unfold until either per-agent cap or total cap
    fires."""
    m = _make_meeting(["a1", "a2"])
    agents = {"a1": _fake_agent("a1", "Alice"),
              "a2": _fake_agent("a2", "Bob")}

    invocations: list[str] = []

    def chat_fn(aid: str, _prompt) -> str:
        invocations.append(aid)
        # Always @ the other — keeps the chain alive until a cap hits.
        return "@Bob ..." if aid == "a1" else "@Alice ..."

    reg = MagicMock(spec=MeetingRegistry)
    meeting_agent_reply(
        meeting=m,
        registry=reg,
        agent_chat_fn=chat_fn,
        agent_lookup_fn=agents.get,
        user_msg="kickoff",
        target_agent_ids=["a1"],
        max_replies_per_agent=3,
        auto_promote_primary=False,
    )
    # a1 speaks 3 times, a2 speaks 3 times — per-agent cap holds.
    # Order: a1 a2 a1 a2 a1 a2.
    assert invocations == ["a1", "a2", "a1", "a2", "a1", "a2"]


def test_reply_loop_respects_max_replies_per_agent():
    """Setting max_replies_per_agent=1 restores old single-pass."""
    m = _make_meeting(["a1", "a2"])
    agents = {"a1": _fake_agent("a1", "Alice"),
              "a2": _fake_agent("a2", "Bob")}

    invocations: list[str] = []

    def chat_fn(aid: str, _prompt) -> str:
        invocations.append(aid)
        return "@Bob ..." if aid == "a1" else "@Alice ..."

    reg = MagicMock(spec=MeetingRegistry)
    meeting_agent_reply(
        meeting=m,
        registry=reg,
        agent_chat_fn=chat_fn,
        agent_lookup_fn=agents.get,
        user_msg="kickoff",
        target_agent_ids=["a1"],
        max_replies_per_agent=1,
    )
    assert invocations == ["a1", "a2"]  # same as before the new default


def test_reply_loop_respects_max_total_replies():
    """Hard ceiling: even if per-agent cap would allow more, the total
    number of agent replies stops at max_total_replies."""
    m = _make_meeting(["a1", "a2"])
    agents = {"a1": _fake_agent("a1", "Alice"),
              "a2": _fake_agent("a2", "Bob")}

    invocations: list[str] = []

    def chat_fn(aid: str, _prompt) -> str:
        invocations.append(aid)
        return "@Bob ..." if aid == "a1" else "@Alice ..."

    reg = MagicMock(spec=MeetingRegistry)
    meeting_agent_reply(
        meeting=m,
        registry=reg,
        agent_chat_fn=chat_fn,
        agent_lookup_fn=agents.get,
        user_msg="kickoff",
        target_agent_ids=["a1"],
        max_replies_per_agent=10,   # high enough not to matter
        max_total_replies=4,         # hard cap hits first
        auto_promote_primary=False,
    )
    assert len(invocations) == 4


def test_reply_loop_respects_max_participants_cap():
    """Chain of @ mentions should not bust the max_participants cap."""
    m = _make_meeting(["a1", "a2", "a3"])
    agents = {"a1": _fake_agent("a1", "Alice"),
              "a2": _fake_agent("a2", "Bob"),
              "a3": _fake_agent("a3", "Carol")}

    invocations: list[str] = []

    def chat_fn(aid: str, _prompt) -> str:
        invocations.append(aid)
        if aid == "a1":
            return "@Bob 提报"
        if aid == "a2":
            return "@Carol 复核"
        return "OK"

    reg = MagicMock(spec=MeetingRegistry)
    meeting_agent_reply(
        meeting=m,
        registry=reg,
        agent_chat_fn=chat_fn,
        agent_lookup_fn=agents.get,
        user_msg="kickoff",
        target_agent_ids=["a1"],
        max_participants=2,  # cap below the full chain
    )
    # Cap enforced — only 2 invocations even though the chain would
    # normally produce 3.
    assert len(invocations) == 2
