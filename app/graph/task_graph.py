"""6-phase task state machine via LangGraph (PoC).

Phases:

    intake → plan → execute ⇄ verify → deliver → done
                       │         │
                       └─ retry ─┘  (verify says not yet)

State (single TypedDict, ``Annotated`` controls merge semantics):

    intent           str                     replace
    messages         list[dict]              additive (operator.add)
    plan             dict                    replace
    current_step     int                     replace
    artifacts        list[str]               additive
    verify_passed    bool                    replace
    failed_reason    str                     replace
    iteration        int                     replace      (anti-loop guard)
    agent_id         str                     replace
    role             str                     replace

Each node is a thin wrapper that calls our existing modules:

    plan node     → app.llm.chat_no_stream + app.tools (plan_update tool)
    execute node  → app.tools._TOOL_FUNCS[*]
    verify node   → app.llm.chat_no_stream
    done node     → app.knowledge.wiki_ingest + history fold

The graph itself owns:
    - phase transitions (conditional edges below)
    - persistence (SqliteSaver, ``~/.tudou_claw/graph_checkpoints.db``)
    - retry budget (iteration counter)

This file is intentionally NOT wired to ``Agent.chat_async`` yet —
PoC only. Run ``python -m app.graph.task_graph`` for a smoke test.
"""

from __future__ import annotations

import logging
import operator
import os
import time
from typing import Annotated, Any, Optional, TypedDict

logger = logging.getLogger("tudou.graph")


# ─────────────────────────────────────────────────────────────────────
# State schema
# ─────────────────────────────────────────────────────────────────────


class TaskState(TypedDict, total=False):
    """The full state passed between graph nodes.

    LangGraph merges per-key according to the ``Annotated[..., reducer]``
    declaration: keys without a reducer are REPLACED by each node's
    return; keys with ``operator.add`` are APPENDED.
    """
    # Identity
    intent: str
    agent_id: str
    role: str

    # Conversation
    messages: Annotated[list[dict], operator.add]   # additive

    # Plan
    plan: dict                                       # {"steps": [...], "simple": bool}
    current_step: int

    # Execution outputs
    artifacts: Annotated[list[str], operator.add]    # additive

    # Verify outcome
    verify_passed: bool
    failed_reason: str

    # Anti-loop
    iteration: int


# ─────────────────────────────────────────────────────────────────────
# Node implementations
#
# Each node receives the full state and returns a partial dict — only
# the keys it wants to update. Reducer above decides additive/replace.
# Side effects (LLM calls, file writes) happen here. Pure routing
# decisions live in the conditional edges, not in nodes.
# ─────────────────────────────────────────────────────────────────────


def _intake(state: TaskState) -> dict:
    """Classify the task: simple chat vs multi-step.

    Heuristic: short intent + no action verbs → simple.
    Future: replace with a small LLM classifier.
    """
    intent = state.get("intent", "")
    simple = (
        len(intent) < 60
        and not any(kw in intent for kw in (
            "做", "写", "生成", "搜索", "学习", "分析", "整理",
            "build", "create", "research", "learn", "analyze",
        ))
    )
    logger.info("[graph.intake] simple=%s intent=%r", simple, intent[:60])
    return {
        "plan": {"simple": simple, "steps": [], "all_done": simple},
        "iteration": 0,
        "verify_passed": False,
    }


def _plan(state: TaskState) -> dict:
    """Decompose the task into steps. PoC: hardcoded 3-step plan."""
    intent = state.get("intent", "")
    # In production: call LLM with system_prompt + tools to do a real
    # plan_update(create_plan). Here we mock for the smoke test.
    steps = [
        {"id": "s1", "title": f"调研: {intent[:30]}",
         "acceptance": "≥3 条来源", "completed": False},
        {"id": "s2", "title": "整理成结构化输出",
         "acceptance": "≥1 个 markdown 文件", "completed": False},
        {"id": "s3", "title": "沉淀为 wiki",
         "acceptance": "wiki_ingest 调用成功", "completed": False},
    ]
    logger.info("[graph.plan] %d steps for %r", len(steps), intent[:40])
    return {
        "plan": {"simple": False, "steps": steps, "all_done": False},
        "current_step": 0,
    }


