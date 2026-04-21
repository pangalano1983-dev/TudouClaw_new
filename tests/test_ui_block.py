"""Tests for the emit_ui_block tool + build_ui_block validator."""
from __future__ import annotations

import pytest

from app.tools_split.ui import (
    _MAX_CHECKLIST_ITEMS,
    _MAX_CHOICE_OPTIONS,
    _tool_emit_ui_block,
    build_ui_block,
)


# ── choice blocks ────────────────────────────────────────────────────

def test_choice_block_happy_path():
    block, err = build_ui_block(
        kind="choice",
        prompt="Continue?",
        options=[
            {"id": "yes", "label": "Yes"},
            {"id": "no", "label": "No"},
        ],
    )
    assert err is None
    assert block["kind"] == "choice"
    assert block["prompt"] == "Continue?"
    assert len(block["options"]) == 2
    assert block["options"][0] == {"id": "yes", "label": "Yes"}


def test_choice_block_accepts_string_options():
    block, err = build_ui_block(
        kind="choice",
        prompt="Pick one",
        options=["Alpha", "Beta", "Gamma"],
    )
    assert err is None
    assert [o["label"] for o in block["options"]] == ["Alpha", "Beta", "Gamma"]
    # Auto-assigned IDs are unique.
    ids = [o["id"] for o in block["options"]]
    assert len(set(ids)) == 3


def test_choice_block_rejects_duplicate_ids():
    _, err = build_ui_block(
        kind="choice",
        prompt="Pick",
        options=[{"id": "x", "label": "A"}, {"id": "x", "label": "B"}],
    )
    assert err is not None
    assert "duplicate" in err.lower()


def test_choice_block_enforces_option_cap():
    too_many = [{"id": f"o{i}", "label": f"L{i}"} for i in range(_MAX_CHOICE_OPTIONS + 1)]
    _, err = build_ui_block(kind="choice", prompt="P", options=too_many)
    assert err is not None
    assert str(_MAX_CHOICE_OPTIONS) in err


def test_choice_block_rejects_empty_options():
    _, err = build_ui_block(kind="choice", prompt="P", options=[])
    assert err is not None
    assert "non-empty" in err.lower()


def test_choice_block_rejects_empty_label():
    _, err = build_ui_block(kind="choice", prompt="P",
                            options=[{"id": "x", "label": "  "}])
    assert err is not None
    assert "empty label" in err.lower()


# ── checklist blocks ─────────────────────────────────────────────────

def test_checklist_block_happy_path():
    block, err = build_ui_block(
        kind="checklist",
        prompt="Todos",
        items=[
            {"id": "t1", "text": "Write tests", "done": False},
            {"id": "t2", "text": "Deploy", "done": True},
        ],
    )
    assert err is None
    assert block["kind"] == "checklist"
    assert len(block["items"]) == 2
    assert block["items"][1]["done"] is True


def test_checklist_block_accepts_string_items():
    block, err = build_ui_block(kind="checklist", prompt="P",
                                items=["Foo", "Bar"])
    assert err is None
    assert [i["text"] for i in block["items"]] == ["Foo", "Bar"]
    assert all(not i["done"] for i in block["items"])


def test_checklist_block_enforces_item_cap():
    too_many = [f"item {i}" for i in range(_MAX_CHECKLIST_ITEMS + 1)]
    _, err = build_ui_block(kind="checklist", prompt="P", items=too_many)
    assert err is not None
    assert str(_MAX_CHECKLIST_ITEMS) in err


# ── validation + security ────────────────────────────────────────────

def test_unknown_kind_rejected():
    _, err = build_ui_block(kind="carousel", prompt="P", options=[])
    assert err is not None
    assert "kind" in err.lower()


def test_empty_prompt_rejected():
    _, err = build_ui_block(kind="choice", prompt="",
                            options=[{"id": "x", "label": "X"}])
    assert err is not None
    assert "prompt" in err.lower()


def test_long_prompt_truncated():
    block, err = build_ui_block(
        kind="choice",
        prompt="A" * 500,
        options=[{"id": "x", "label": "X"}],
    )
    assert err is None
    # Prompt truncated + ellipsis added.
    assert len(block["prompt"]) < 500
    assert block["prompt"].endswith("…")


def test_long_label_truncated():
    block, err = build_ui_block(
        kind="choice",
        prompt="P",
        options=[{"id": "x", "label": "B" * 200}],
    )
    assert err is None
    assert len(block["options"][0]["label"]) < 200
    assert block["options"][0]["label"].endswith("…")


# ── tool handler return value ────────────────────────────────────────

def test_tool_handler_returns_confirmation_for_choice():
    result = _tool_emit_ui_block(
        kind="choice", prompt="Pick",
        options=[{"id": "a", "label": "A"}],
    )
    # Not an error, mentions 'choice' and 'option'.
    assert "Error" not in result
    assert "choice" in result.lower()


def test_tool_handler_returns_confirmation_for_checklist():
    result = _tool_emit_ui_block(
        kind="checklist", prompt="Tasks",
        items=["one", "two"],
    )
    assert "Error" not in result
    assert "checklist" in result.lower()


def test_tool_handler_returns_error_string_on_bad_input():
    result = _tool_emit_ui_block(kind="choice", prompt="P")  # No options.
    assert result.startswith("Error:")


# ── dispatcher integration ───────────────────────────────────────────

def test_tool_registered_in_dispatcher():
    from app import tools
    assert "emit_ui_block" in tools._TOOL_FUNCS
    assert callable(tools._TOOL_FUNCS["emit_ui_block"])


def test_tool_has_schema_with_five_elements():
    from app import tools
    schema = next(
        (d for d in tools.TOOL_DEFINITIONS
         if d["function"]["name"] == "emit_ui_block"),
        None,
    )
    assert schema is not None
    desc = schema["function"]["description"]
    for marker in ("Use when", "Not for", "Output", "GOTCHA"):
        assert marker in desc, f"emit_ui_block description missing {marker}"
