"""P0-B — Auto-spill large tool results.

Tool outputs over threshold get written to
$workspace/tool_outputs/<ts>_<tool>.md and replaced in-message with a
ref + preview. Stops large web_fetch / file reads / bash output from
costing 5-10k tokens on every subsequent LLM call.
"""
from __future__ import annotations

import os
import sys
import time

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


class _StubProfile:
    def __init__(self, spill_chars: int = 0):
        self.spill_tool_result_chars = spill_chars


class _StubAgent:
    """Minimum Agent surface for the spill helper."""

    def __init__(self, ws: str, spill_chars: int = 0):
        self.id = "a-tester"
        self.name = "Tester"
        self._ws = ws
        self.profile = _StubProfile(spill_chars=spill_chars)
        self.logs: list = []

    def _get_agent_workspace(self):
        return self._ws

    def _log(self, kind, payload):
        self.logs.append((kind, payload))


def _bind():
    from app.agent import Agent
    _StubAgent._maybe_spill_tool_result = Agent._maybe_spill_tool_result
    _StubAgent._SPILL_TOOL_RESULT_THRESHOLD = Agent._SPILL_TOOL_RESULT_THRESHOLD
    _StubAgent._SPILL_PREVIEW_CHARS = Agent._SPILL_PREVIEW_CHARS
    _StubAgent._SPILL_SKIP_TOOLS = Agent._SPILL_SKIP_TOOLS


# ── below threshold: untouched ────────────────────────────────────


def test_small_result_is_unchanged(tmp_path):
    _bind()
    a = _StubAgent(str(tmp_path))
    out = a._maybe_spill_tool_result("web_search", "small result", "c1")
    assert out == "small result"
    # No file written.
    assert not os.path.isdir(os.path.join(str(tmp_path), "tool_outputs"))


def test_at_threshold_not_spilled(tmp_path):
    _bind()
    a = _StubAgent(str(tmp_path))
    boundary = _StubAgent._SPILL_TOOL_RESULT_THRESHOLD - 1
    text = "X" * boundary
    out = a._maybe_spill_tool_result("web_fetch", text, "c2")
    assert out == text


# ── above threshold: spills ───────────────────────────────────────


def test_large_result_spills_to_disk(tmp_path):
    _bind()
    a = _StubAgent(str(tmp_path))
    big = "X" * 5000
    out = a._maybe_spill_tool_result("web_fetch", big, "call-abc")
    # Return value is the compact replacement, not the raw text.
    assert out != big
    assert out.startswith("[Artifact:")
    assert "web_fetch" in out
    assert "call_id=call-abc"[:16] in out or "call-abc"[:6] in out
    # File actually written under tool_outputs/.
    out_dir = os.path.join(str(tmp_path), "tool_outputs")
    assert os.path.isdir(out_dir)
    files = os.listdir(out_dir)
    assert len(files) == 1
    # Body contains the full original text.
    body = open(os.path.join(out_dir, files[0]), encoding="utf-8").read()
    assert big in body
    # Metadata header present.
    assert "# Spilled tool result" in body
    assert "web_fetch" in body


def test_replacement_contains_preview_and_size(tmp_path):
    _bind()
    a = _StubAgent(str(tmp_path))
    big = ("Search results for cloud trends:\n"
           "1. AWS revenue grew 17% YoY in Q3 2026\n"
           "2. Azure overtook GCP in enterprise\n" + "X" * 6000)
    out = a._maybe_spill_tool_result("web_search", big, "c3")
    # Size appears in KB.
    assert "KB" in out
    # Preview contains content from the start of the string.
    assert "AWS revenue grew" in out
    # Read_file hint included.
    assert "read_file" in out


def test_preview_is_truncated_to_cap(tmp_path):
    _bind()
    a = _StubAgent(str(tmp_path))
    big = "Y" * 6000
    out = a._maybe_spill_tool_result("bash", big, "c4")
    # The preview section is capped (300 chars).
    # The out message is much smaller than the original.
    assert len(out) < 900
    # Original is preserved on disk.
    files = os.listdir(os.path.join(str(tmp_path), "tool_outputs"))
    body = open(os.path.join(str(tmp_path), "tool_outputs", files[0]),
                encoding="utf-8").read()
    assert "Y" * 6000 in body


# ── skip list: certain tools never spill ─────────────────────────


@pytest.mark.parametrize("skip_tool", [
    "plan_update", "complete_step", "memory_recall",
    "check_inbox", "ack_message", "reply_message",
    "save_experience",
])
def test_skipped_tools_dont_spill(tmp_path, skip_tool):
    _bind()
    a = _StubAgent(str(tmp_path))
    big = "Z" * 6000
    out = a._maybe_spill_tool_result(skip_tool, big, "c5")
    assert out == big
    # No file.
    assert not os.path.exists(
        os.path.join(str(tmp_path), "tool_outputs"))


# ── idempotency: already-spilled content not re-wrapped ──────────


def test_already_spilled_is_not_rewrapped(tmp_path):
    _bind()
    a = _StubAgent(str(tmp_path))
    pre = ("[Artifact: path=foo.md size=5KB]\nPreview: aaa\n" + "X" * 5000)
    out = a._maybe_spill_tool_result("web_fetch", pre, "c6")
    # Returns unchanged.
    assert out == pre


# ── profile override: custom threshold ──────────────────────────


def test_profile_override_lowers_threshold(tmp_path):
    _bind()
    a = _StubAgent(str(tmp_path), spill_chars=100)
    text = "a" * 200    # below default 1500 but above override 100
    out = a._maybe_spill_tool_result("web_fetch", text, "c7")
    assert out != text
    assert "[Artifact:" in out


def test_profile_override_raises_threshold(tmp_path):
    _bind()
    a = _StubAgent(str(tmp_path), spill_chars=10000)
    text = "a" * 3000    # above default 1500 but below override 10000
    out = a._maybe_spill_tool_result("web_fetch", text, "c8")
    assert out == text


# ── empty workspace: fall through gracefully ─────────────────────


def test_no_workspace_returns_unchanged(tmp_path):
    _bind()
    a = _StubAgent("")    # no workspace
    big = "X" * 5000
    out = a._maybe_spill_tool_result("web_fetch", big, "c9")
    assert out == big


# ── non-string input passthrough ────────────────────────────────


def test_non_string_passthrough(tmp_path):
    _bind()
    a = _StubAgent(str(tmp_path))
    # Shouldn't crash on weird inputs (defensive).
    out = a._maybe_spill_tool_result("web_fetch", 12345, "c10")
    assert out == 12345


# ── concurrent calls produce distinct files ─────────────────────


def test_multiple_spills_produce_distinct_files(tmp_path):
    _bind()
    a = _StubAgent(str(tmp_path))
    for i in range(3):
        a._maybe_spill_tool_result(
            "web_fetch", "X" * 5000, f"call-{i}",
        )
        time.sleep(0.01)   # avoid same-second filename collision
    files = os.listdir(os.path.join(str(tmp_path), "tool_outputs"))
    assert len(files) == 3


# ── audit log emission ──────────────────────────────────────────


def test_spill_emits_audit_log(tmp_path):
    _bind()
    a = _StubAgent(str(tmp_path))
    a._maybe_spill_tool_result("web_fetch", "X" * 5000, "c11")
    audit_events = [k for k, _ in a.logs if k == "tool_result_spilled"]
    assert len(audit_events) == 1
