"""LangGraph-based task state machine (PoC).

Replaces the V1 ad-hoc plan-tracking + V2 deprecated TaskLoop with a
single explicit StateGraph. Uses our own ``app.llm`` / ``app.tools`` /
``app.system_prompt`` / ``app.knowledge`` — LangGraph handles only:
  - state schema (TypedDict, additive vs replace semantics)
  - phase transitions (conditional edges)
  - checkpointing (SqliteSaver) → automatic resume / replay
  - HITL interrupts

This is PoC — no API endpoint binds to it yet. Tests live in
``smoke_main`` at the bottom of ``task_graph.py``. Run::

    python -m app.graph.task_graph

to see a 6-phase task tick through with a mock LLM.
"""
from .task_graph import (
    TaskState,
    build_task_graph,
    run_task,
)

__all__ = ["TaskState", "build_task_graph", "run_task"]
