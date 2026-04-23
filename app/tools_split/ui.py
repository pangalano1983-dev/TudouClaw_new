"""UI-block tools + handoff payload — structured messages between agents.

UI blocks
  - choice   : prompt + list of options rendered as buttons. User click
               sends a follow-up message whose text is the option label.
  - checklist: prompt + list of items (text, optional pre-ticked state).
               Display-only; users can tick items visually but there is
               no feedback loop to the agent in the initial version.

Handoff (Sprint-collab B)
  - emit_handoff: structured "baton pass" between agents. Carries
                   deliverable path, highlights, and follow-up tasks
                   the NEXT agent should pick up. Rendered as a
                   distinct card in chat; ingested by the next
                   execution-phase agent's system prompt so the baton
                   content is visible without it having to scroll the
                   whole discussion.

All three kinds flow through the agent event stream as typed events
(``ui_block`` / ``handoff``). agent_execution.py special-cases the
tool names and emits the envelope after the handler validates.
"""
from __future__ import annotations

from typing import Any


# Upper bound on buttons / items per block. More than this makes the UI
# unwieldy and usually indicates the agent should be asking a narrower
# question.
_MAX_CHOICE_OPTIONS = 8
_MAX_CHECKLIST_ITEMS = 20

# Truncation caps so a runaway prompt can't blow up the rendering.
_PROMPT_MAX_CHARS = 400
_LABEL_MAX_CHARS = 80
_ITEM_TEXT_MAX_CHARS = 160

_ALLOWED_KINDS = frozenset({"choice", "checklist"})