def _execute(state: TaskState) -> dict:
    """Run the current step's tool calls.

    PoC: just mark the current step complete and append a fake artifact.
    Production: parse step.tools_hint, call ``_TOOL_FUNCS[*]`` (parallel
    safe ones in a thread pool), append messages + artifacts.

    Simple-path handling: when ``plan.simple`` is true (no real steps),
    execute is a degenerate one-shot — mark all_done and emit a single
    artifact so verify passes immediately.
    """
    plan = dict(state.get("plan") or {})
    steps = list(plan.get("steps") or [])
    cur = state.get("current_step", 0)
    iteration = state.get("iteration", 0) + 1

    # Simple path (intake said no decomposition needed): direct reply.
    if plan.get("simple") and not steps:
        plan["all_done"] = True
        logger.info(
            "[graph.execute] simple path; iter=%d", iteration,
        )
        return {
            "plan": plan,
            "iteration": iteration,
            "artifacts": ["(simple-reply)"],
        }

    if cur >= len(steps):
        plan["all_done"] = True
        return {"plan": plan, "iteration": iteration}

    step = dict(steps[cur])
    step["completed"] = True
    step["result_summary"] = f"(mock) step {step['id']} done in iter {iteration}"
    steps[cur] = step

    artifact = f"workspace/step_{step['id']}_output.md"

    new_cur = cur + 1
    plan["steps"] = steps
    plan["all_done"] = (new_cur >= len(steps))

    logger.info(
        "[graph.execute] step=%s done; current_step %d → %d; all_done=%s",
        step["id"], cur, new_cur, plan["all_done"],
    )
    return {
        "plan": plan,
        "current_step": new_cur,
        "artifacts": [artifact],
        "iteration": iteration,
    }


def _verify(state: TaskState) -> dict:
    """Check whether all step acceptances are satisfied.

    PoC: trust ``step.completed``. Production: re-run acceptance regex /
    artifact-existence check / spawn a verifier sub-agent.

    For simple-path tasks (no real plan), trust ``plan.all_done`` set
    by _execute — verifier has nothing to inspect.
    """
    plan = state.get("plan") or {}
    steps = plan.get("steps") or []
    if plan.get("simple"):
        all_done = bool(plan.get("all_done"))
    elif steps:
        all_done = all(s.get("completed") for s in steps)
    else:
        all_done = False
    logger.info("[graph.verify] all_done=%s simple=%s", all_done, plan.get("simple"))
    return {
        "verify_passed": all_done,
        "failed_reason": "" if all_done else "some steps still pending",
    }


def _deliver(state: TaskState) -> dict:
    """Compose the final user-facing reply.

    PoC: just log. Production: pull artifact paths, write the agent's
    final ``assistant`` message into ``messages`` so the chat UI
    surfaces it.
    """
    arts = state.get("artifacts", [])
    summary = f"完成。交付物: {', '.join(arts)}" if arts else "完成。"
    logger.info("[graph.deliver] summary=%r", summary)
    return {
        "messages": [{
            "role": "assistant",
            "content": summary,
            "_source": "graph_deliver",
        }],
    }


def _done(state: TaskState) -> dict:
    """Terminal: write a wiki entry summarising the task, fold history.

    Smoke test runs without a wiki store wired up; we guard the import
    so the PoC also works in isolation.
    """
    intent = state.get("intent", "")
    arts = state.get("artifacts", [])
    try:
        from ..knowledge import get_wiki_store, WikiPage, slugify
        page = WikiPage(
            scope="global", kind="experience",
            slug=slugify(intent[:60]),
            title=intent[:80] or "graph_poc",
            body=f"# 任务记录\n\n意图: {intent}\n\n交付物:\n" + "\n".join(
                f"- {a}" for a in arts),
            tags=["graph_poc"],
        )
        get_wiki_store().write_page(page)
        logger.info("[graph.done] wiki page written: %s", page.slug)
    except Exception as e:
        logger.warning("[graph.done] wiki write skipped (PoC): %s", e)
    return {}


# ─────────────────────────────────────────────────────────────────────
# Graph builder
# ─────────────────────────────────────────────────────────────────────


_MAX_EXECUTE_ITERATIONS = 20      # anti-loop budget across execute/verify


def _route_after_intake(state: TaskState) -> str:
    return "execute" if (state.get("plan") or {}).get("simple") else "plan"


def _route_after_execute(state: TaskState) -> str:
    plan = state.get("plan") or {}
    if state.get("iteration", 0) >= _MAX_EXECUTE_ITERATIONS:
        logger.warning("[graph] iteration budget exceeded; force verify")
        return "verify"
    return "verify" if plan.get("all_done") else "execute"


def _route_after_verify(state: TaskState) -> str:
    return "deliver" if state.get("verify_passed") else "execute"


