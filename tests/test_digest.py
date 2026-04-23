"""Block 3 Day 4-5 — digest builder tests."""
from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


from app import checkpoint as ckpt  # noqa: E402
from app import digest as dg       # noqa: E402
from app.checkpoint import AgentCheckpoint  # noqa: E402


@pytest.fixture
def store(tmp_path, monkeypatch):
    ckpt.reset_store_for_test()
    db = tmp_path / "ckpt.db"
    monkeypatch.setenv("TUDOU_CLAW_DATA_DIR", str(tmp_path))
    s = ckpt.get_store(db_path=str(db))
    yield s
    ckpt.reset_store_for_test()


def _make(**overrides) -> AgentCheckpoint:
    defaults = dict(
        id="ckpt_xyz",
        agent_id="a-alice",
        scope=ckpt.SCOPE_AGENT,
        scope_id="",
        created_at=1700_000_000.0,
        reason=ckpt.REASON_USER_ABORT,
        plan_json={},
        artifact_refs=[],
        chat_tail=[],
        digest="",
        metadata={},
        status=ckpt.STATUS_OPEN,
        restored_at=0.0,
    )
    defaults.update(overrides)
    return AgentCheckpoint(**defaults)


# ── core structure ─────────────────────────────────────────────────


def test_digest_none_checkpoint_returns_empty():
    r = dg.build_digest(None)
    assert r.text == ""
    assert r.token_estimate == 0


def test_header_always_present():
    r = dg.build_digest(_make())
    assert "检查点 ID" in r.text
    assert "ckpt_xyz" in r.text
    assert "header" in r.sections_included
    assert "next_action" in r.sections_included


def test_completed_and_unfinished_sections():
    plan = {
        "task_summary": "build report",
        "steps": [
            {"id": "s1", "title": "read code", "status": "completed",
             "order": 0, "result_summary": "read 12 files"},
            {"id": "s2", "title": "write draft", "status": "in_progress",
             "order": 1, "acceptance": "draft.md exists ≥ 500 words"},
            {"id": "s3", "title": "send email", "status": "pending",
             "order": 2},
        ],
    }
    r = dg.build_digest(_make(plan_json=plan))
    assert "✅ 已完成" in r.text
    assert "read 12 files" in r.text
    assert "⏳ 待完成" in r.text
    assert "write draft" in r.text
    assert "send email" in r.text
    assert "draft.md exists" in r.text
    assert "completed" in r.sections_included
    assert "unfinished" in r.sections_included


def test_failed_step_keeps_last_error_in_digest():
    plan = {
        "steps": [
            {"id": "s1", "title": "run tests", "status": "failed",
             "order": 0,
             "result_summary": "AssertionError: expected 200, got 500"},
        ],
    }
    r = dg.build_digest(_make(plan_json=plan))
    assert "上次失败" in r.text
    assert "AssertionError" in r.text


def test_empty_plan_omits_plan_sections():
    r = dg.build_digest(_make(plan_json={"steps": []}))
    assert "completed" not in r.sections_included
    assert "unfinished" not in r.sections_included


# ── artifacts ──────────────────────────────────────────────────────


def test_artifact_refs_render_with_sizes():
    refs = [
        {"id": "a1", "kind": "file",
         "path": "/ws/report.pdf", "size_bytes": 2048},
        {"id": "a2", "kind": "value", "path": "rev_hash"},
    ]
    r = dg.build_digest(_make(artifact_refs=refs))
    assert "已有产物" in r.text
    assert "report.pdf" in r.text
    assert "2 KB" in r.text
    assert "rev_hash" in r.text


def test_more_than_15_artifacts_truncated_with_note():
    refs = [{"id": f"a{i}", "kind": "file",
             "path": f"/tmp/f{i}.txt"} for i in range(20)]
    r = dg.build_digest(_make(artifact_refs=refs))
    assert "还有 5 个" in r.text


# ── chat tail ──────────────────────────────────────────────────────


def test_chat_tail_limited_and_trimmed():
    tail = [
        {"role": "user", "content": "a" * 500},
        {"role": "assistant", "content": "ok"},
    ]
    r = dg.build_digest(_make(chat_tail=tail))
    assert "最近对话" in r.text
    # 500-char message should be trimmed with ellipsis.
    assert "…" in r.text


def test_long_chat_tail_only_last_n_shown():
    tail = [{"role": "user", "content": f"m{i}"} for i in range(20)]
    r = dg.build_digest(_make(chat_tail=tail))
    # Default max_msgs=8 → last 8 entries: m12..m19.
    assert "m19" in r.text
    assert "m12" in r.text
    assert "m11" not in r.text
    assert "m2" not in r.text