def _truncate(s: str, cap: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= cap else s[: cap - 1] + "…"


def _normalize_choice_options(options: Any) -> tuple[list[dict], str | None]:
    """Return (normalized_options, error_message)."""
    if not isinstance(options, list) or not options:
        return [], "Error: 'options' must be a non-empty list for kind='choice'."
    if len(options) > _MAX_CHOICE_OPTIONS:
        return [], (f"Error: at most {_MAX_CHOICE_OPTIONS} options allowed "
                    f"(got {len(options)}).")

    normalized: list[dict] = []
    seen_ids: set[str] = set()
    for i, opt in enumerate(options):
        # Accept either a string shortcut or a {id,label} dict.
        if isinstance(opt, str):
            label = _truncate(opt, _LABEL_MAX_CHARS)
            opt_id = f"opt_{i+1}"
        elif isinstance(opt, dict):
            label = _truncate(str(opt.get("label", "")), _LABEL_MAX_CHARS)
            opt_id = str(opt.get("id", f"opt_{i+1}")).strip() or f"opt_{i+1}"
        else:
            return [], f"Error: option[{i}] must be string or {{id,label}} dict."
        if not label:
            return [], f"Error: option[{i}] has empty label."
        if opt_id in seen_ids:
            return [], f"Error: duplicate option id: {opt_id!r}"
        seen_ids.add(opt_id)
        normalized.append({"id": opt_id, "label": label})
    return normalized, None


def _normalize_checklist_items(items: Any) -> tuple[list[dict], str | None]:
    if not isinstance(items, list) or not items:
        return [], "Error: 'items' must be a non-empty list for kind='checklist'."
    if len(items) > _MAX_CHECKLIST_ITEMS:
        return [], (f"Error: at most {_MAX_CHECKLIST_ITEMS} items allowed "
                    f"(got {len(items)}).")

    normalized: list[dict] = []
    seen_ids: set[str] = set()
    for i, item in enumerate(items):
        if isinstance(item, str):
            text = _truncate(item, _ITEM_TEXT_MAX_CHARS)
            item_id = f"item_{i+1}"
            done = False
        elif isinstance(item, dict):
            text = _truncate(str(item.get("text", "")), _ITEM_TEXT_MAX_CHARS)
            item_id = str(item.get("id", f"item_{i+1}")).strip() or f"item_{i+1}"
            done = bool(item.get("done", False))
        else:
            return [], f"Error: item[{i}] must be string or {{id,text,done}} dict."
        if not text:
            return [], f"Error: item[{i}] has empty text."
        if item_id in seen_ids:
            return [], f"Error: duplicate item id: {item_id!r}"
        seen_ids.add(item_id)
        normalized.append({"id": item_id, "text": text, "done": done})
    return normalized, None


def build_ui_block(kind: str, prompt: str, options: Any = None,
                   items: Any = None) -> tuple[dict | None, str | None]:
    """Validate and shape a ui_block payload.

    Returns (block_dict, error_string). Exactly one is non-None.

    Exported so agent_execution.py can call it directly when intercepting
    emit_ui_block — avoids parsing the tool's text return value.
    """
    k = (kind or "").strip().lower()
    if k not in _ALLOWED_KINDS:
        return None, (f"Error: kind must be one of {sorted(_ALLOWED_KINDS)}, "
                      f"got {kind!r}.")

    prompt_clean = _truncate(str(prompt or ""), _PROMPT_MAX_CHARS)
    if not prompt_clean:
        return None, "Error: 'prompt' is required."

    if k == "choice":
        normalized, err = _normalize_choice_options(options)
        if err:
            return None, err
        return {"kind": "choice", "prompt": prompt_clean,
                "options": normalized}, None

    # k == "checklist"
    normalized, err = _normalize_checklist_items(items)
    if err:
        return None, err
    return {"kind": "checklist", "prompt": prompt_clean,
            "items": normalized}, None


def _tool_emit_ui_block(kind: str = "", prompt: str = "",
                       options: Any = None, items: Any = None,
                       **_: Any) -> str:
    """Handler body — validation only.

    Real UI emission is done by agent_execution.py after seeing this tool
    name. Return a text confirmation so the LLM sees the outcome in its
    own chat history, not a dict (the dispatcher stringifies tool results).
    """
    block, err = build_ui_block(kind, prompt, options=options, items=items)
    if err:
        return err
    if block["kind"] == "choice":
        return (f"UI block emitted: choice with {len(block['options'])} option(s). "
                f"Wait for user's response in the next turn.")
    return (f"UI block emitted: checklist with {len(block['items'])} item(s). "
            f"Display-only; no user response expected.")


# ── Handoff payload (Sprint-collab B) ────────────────────────────────
# Structured "baton pass" — a completing agent emits one of these to
# tell the next agent exactly what got done and what to do next.
# Displayed as a distinct card in chat AND ingested into the next
# agent's system prompt by _build_execution_prompt.

_MAX_HIGHLIGHTS = 6
_MAX_FOLLOWUPS = 8
_HIGHLIGHT_MAX_CHARS = 200
_FOLLOWUP_TASK_MAX_CHARS = 200
_DELIVERABLE_PATH_MAX_CHARS = 300
_SUMMARY_MAX_CHARS = 500


def build_handoff_payload(
    summary: str,
    deliverable_path: str = "",
    highlights: Any = None,
    followups: Any = None,
) -> tuple[dict | None, str | None]:
    """Validate + shape a handoff payload. Returns (payload, error).

    Exported so agent_execution.py can call directly when intercepting
    ``emit_handoff`` — avoids parsing the tool's text return value.

    Canonical shape (what chat UI + next-agent prompt see):
        {
          "summary":          str,  # one-paragraph what-I-did
          "deliverable_path": str,  # relative path in shared workspace (may be empty)
          "highlights":       [str, ...],  # key findings / decisions / data points
          "followups":        [{"for": str, "task": str}, ...],  # suggested next steps
        }
    """
    summary_clean = _truncate(str(summary or ""), _SUMMARY_MAX_CHARS)
    if not summary_clean:
        return None, "Error: 'summary' is required."

    path_clean = _truncate(str(deliverable_path or ""),
                           _DELIVERABLE_PATH_MAX_CHARS)

    # Highlights — accept list of strings OR dicts with 'text'.
    hl_norm: list[str] = []
    if isinstance(highlights, list):
        for i, h in enumerate(highlights[:_MAX_HIGHLIGHTS]):
            if isinstance(h, str):
                t = h
            elif isinstance(h, dict):
                t = str(h.get("text", ""))
            else:
                continue
            t = _truncate(t, _HIGHLIGHT_MAX_CHARS)
            if t:
                hl_norm.append(t)

    # Follow-ups — require {for, task} pairs.
    fu_norm: list[dict] = []
    if isinstance(followups, list):
        for i, f in enumerate(followups[:_MAX_FOLLOWUPS]):
            if not isinstance(f, dict):
                continue
            target = str(f.get("for") or f.get("assignee") or "").strip()
            task = _truncate(str(f.get("task") or f.get("description") or ""),
                             _FOLLOWUP_TASK_MAX_CHARS)
            if target and task:
                fu_norm.append({"for": target, "task": task})

    return {
        "summary": summary_clean,
        "deliverable_path": path_clean,
        "highlights": hl_norm,
        "followups": fu_norm,
    }, None


def _tool_emit_handoff(summary: str = "",
                       deliverable_path: str = "",
                       highlights: Any = None,
                       followups: Any = None,
                       **_: Any) -> str:
    """Handler body — validation only.

    Real handoff event emission is done by agent_execution.py after
    seeing this tool name. The handler just shapes and validates the
    payload; returning a short text confirmation so the LLM sees it
    logged in its own history.
    """
    payload, err = build_handoff_payload(
        summary, deliverable_path=deliverable_path,
        highlights=highlights, followups=followups,
    )
    if err:
        return err
    parts = [f"Handoff emitted: {payload['summary'][:80]}"]
    if payload["deliverable_path"]:
        parts.append(f"→ {payload['deliverable_path']}")
    if payload["followups"]:
        whos = ", ".join(f["for"] for f in payload["followups"])
        parts.append(f"followups for {whos}")
    return " · ".join(parts)