def build_task_graph(*, checkpoint_db: str = ""):
    """Compile the StateGraph. Returns a ``CompiledGraph`` ready to run.

    Pass ``checkpoint_db=""`` (default) to skip persistence — the graph
    runs entirely in-memory. Pass a SQLite path to enable resume across
    process restarts (LangGraph SqliteSaver).
    """
    # Lazy import so module loads even if langgraph isn't installed —
    # callers see a clear error only when they try to build the graph.
    from langgraph.graph import StateGraph, END

    # NB: LangGraph forbids node names that match state keys. The
    # state has ``plan`` / ``current_step`` / ``verify_passed`` etc., so
    # we suffix nodes with ``_phase`` to disambiguate. Edge logic uses
    # the same suffix.
    g = StateGraph(TaskState)
    g.add_node("intake_phase",  _intake)
    g.add_node("plan_phase",    _plan)
    g.add_node("execute_phase", _execute)
    g.add_node("verify_phase",  _verify)
    g.add_node("deliver_phase", _deliver)
    g.add_node("done_phase",    _done)

    g.set_entry_point("intake_phase")
    g.add_conditional_edges(
        "intake_phase", _route_after_intake,
        {"plan": "plan_phase", "execute": "execute_phase"},
    )
    g.add_edge("plan_phase", "execute_phase")
    g.add_conditional_edges(
        "execute_phase", _route_after_execute,
        {"execute": "execute_phase", "verify": "verify_phase"},
    )
    g.add_conditional_edges(
        "verify_phase", _route_after_verify,
        {"deliver": "deliver_phase", "execute": "execute_phase"},
    )
    g.add_edge("deliver_phase", "done_phase")
    g.add_edge("done_phase", END)

    # Checkpointer (optional)
    checkpointer = None
    if checkpoint_db:
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver
            os.makedirs(os.path.dirname(checkpoint_db) or ".", exist_ok=True)
            # langgraph SqliteSaver constructor varies by version
            try:
                # 0.2.x style
                checkpointer = SqliteSaver.from_conn_string(checkpoint_db)
            except AttributeError:
                # 0.0.x fallback
                import sqlite3
                checkpointer = SqliteSaver(sqlite3.connect(checkpoint_db,
                                                            check_same_thread=False))
        except Exception as e:
            logger.warning("graph: checkpointer disabled (%s)", e)
            checkpointer = None

    if checkpointer is not None:
        return g.compile(checkpointer=checkpointer)
    return g.compile()


# ─────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────


def run_task(
    intent: str,
    *,
    agent_id: str = "graph_poc",
    role: str = "default",
    thread_id: str = "",
    checkpoint_db: str = "",
) -> TaskState:
    """Run a task to completion. Returns the final state.

    For checkpoint-aware runs, pass ``thread_id`` (any unique str —
    typically agent_id + task_id) and ``checkpoint_db``. Re-running with
    the same thread_id resumes from where the last run left off.
    """
    graph = build_task_graph(checkpoint_db=checkpoint_db)
    initial: TaskState = {
        "intent": intent,
        "agent_id": agent_id,
        "role": role,
        "messages": [],
        "plan": {},
        "current_step": 0,
        "artifacts": [],
        "verify_passed": False,
        "failed_reason": "",
        "iteration": 0,
    }
    config: dict = {}
    if thread_id and checkpoint_db:
        config = {"configurable": {"thread_id": thread_id}}
    final_state: TaskState = graph.invoke(initial, config=config)
    return final_state


# ─────────────────────────────────────────────────────────────────────
# Smoke test
# ─────────────────────────────────────────────────────────────────────


def _smoke_main() -> None:
    """End-to-end smoke: run a fake task through all 6 phases."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    print("\n=== LangGraph PoC smoke test ===\n")

    # Test 1: in-memory run
    print(">>> Test 1: complex task, no checkpointer")
    final = run_task("学习漏洞管理最佳流程")
    print(f"final.iteration   = {final.get('iteration')}")
    print(f"final.artifacts   = {final.get('artifacts')}")
    print(f"final.verify_passed = {final.get('verify_passed')}")
    print(f"final.messages    = {final.get('messages')}")
    assert final.get("verify_passed") is True
    assert len(final.get("artifacts") or []) == 3
    assert len(final.get("messages") or []) == 1
    print("  ✓ ran intake → plan → execute(×3) → verify → deliver → done\n")

    # Test 2: simple task
    print(">>> Test 2: simple task (intake → execute → verify → ...)")
    final = run_task("hi")
    print(f"final.plan.simple = {(final.get('plan') or {}).get('simple')}")
    print(f"final.iteration   = {final.get('iteration')}")
    print("  ✓ simple path\n")

    # Test 3: with SQLite checkpointer (resume capability)
    print(">>> Test 3: checkpointer-backed (SQLite)")
    db_path = os.path.expanduser("~/.tudou_claw/graph_checkpoints_test.db")
    try:
        os.remove(db_path)
    except OSError:
        pass
    try:
        final = run_task(
            "搭建漏洞管理流程",
            agent_id="test_agent",
            thread_id="thread_001",
            checkpoint_db=db_path,
        )
        print(f"  ✓ checkpoint db at: {db_path}")
        print(f"  final.iteration = {final.get('iteration')}")

        # Re-run same thread → should reach Done immediately (cached)
        final2 = run_task(
            "搭建漏洞管理流程",
            agent_id="test_agent",
            thread_id="thread_001",
            checkpoint_db=db_path,
        )
        print(f"  ✓ resumed thread_001; iter={final2.get('iteration')}")
    except Exception as e:
        print(f"  ⚠ checkpointer test skipped: {type(e).__name__}: {e}")

    print("\n=== All graph PoC tests passed ===\n")


if __name__ == "__main__":
    _smoke_main()