def test_empty_chat_tail_omits_section():
    r = dg.build_digest(_make(chat_tail=[]))
    assert "chat_tail" not in r.sections_included


# ── reason hint ────────────────────────────────────────────────────


def test_reason_hint_from_metadata():
    meta = {"interrupt_reason": "verifier failed: 文件不足 3 张 slide"}
    r = dg.build_digest(_make(metadata=meta))
    assert "上次中断线索" in r.text
    assert "verifier failed" in r.text
    assert "reason_hint" in r.sections_included


def test_no_reason_hint_when_metadata_clean():
    r = dg.build_digest(_make(metadata={"unrelated": "value"}))
    assert "reason_hint" not in r.sections_included


# ── LLM compression path ──────────────────────────────────────────


def test_over_budget_calls_llm_and_replaces_completed():
    plan = {
        "steps": [
            {"id": f"s{i}", "title": f"step {i}",
             "status": "completed", "order": i,
             "result_summary": "X" * 300}
            for i in range(20)
        ],
    }
    calls = {"n": 0}

    def _llm(prompt: str) -> str:
        calls["n"] += 1
        assert "已完成" in prompt or "步骤" in prompt
        return "- 读完所有文件\n- 生成 pptx\n- 写邮件"

    r = dg.build_digest(_make(plan_json=plan),
                        token_budget=200, llm_call=_llm)
    assert calls["n"] == 1
    assert r.llm_compressed is True
    assert "✅ 已完成 (摘要)" in r.text
    assert "读完所有文件" in r.text
    # Unfinished section (none here) untouched; raw details gone.
    assert "step 0" not in r.text


def test_llm_rejection_when_no_shrink():
    plan = {
        "steps": [
            {"id": f"s{i}", "title": f"step {i}",
             "status": "completed", "order": i,
             "result_summary": "X" * 300}
            for i in range(20)
        ],
    }

    def _llm(prompt: str) -> str:
        # Returns something larger than the original → should be discarded.
        return "Y" * 9999

    r = dg.build_digest(_make(plan_json=plan),
                        token_budget=200, llm_call=_llm)
    assert r.llm_compressed is False
    # Original step details still present.
    assert "step 0" in r.text


def test_llm_exception_falls_back_silently():
    plan = {
        "steps": [{"id": "s1", "title": "t", "status": "completed",
                   "order": 0, "result_summary": "X" * 5000}],
    }

    def _llm(prompt: str) -> str:
        raise RuntimeError("provider down")

    r = dg.build_digest(_make(plan_json=plan),
                        token_budget=100, llm_call=_llm)
    # Did not raise.
    assert r.llm_compressed is False
    assert r.text  # still produced SOMETHING


def test_under_budget_skips_llm():
    plan = {
        "steps": [
            {"id": "s1", "title": "small",
             "status": "completed", "order": 0},
        ],
    }
    calls = {"n": 0}

    def _llm(prompt: str) -> str:
        calls["n"] += 1
        return "should not be called"

    r = dg.build_digest(_make(plan_json=plan),
                        token_budget=5000, llm_call=_llm)
    assert calls["n"] == 0
    assert r.llm_compressed is False


# ── truncation backstop ───────────────────────────────────────────


def test_huge_digest_hard_truncated():
    # Force a monster digest with no llm_call → triggers truncation.
    refs = [{"id": f"a{i}", "kind": "file",
             "path": f"/x/{i}.txt"} for i in range(200)]
    tail = [{"role": "user", "content": "Q" * 400} for _ in range(30)]
    plan = {"steps": [
        {"id": f"s{i}", "title": "step", "status": "completed",
         "order": i, "result_summary": "R" * 500}
        for i in range(50)
    ]}
    r = dg.build_digest(_make(plan_json=plan, artifact_refs=refs,
                              chat_tail=tail),
                        token_budget=100)
    assert r.truncated is True
    assert "(truncated for budget)" in r.text


# ── update_checkpoint_digest ──────────────────────────────────────


def test_update_checkpoint_digest_writes_back(store):
    cid = store.save(agent_id="a", plan_json={
        "steps": [{"id": "s1", "title": "done", "status": "completed",
                   "order": 0}],
    })
    r = dg.update_checkpoint_digest(cid)
    assert r is not None
    reloaded = store.load(cid)
    assert reloaded.digest == r.text
    assert "已完成" in reloaded.digest


def test_update_checkpoint_digest_missing_returns_none(store):
    r = dg.update_checkpoint_digest("ckpt_missing")
    assert r is None


def test_build_digest_estimates_token_count():
    r = dg.build_digest(_make(plan_json={
        "steps": [{"id": "s", "title": "t", "status": "pending",
                   "order": 0}],
    }))
    assert r.token_estimate > 0
    assert abs(r.token_estimate - len(r.text) // 4) <= 1
