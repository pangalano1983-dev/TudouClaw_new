"""Tool-output spill: no re-spill loop + age/cap cleanup.

Bugs addressed:
  * read_file against an already-spilled tool_outputs/*.md produced
    yet another spill (same content, slightly different header) — a
    runaway cascade filled the directory in minutes.
  * No cleanup was ever scheduled: the directory only grew.

Fixes:
  * _maybe_spill_tool_result returns early when the result body starts
    with the "# Spilled tool result" marker we write ourselves.
  * cleanup_stale_tool_outputs() prunes by age AND by per-agent cap.
"""
from __future__ import annotations

import os
import sys
import time
from types import SimpleNamespace
from pathlib import Path

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# We don't want the full Agent dataclass in these tests, just the two
# methods we edited. Bind them to a shim via a minimal harness.
class _AgentHarness:
    """A lightweight stand-in that imports the real methods via descriptors."""

    def __init__(self, workspace: Path, aid="a1", name="test"):
        self._ws = workspace
        self.id = aid
        self.name = name
        # Minimal profile with the override attribute the real code reads.
        self.profile = SimpleNamespace(spill_tool_result_chars=0)

    def _get_agent_workspace(self):
        return self._ws

    def _log(self, *a, **kw):
        # no-op stub — the real Agent logs to an event stream
        pass

    # Agent.events — some spill paths walk this
    events = []


def _bind_methods(harness):
    from app.agent import Agent
    harness._maybe_spill_tool_result = Agent._maybe_spill_tool_result.__get__(harness)
    harness.cleanup_stale_tool_outputs = Agent.cleanup_stale_tool_outputs.__get__(harness)
    # Class constants
    harness._SPILL_TOOL_RESULT_THRESHOLD = Agent._SPILL_TOOL_RESULT_THRESHOLD
    harness._SPILL_PREVIEW_CHARS = Agent._SPILL_PREVIEW_CHARS
    harness._SPILL_SKIP_TOOLS = Agent._SPILL_SKIP_TOOLS
    harness._SPILL_MAX_AGE_SECONDS = Agent._SPILL_MAX_AGE_SECONDS
    harness._SPILL_MAX_FILES = Agent._SPILL_MAX_FILES


@pytest.fixture
def agent(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    h = _AgentHarness(ws)
    _bind_methods(h)
    return h


# ── re-spill loop fix ──────────────────────────────────────────────


def test_spill_skips_already_spilled_content(agent):
    """If the tool_result body is itself a spill file's content
    (starts with '# Spilled tool result'), we must NOT spill again."""
    spill_body = (
        "# Spilled tool result — read_file\n"
        "# timestamp: 2026-04-22 17:47:19\n"
        "# call_id:   abc123\n"
        "# size:      8234 chars\n"
        "# agent:     a1 (test)\n"
        "# ─────────────────────────────────────\n\n"
        + ("payload " * 1000)
    )
    out = agent._maybe_spill_tool_result("read_file", spill_body, "call-99")
    # Unchanged — no new file written, no ref substituted
    assert out == spill_body
    out_dir = Path(agent._ws) / "tool_outputs"
    assert not out_dir.exists() or not any(out_dir.iterdir())


def test_spill_still_happens_for_genuine_large_result(agent):
    """Sanity check: non-spill large results still get spilled."""
    big = "x" * 5000
    out = agent._maybe_spill_tool_result("some_tool", big, "call-1")
    # Replaced with compact ref
    assert out != big
    assert "spilled" in out.lower()
    out_dir = Path(agent._ws) / "tool_outputs"
    assert out_dir.exists()
    assert len(list(out_dir.iterdir())) == 1


def test_spill_below_threshold_unchanged(agent):
    small = "y" * 500
    out = agent._maybe_spill_tool_result("some_tool", small, "c")
    assert out == small


def test_spill_skiplist_respected(agent):
    big = "z" * 5000
    out = agent._maybe_spill_tool_result("memory_recall", big, "c")
    assert out == big


def test_knowledge_lookup_is_never_spilled(agent):
    """Pack v2 — 12KB JSON from top_k=8 RAG chunks must reach the LLM
    inline; spilling would force an extra read_file round-trip."""
    big_rag_json = (
        '{"status":"success","entries":['
        + ','.join(['{"id":"c%d","content":"%s"}' % (i, "x" * 1200)
                    for i in range(8)])
        + '],"usage_guidance":"..."}'
    )
    assert len(big_rag_json) > agent._SPILL_TOOL_RESULT_THRESHOLD
    out = agent._maybe_spill_tool_result("knowledge_lookup", big_rag_json, "c")
    assert out == big_rag_json
    out_dir = Path(agent._ws) / "tool_outputs"
    assert not out_dir.exists() or not any(out_dir.iterdir())


# ── cleanup: age + cap ────────────────────────────────────────────


def test_cleanup_removes_files_older_than_age_limit(agent):
    out_dir = Path(agent._ws) / "tool_outputs"
    out_dir.mkdir()
    # Two old, one fresh
    old_a = out_dir / "old_a.md"
    old_b = out_dir / "old_b.md"
    fresh = out_dir / "fresh.md"
    for p in (old_a, old_b, fresh):
        p.write_text("x")
    ancient = time.time() - 30 * 24 * 3600
    os.utime(old_a, (ancient, ancient))
    os.utime(old_b, (ancient, ancient))

    stats = agent.cleanup_stale_tool_outputs()
    assert stats["deleted_stale"] == 2
    assert stats["remaining"] == 1
    assert fresh.exists()
    assert not old_a.exists()
    assert not old_b.exists()


def test_cleanup_enforces_file_cap_by_oldest_first(agent):
    out_dir = Path(agent._ws) / "tool_outputs"
    out_dir.mkdir()
    # 5 files, all fresh
    paths = []
    now = time.time()
    for i in range(5):
        p = out_dir / f"f{i}.md"
        p.write_text("x")
        # Make each file slightly older than the next — f0 oldest
        t = now - (5 - i) * 10
        os.utime(p, (t, t))
        paths.append(p)

    # Cap at 3 → should delete 2 oldest (f0, f1)
    stats = agent.cleanup_stale_tool_outputs(
        max_age_seconds=10 ** 9, max_files=3)
    assert stats["deleted_stale"] == 0
    assert stats["deleted_cap"] == 2
    assert stats["remaining"] == 3
    assert not paths[0].exists()
    assert not paths[1].exists()
    assert paths[2].exists()
    assert paths[3].exists()
    assert paths[4].exists()


def test_cleanup_nop_when_dir_missing(agent):
    """Never-existed tool_outputs/ must not crash cleanup."""
    stats = agent.cleanup_stale_tool_outputs()
    assert stats == {"deleted_stale": 0, "deleted_cap": 0, "remaining": 0}


def test_cleanup_idempotent(agent):
    out_dir = Path(agent._ws) / "tool_outputs"
    out_dir.mkdir()
    (out_dir / "a.md").write_text("x")
    a = agent.cleanup_stale_tool_outputs()
    b = agent.cleanup_stale_tool_outputs()
    assert a["remaining"] == 1
    assert b["remaining"] == 1
