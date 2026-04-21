"""UI-block tools — emit rich interactive blocks into the agent conversation.

Two block kinds supported:
  - choice   : prompt + list of options rendered as buttons. User click
               sends a follow-up message whose text is the option label.
  - checklist: prompt + list of items (text, optional pre-ticked state).
               Display-only; users can tick items visually but there is
               no feedback loop to the agent in the initial version.

Both blocks flow through the existing agent event stream as a new
``ui_block`` event kind — agent_execution.py special-cases
``emit_ui_block`` and emits the envelope after the handler validates
the payload.

Design note: the tool handler does validation only. It returns a short
text confirmation (so the LLM sees "block emitted OK" in its own
history). The actual UI rendering happens because agent_execution.py
pulls the validated block out of the arguments and emits a typed event
that the portal frontend listens for.
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
