"""Capture agent-execution events for display in project / meeting chat.

Context
-------
Agent chat (the 1:1 page) gets real-time SSE events — tool_call /
tool_result / ui_block etc. — because the backend streams them to the
frontend as they happen.

Project chat and meeting chat are DIFFERENT: they invoke the same
agent internally but receive only the FINAL assistant text. Without
this helper, any ui_block the agent emits during project / meeting
execution is invisible to those pages.

Design
------
We piggy-back on the agent's internal `self.events` ring buffer.
Before running the agent's chat call, record the current length.
After the call returns, slice from that index and extract the subset
of events that are meaningful to render in a chat bubble:

  - tool_call   : displayed as compact "▸ tool_name arg_preview"
  - tool_result : used to mark the matching tool_call as done
  - ui_block    : rendered as interactive card (choice/checklist)

Other event kinds (thinking / message / plan_update / etc.) are
dropped — they either show up elsewhere or are internal noise.

Payloads are serialized to plain dicts so they can be JSON-persisted
alongside the message in ProjectMessage.blocks / MeetingMessage.blocks.
"""
from __future__ import annotations

from typing import Any


# Event kinds worth surfacing in non-streaming chat contexts.
# Keep this list tight — adding more kinds means more storage bloat
# AND more frontend render paths to maintain.
_RENDERABLE_EVENT_KINDS = frozenset({
    "tool_call", "tool_result",
    "ui_block",
    # plan_update captures the agent's multi-step execution checklist.
    # For streaming agent chat the UI updates in real-time; for the
    # non-streaming project / meeting chat we snapshot the FINAL plan
    # state at turn end, giving users the same "what did the agent do
    # step-by-step" view they expect.
    "plan_update",
    # skill_match — emitted when the agent matches a skill for the
    # current turn. Surfaces skill invocations so users can see
    # which capability the agent leaned on, not just which tools.
    "skill_match",
})

# Cap on how many renderable events one chat turn can carry forward.
# A pathological agent loop can emit hundreds of tool_calls; beyond
# this cap we truncate to keep message payload bounded.
_MAX_EVENTS_PER_TURN = 40

# Truncation caps for tool_call argument previews. Frontend applies
# its own compact-render but we bound storage here too.
_TOOL_ARGS_PREVIEW_CHARS = 200
_TOOL_RESULT_PREVIEW_CHARS = 400


def snapshot_event_count(agent: Any) -> int:
    """Record the current position in the agent's event log.

    Call this RIGHT BEFORE invoking the agent's chat path. The returned
    integer is a cursor; pass it back to ``capture_events_since`` after
    the chat completes.

    Tolerates agents without an ``events`` attribute (returns 0) so
    callers don't need to special-case test doubles.
    """
    events = getattr(agent, "events", None)
    if events is None:
        return 0
    try:
        return len(events)
    except TypeError:
        return 0


def capture_events_since(agent: Any, start_idx: int) -> list[dict]:
    """Return renderable events that happened after ``start_idx``.

    Each returned dict has shape:
        {"kind": str, "data": dict, "timestamp": float}

    Data is pre-truncated to keep the persisted payload small. Arrays
    longer than _MAX_EVENTS_PER_TURN are truncated with the FIRST
    items kept (so the user sees where execution started) plus a
    synthetic "truncated" marker event at the end.
    """
    events = getattr(agent, "events", None)
    if not events:
        return []

    try:
        raw_tail = list(events[start_idx:])
    except (TypeError, IndexError):
        return []

    out: list[dict] = []
    # plan_update fires once per step mutation; each event carries the
    # FULL plan snapshot. For non-streaming replay we only need the
    # final state, so we remember the index of the last plan_update in
    # `out` and overwrite it as new ones arrive (vs. appending all).
    last_plan_idx = -1
    for evt in raw_tail:
        # AgentEvent exposes .kind, .data, .timestamp. Duck-type for safety.
        kind = getattr(evt, "kind", None)
        if kind not in _RENDERABLE_EVENT_KINDS:
            continue
        data = getattr(evt, "data", None) or {}
        ts = getattr(evt, "timestamp", 0.0)
        rendered = {
            "kind": kind,
            "data": _shrink_event_data(kind, data),
            "timestamp": float(ts) if ts else 0.0,
        }
        if kind == "plan_update" and last_plan_idx >= 0:
            # Replace earlier plan_update snapshot — same plan, newer state.
            out[last_plan_idx] = rendered
        else:
            if kind == "plan_update":
                last_plan_idx = len(out)
            out.append(rendered)
        if len(out) >= _MAX_EVENTS_PER_TURN:
            out.append({
                "kind": "ellipsis",
                "data": {"dropped": len(raw_tail) - _MAX_EVENTS_PER_TURN},
                "timestamp": out[-1]["timestamp"],
            })
            break
    return out


def _shrink_event_data(kind: str, data: dict) -> dict:
    """Apply per-kind truncation so we don't persist huge payloads."""
    if kind == "tool_call":
        name = str(data.get("name", ""))[:80]
        args = str(data.get("args") or data.get("arguments_preview") or "")
        if len(args) > _TOOL_ARGS_PREVIEW_CHARS:
            args = args[:_TOOL_ARGS_PREVIEW_CHARS - 3] + "..."
        return {"name": name, "args": args}
    if kind == "tool_result":
        name = str(data.get("name", ""))[:80]
        result = str(data.get("result", ""))
        if len(result) > _TOOL_RESULT_PREVIEW_CHARS:
            result = result[:_TOOL_RESULT_PREVIEW_CHARS - 3] + "..."
        return {"name": name, "result_preview": result}
    if kind == "ui_block":
        # ui_block is already bounded by build_ui_block's caps; pass through.
        return {"block": data.get("block", {})}
    if kind == "skill_match":
        # Agent's skill-matching hit. Keep the name + a short reason
        # string; internal scoring floats aren't meaningful in chat
        # display.
        return {
            "skill_name": str(data.get("skill_name")
                              or data.get("name") or "")[:80],
            "reason": str(data.get("reason")
                          or data.get("triggered_by") or "")[:200],
        }
    if kind == "plan_update":
        # A plan is {summary, steps:[{id,title,status,result_summary}]}.
        # Agent chat receives deltas and mutates the UI; we only receive
        # this event for the SNAPSHOT at turn-end so we keep the full
        # plan structure but truncate each step's verbose fields.
        plan = data.get("plan") or {}
        steps = plan.get("steps") or []
        compact_steps = []
        for s in steps[:40]:  # matches _MAX_EVENTS_PER_TURN for consistency
            compact_steps.append({
                "id": str(s.get("id", ""))[:40],
                "title": str(s.get("title", ""))[:200],
                "status": str(s.get("status", "pending"))[:20],
                "result_summary": str(s.get("result_summary", ""))[:200],
            })
        return {
            "plan": {
                "task_summary": str(plan.get("task_summary", ""))[:400],
                "steps": compact_steps,
            },
        }
    return dict(data)  # defensive copy
