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
_RENDERABLE_EVENT_KINDS = frozenset({"tool_call", "tool_result", "ui_block"})

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
    for evt in raw_tail:
        # AgentEvent exposes .kind, .data, .timestamp. Duck-type for safety.
        kind = getattr(evt, "kind", None)
        if kind not in _RENDERABLE_EVENT_KINDS:
            continue
        data = getattr(evt, "data", None) or {}
        ts = getattr(evt, "timestamp", 0.0)
        out.append({
            "kind": kind,
            "data": _shrink_event_data(kind, data),
            "timestamp": float(ts) if ts else 0.0,
        })
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
    return dict(data)  # defensive copy
