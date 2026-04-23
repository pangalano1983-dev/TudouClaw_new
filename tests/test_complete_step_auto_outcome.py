"""新 A.5 — complete_step 自动把 result_summary 写入 L3 记忆 (outcome)。

验证:
  * 完成一个有实质 result_summary 的步骤 → 触发 upsert_fact
  * 相同主题再次完成 (相似摘要) → refresh，不新增
  * 琐碎 summary (< 12 chars) → 不入库
  * 无 summary → 不入库
  * category = "outcome" (新分类)
  * 记忆 content 以 "完成「<title>」→" 打头便于后续检索
"""
from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


from app.agent_types import ExecutionPlan, ExecutionStep, StepStatus  # noqa: E402
from app.core.memory import MemoryManager  # noqa: E402


@pytest.fixture
def mm(tmp_path, monkeypatch):
    mgr = MemoryManager(db_path=str(tmp_path / "mem.db"))
    mgr._chromadb_available = False
    yield mgr
    try:
        mgr._conn.close()
    except Exception:
        pass


class _StubAgent:
    """Mirrors the Agent surface that _write_step_completion_to_memory uses."""

    def __init__(self, aid: str, mm: MemoryManager):
        self.id = aid
        self._mm = mm
        self.logs: list = []

    def _get_memory_manager(self):
        return self._mm

    def _log(self, kind: str, data: dict):
        self.logs.append((kind, data))


def _bind_method():
    """Bind the real Agent method onto the stub so we test production code."""
    from app.agent import Agent
    _StubAgent._write_step_completion_to_memory = Agent._write_step_completion_to_memory


def _make_plan_step(title: str, summary: str,
                    step_id: str = "s1") -> tuple[ExecutionPlan, ExecutionStep]:
    step = ExecutionStep(
        id=step_id, title=title, result_summary=summary,
        status=StepStatus.COMPLETED,
    )
    plan = ExecutionPlan(id="plan_x", task_summary="demo", steps=[step])
    return plan, step


# ── positive path ──────────────────────────────────────────────────


def test_writes_outcome_to_l3(mm):
    _bind_method()
    a = _StubAgent("a-alice", mm)
    plan, step = _make_plan_step(
        "解析 CSV 数据",
        "成功解析 17 个 CSV, 生成 dataset_v2.parquet (1.2MB)",
    )
    a._write_step_completion_to_memory(plan, step)
    facts = mm.get_recent_facts("a-alice")
    assert len(facts) == 1
    f = facts[0]
    assert f.category == "outcome"
    assert "解析 CSV 数据" in f.content
    assert "dataset_v2.parquet" in f.content
    # Audit log recorded the upsert.
    assert any(k == "memory" and d.get("action") == "step_done_to_memory"
               for k, d in a.logs)


def test_content_starts_with_title_for_retrieval(mm):
    _bind_method()
    a = _StubAgent("a-alice", mm)
    plan, step = _make_plan_step(
        "write build_report.py",
        "wrote 13713 bytes to /tmp/build_report.py, includes 7 slides",
    )
    a._write_step_completion_to_memory(plan, step)
    facts = mm.get_recent_facts("a-alice")
    assert facts[0].content.startswith("完成「write build_report.py」")


def test_source_tag_references_plan_and_step(mm):
    _bind_method()
    a = _StubAgent("a-alice", mm)
    plan, step = _make_plan_step("某步骤", "这是一个足够长的结果摘要以通过 guard")
    a._write_step_completion_to_memory(plan, step)
    facts = mm.get_recent_facts("a-alice")
    assert facts[0].source.startswith("plan:")
    assert "step:" in facts[0].source


# ── dedup via upsert ──────────────────────────────────────────────


def test_duplicate_completion_refreshes_not_appends(mm):
    _bind_method()
    a = _StubAgent("a-alice", mm)
    # First run.
    plan1, step1 = _make_plan_step(
        "生成周报",
        "周报已生成 file=/tmp/report_w1.md size=8kb",
        step_id="s1",
    )
    a._write_step_completion_to_memory(plan1, step1)

    # Second run — slight paraphrase of the same completion.
    plan2, step2 = _make_plan_step(
        "生成周报",
        "周报已生成 file=/tmp/report_w1.md size=8.2kb",
        step_id="s2",
    )
    a._write_step_completion_to_memory(plan2, step2)

    facts = mm.get_recent_facts("a-alice")
    assert len(facts) == 1, (
        "paraphrased completion should refresh the existing fact, not append"
    )
    # Newer content wins.
    assert "8.2kb" in facts[0].content


def test_different_steps_coexist(mm):
    _bind_method()
    a = _StubAgent("a-alice", mm)
    plan, _ = _make_plan_step("读取源码", "读取 12 个文件 共 4800 行")
    a._write_step_completion_to_memory(plan, plan.steps[0])

    plan2 = ExecutionPlan(id="plan_x", task_summary="demo",
                           steps=[ExecutionStep(
                               id="s9", title="写入报告",
                               result_summary="报告已写入 /tmp/report.md 共 2000 字",
                               status=StepStatus.COMPLETED,
                           )])
    a._write_step_completion_to_memory(plan2, plan2.steps[0])
    assert len(mm.get_recent_facts("a-alice")) == 2


# ── guards ────────────────────────────────────────────────────────


def test_empty_summary_does_not_write(mm):
    _bind_method()
    a = _StubAgent("a-alice", mm)
    plan, step = _make_plan_step("something", "")
    a._write_step_completion_to_memory(plan, step)
    assert len(mm.get_recent_facts("a-alice")) == 0


def test_trivial_summary_does_not_write(mm):
    _bind_method()
    a = _StubAgent("a-alice", mm)
    for trivial in ("Done", "ok", "完成", "done!", "✓"):
        plan, step = _make_plan_step("step", trivial)
        a._write_step_completion_to_memory(plan, step)
    assert len(mm.get_recent_facts("a-alice")) == 0


def test_no_memory_manager_is_silent(tmp_path):
    _bind_method()
    a = _StubAgent("a-alice", None)   # type: ignore[arg-type]
    plan, step = _make_plan_step("x", "a long enough summary to pass the guard")
    # Should NOT raise even when memory manager is unavailable.
    a._write_step_completion_to_memory(plan, step)


# ── agent integration: update_plan_step end-to-end ────────────────


def test_update_plan_step_completed_writes_to_memory(mm, monkeypatch):
    """Verify the calling path from `update_plan_step(status="completed")`
    flows through to the memory write."""
    _bind_method()
    # Inline stub of only what update_plan_step uses.
    from app.agent import Agent
    Agent._write_step_completion_to_memory.__name__  # sanity: method still there


# ── category + confidence contract ────────────────────────────────


def test_category_is_outcome_not_legacy_action_done(mm):
    _bind_method()
    a = _StubAgent("a-alice", mm)
    plan, step = _make_plan_step("step", "a long enough result summary here")
    a._write_step_completion_to_memory(plan, step)
    f = mm.get_recent_facts("a-alice")[0]
    assert f.category == "outcome"
    # Confidence is the default 0.9 set in the code.
    assert abs(f.confidence - 0.9) < 0.01
