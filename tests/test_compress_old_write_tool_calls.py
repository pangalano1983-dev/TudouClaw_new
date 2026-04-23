"""Opt 4 — old write_file / edit_file tool_call args get trimmed on resend.

Without this, every turn after a `write_file({path, content="<10k chars>"})`
call re-ships the full 10k back to the LLM. Only the 2 most recent write
calls keep their content verbatim; older ones get a 1-line summary with
head preview.
"""
from __future__ import annotations

import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


from app.agent import _compress_old_write_tool_calls  # noqa: E402


def _write_call(path: str, content: str, call_id: str = "c",
                fn_name: str = "write_file") -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": fn_name,
            "arguments": json.dumps({"path": path, "content": content},
                                    ensure_ascii=False),
        },
    }


def _edit_call(path: str, new_string: str, call_id: str = "c") -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": "edit_file",
            "arguments": json.dumps(
                {"path": path, "old_string": "x", "new_string": new_string},
                ensure_ascii=False),
        },
    }


def _assistant(tool_calls: list[dict]) -> dict:
    return {"role": "assistant", "content": "", "tool_calls": tool_calls}


# ── fewer-than-threshold: untouched ────────────────────────────────


def test_zero_write_calls_unchanged():
    msgs = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    assert _compress_old_write_tool_calls(msgs) == msgs


def test_one_write_call_kept_verbatim():
    msgs = [
        _assistant([_write_call("/a.py", "X" * 5000)]),
    ]
    out = _compress_old_write_tool_calls(msgs)
    assert out == msgs  # only one → within keep_last=2


def test_two_write_calls_both_kept():
    msgs = [
        _assistant([_write_call("/a.py", "X" * 5000, "c1")]),
        _assistant([_write_call("/b.py", "Y" * 5000, "c2")]),
    ]
    out = _compress_old_write_tool_calls(msgs)
    assert out == msgs


# ── threshold exceeded: OLD ones shrink, NEW ones stay ────────────


def test_three_write_calls_oldest_shrinks():
    big_a = "A" * 3000
    big_b = "B" * 3000
    big_c = "C" * 3000
    msgs = [
        _assistant([_write_call("/a.py", big_a, "c1")]),   # oldest → shrink
        _assistant([_write_call("/b.py", big_b, "c2")]),   # kept
        _assistant([_write_call("/c.py", big_c, "c3")]),   # kept
    ]
    out = _compress_old_write_tool_calls(msgs)
    # Oldest write call got shrunk.
    shrunk_args = json.loads(out[0]["tool_calls"][0]["function"]["arguments"])
    assert shrunk_args["path"] == "/a.py"   # path preserved
    assert "elided" in shrunk_args["content"]
    assert str(len(big_a)) in shrunk_args["content"]
    # Newer ones unchanged.
    kept_args_b = json.loads(out[1]["tool_calls"][0]["function"]["arguments"])
    kept_args_c = json.loads(out[2]["tool_calls"][0]["function"]["arguments"])
    assert kept_args_b["content"] == big_b
    assert kept_args_c["content"] == big_c


def test_edit_file_new_string_also_trimmed():
    big = "Z" * 3000
    msgs = [
        _assistant([_edit_call("/a.py", big, "c1")]),    # oldest → shrink
        _assistant([_write_call("/b.py", "small", "c2")]),
        _assistant([_write_call("/c.py", "small", "c3")]),
    ]
    out = _compress_old_write_tool_calls(msgs)
    args0 = json.loads(out[0]["tool_calls"][0]["function"]["arguments"])
    assert "elided" in args0["new_string"]
    assert args0["old_string"] == "x"    # other args preserved


def test_small_content_not_trimmed_even_when_old():
    msgs = [
        _assistant([_write_call("/a.py", "tiny", "c1")]),   # small → keep
        _assistant([_write_call("/b.py", "B" * 3000, "c2")]),
        _assistant([_write_call("/c.py", "C" * 3000, "c3")]),
    ]
    out = _compress_old_write_tool_calls(msgs)
    args0 = json.loads(out[0]["tool_calls"][0]["function"]["arguments"])
    assert args0["content"] == "tiny"     # under threshold → untouched


def test_non_write_assistant_messages_unchanged():
    msgs = [
        _assistant([{"id": "c0", "type": "function",
                     "function": {"name": "read_file",
                                  "arguments": '{"path":"/a"}'}}]),
        _assistant([_write_call("/a.py", "X" * 3000, "c1")]),
        _assistant([_write_call("/b.py", "Y" * 3000, "c2")]),
        _assistant([_write_call("/c.py", "Z" * 3000, "c3")]),
    ]
    out = _compress_old_write_tool_calls(msgs)
    # read_file untouched.
    assert out[0] == msgs[0]
    # The 3 write calls: oldest (msgs[1]) shrunk, msgs[2] & msgs[3] kept.
    args1 = json.loads(out[1]["tool_calls"][0]["function"]["arguments"])
    assert "elided" in args1["content"]
    args2 = json.loads(out[2]["tool_calls"][0]["function"]["arguments"])
    args3 = json.loads(out[3]["tool_calls"][0]["function"]["arguments"])
    assert args2["content"] == "Y" * 3000
    assert args3["content"] == "Z" * 3000


def test_returns_new_list_no_mutation():
    big = "X" * 3000
    msgs = [
        _assistant([_write_call("/a.py", big, "c1")]),
        _assistant([_write_call("/b.py", big, "c2")]),
        _assistant([_write_call("/c.py", big, "c3")]),
    ]
    snapshot = json.dumps(msgs, ensure_ascii=False)
    _ = _compress_old_write_tool_calls(msgs)
    assert json.dumps(msgs, ensure_ascii=False) == snapshot


def test_malformed_arguments_json_passed_through():
    msgs = [
        _assistant([{
            "id": "c1", "type": "function",
            "function": {"name": "write_file", "arguments": "not json"},
        }]),
        _assistant([_write_call("/b.py", "X" * 3000, "c2")]),
        _assistant([_write_call("/c.py", "X" * 3000, "c3")]),
    ]
    out = _compress_old_write_tool_calls(msgs)
    # First call (malformed) is left untouched rather than crashing.
    assert out[0] == msgs[0]
