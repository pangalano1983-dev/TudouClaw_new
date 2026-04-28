"""LangGraph-based agent chat (real LLM/tool execution).

Status: PoC — runs end-to-end with our actual LLM + tools, but is NOT
yet wired into ``Agent.chat_async``. Run via::

    python -m app.graph.agent_chat_graph "你的任务"

This replaces the simpler 6-phase ``task_graph.py`` PoC with a graph
shaped after LangGraph's official ReAct template:

    user → assistant_node ⇄ tool_node → END
                            (loop until no tool_calls)

Each node uses the platform's existing modules — we are NOT introducing
LangChain's agent / chain / memory abstractions.

  assistant_node  →  app.llm.chat_no_stream  (provider-aware, our quirks)
  tool_node       →  app.tools._TOOL_FUNCS   (our 40+ tool handlers)
  system prompt   →  app.system_prompt.compose_full_prompt
  llm routing     →  app.v2.bridges.llm_router.LLMRouter (5 slots)
  checkpoint      →  langgraph SqliteSaver (resume / replay)

Why we duplicate the V1 chat-loop logic in node form: LangGraph's
state model + checkpointer + interrupt() solve a long list of bugs
the V1 hand-rolled loop accumulated (plan/messages drift, watchdog
false fires, /new not persistent, history fold across plans). The
graph form is shorter, declarative, and reuses LangGraph's tested
infrastructure.
"""

from __future__ import annotations

import json
import logging
import operator
import os
import sqlite3
import sys
import time
from typing import Annotated, Any, Optional, TypedDict

logger = logging.getLogger("tudou.graph.chat")


# ─────────────────────────────────────────────────────────────────────
# State schema
# ─────────────────────────────────────────────────────────────────────


class ChatState(TypedDict, total=False):
    """LangGraph state for an agent chat session.

    Reducer rules:
      - ``messages`` is additive (operator.add) — every node returning
        new messages appends to history.
      - All other keys are replaced by each node's return.

    The shape mirrors OpenAI chat-completions messages directly so we
    can pass them straight to ``app.llm.chat_no_stream`` without
    translation; node functions take/return the same dicts the existing
    V1 chat loop uses.
    """
    messages: Annotated[list[dict], operator.add]
    agent_id: str
    role: str
    name: str
    language: str
    provider: str
    model: str
    iteration: int
    max_iterations: int
    last_finish_reason: str
    # Live Agent instance (when wired into Agent.chat_async). Lets graph
    # nodes reuse the real prompt builder / tool dispatch / sandbox /
    # approval logic instead of mock-style standalone paths.
    # Optional — empty means standalone PoC mode.
    _agent_ref: Any


# ─────────────────────────────────────────────────────────────────────
# Helpers — wrap our existing modules
# ─────────────────────────────────────────────────────────────────────


def _build_system_message(state: ChatState) -> dict:
    """Compose system prompt — prefers the real Agent's prompt builder
    if a live ``Agent`` instance is in state["_agent_ref"]; otherwise
    falls back to the stand-alone system_prompt module.

    When the graph plugs into ``Agent.chat_async``, the agent reference
    flows through state so the system prompt ends up identical to V1
    (DEFAULT + SETTINGS + PERSONA + dynamic context).
    """
    agent = state.get("_agent_ref")
    if agent is not None and hasattr(agent, "_build_static_system_prompt"):
        try:
            text = agent._build_static_system_prompt()
            return {"role": "system", "content": text}
        except Exception:
            pass

    from .. import system_prompt as sp
    text = sp.compose_full_prompt(
        name=state.get("name") or "Agent",
        role=state.get("role") or "default",
        language=state.get("language", "auto"),
        ctx_type="solo",
        working_dir=os.path.expanduser("~/.tudou_claw/graph_workspace"),
    )
    return {"role": "system", "content": text}


def _resolve_provider_model(state: ChatState, last_user_text: str) -> tuple[str, str]:
    """Read (provider, model) from state if present; otherwise consult
    config.yaml as a fallback. The graph itself is provider-agnostic —
    callers wiring an agent into the graph should populate state with
    that agent's own binding.
    """
    prov = (state.get("provider") or "").strip()
    mdl = (state.get("model") or "").strip()
    if prov and mdl:
        return prov, mdl
    from app import llm as _llm
    cfg = _llm.get_config()
    return cfg.get("provider", ""), cfg.get("model", "")


def _llm_call(state: ChatState, *, provider: str, model: str,
               force_no_tools: bool = False) -> dict:
    """Call our existing chat_no_stream with the graph's messages.

    Returns the assistant message dict. Tool calls are surfaced as
    ``message["tool_calls"]`` per OpenAI spec; ``app.llm`` already
    normalizes provider quirks (GLM fold-as-user, DeepSeek
    reasoning_content, etc.) so the assistant message comes back in a
    consistent shape regardless of provider.

    Tools come from the bound Agent's ``_get_effective_tools()`` (filtered
    by allowed_tools / role preset / capability skills) — not the global
    ``TOOL_DEFINITIONS`` registry. The PoC version sent the full 44-tool
    table (~38KB compressed) to every LLM call; that's the famous
    "tools=38311" anomaly in TOKEN-BREAKDOWN logs. Now matches the V1
    agent.chat() contract.
    """
    from app import llm as _llm
    from app.agent import cleanup_message_history
    msgs = list(state.get("messages") or [])
    # Prepend system prompt if missing or stale
    if not msgs or msgs[0].get("role") != "system":
        msgs = [_build_system_message(state)] + msgs

    # ── Comprehensive cleanup: orphan tool / empty content / bad role ──
    # See app.agent.cleanup_message_history for the full rule set.
    # Belt-and-suspenders with llm._sanitize_messages_for_openai which
    # also de-orphans at the LLM layer.
    msgs = cleanup_message_history(msgs, log_label="graph.chat")

    # ── Per-agent tool filtering ──
    # _agent_ref is the live Agent object — passed via graph state so we
    # can call its V1 tool-filtering pipeline (allowed_tools / role preset /
    # capability-skill tier filter). Falls back to the full registry only
    # if the ref is somehow missing (logs a warning so it's debuggable).
    agent_ref = state.get("_agent_ref")
    tool_defs: list[dict] | None = None
    if agent_ref is not None and hasattr(agent_ref, "_get_effective_tools"):
        try:
            tool_defs = agent_ref._get_effective_tools()
        except Exception as e:
            logger.warning(
                "[graph.chat] _get_effective_tools failed for agent=%s: %s "
                "— falling back to full registry",
                getattr(agent_ref, "id", "?")[:8], e,
            )
    if tool_defs is None:
        from app.tools import TOOL_DEFINITIONS
        tool_defs = TOOL_DEFINITIONS
        logger.warning(
            "[graph.chat] no agent_ref or filter failed; sending FULL "
            "tool registry (%d tools) to LLM — this bloats prompts",
            len(tool_defs),
        )

    # ── Set token-context on this thread ──
    # Graph nodes run on a worker thread (see Agent._run_graph), so the
    # main thread's set_token_context doesn't propagate. Tag the call
    # explicitly so TOKEN-BREAKDOWN logs show agent= instead of agent=-.
    try:
        if agent_ref is not None and hasattr(agent_ref, "id"):
            _llm.set_token_context(
                agent_id=agent_ref.id,
                project_id=getattr(agent_ref, "project_id", "") or "",
                meeting_id=getattr(agent_ref, "source_meeting_id", "") or "",
            )
    except Exception:
        pass

    # When force_no_tools=True (loop-break near hard cap), pass tools=None
    # so the LLM has zero option to emit tool_calls. It MUST produce a
    # text answer.
    raw = _llm.chat_no_stream(
        messages=msgs,
        tools=None if force_no_tools else tool_defs,
        provider=provider,
        model=model,
    )
    # `raw` shape: {"message": {role, content, tool_calls, ...}, ...}
    # or older Ollama-style {"message": {...}}.
    if isinstance(raw, dict):
        msg = raw.get("message") or raw
        if isinstance(msg, dict) and msg.get("role"):
            return msg
    # Fallback: empty assistant (no tool_calls field — strict APIs reject [])
    return {"role": "assistant", "content": str(raw)[:500]}


# ─────────────────────────────────────────────────────────────────────
# Nodes
# ─────────────────────────────────────────────────────────────────────


def _assistant_node(state: ChatState) -> dict:
    """One LLM turn: call the model with current messages + tools.

    Returns the assistant message (possibly with tool_calls). Iteration
    is tracked here so the conditional edge can break out of runaway
    loops without relying on LangGraph's recursion_limit alone.

    Loop-breaking heuristics (mirrors V1's narrator_nudge protocol):
      • iteration >= soft_cap (8): inject a system "wrap up" reminder
        before the next LLM call so the agent gets a chance to summarize
      • iteration >= hard_cap-1: force tool_choice="none" so the LLM
        physically cannot emit more tool_calls — it MUST produce a final
        text answer
    """
    iteration = state.get("iteration", 0) + 1
    last_user = ""
    for m in reversed(state.get("messages") or []):
        if m.get("role") == "user":
            c = m.get("content")
            last_user = c if isinstance(c, str) else json.dumps(c)
            break

    provider, model = _resolve_provider_model(state, last_user)
    logger.info(
        "[graph.chat.assistant] iter=%d provider=%s model=%s",
        iteration, provider, model,
    )

    # Loop-break: nudge at soft_cap, force stop near hard_cap.
    max_iter = state.get("max_iterations", 20)
    soft_cap = max(4, max_iter // 2)
    hard_cap_minus_1 = max_iter - 1

    nudge_msg: dict | None = None
    force_no_tools = False

    if iteration >= hard_cap_minus_1:
        force_no_tools = True
        logger.warning(
            "[graph.chat.assistant] iter=%d ≥ hard_cap-1=%d — forcing "
            "tool_choice=none so LLM produces final answer",
            iteration, hard_cap_minus_1,
        )
        nudge_msg = {
            "role": "system",
            "content": (
                f"⚠️ 你已经做了 {iteration-1} 轮工具调用,接近上限。"
                f"现在**必须直接回答用户**,不再调用任何工具。"
                f"基于已收集的信息总结一个完整答复。"
            ),
        }
    elif iteration >= soft_cap:
        logger.info(
            "[graph.chat.assistant] iter=%d ≥ soft_cap=%d — injecting "
            "wrap-up nudge", iteration, soft_cap,
        )
        nudge_msg = {
            "role": "system",
            "content": (
                f"提示:你已经做了 {iteration-1} 轮工具调用。"
                f"如果信息已够,**优先直接回答**,而不是继续调用工具。"
                f"只在确实必要时才再调一两个工具。"
            ),
        }

    # Inject nudge into a SHALLOW-COPIED state so it only affects this
    # turn's LLM call — doesn't pollute the persistent message history.
    if nudge_msg is not None:
        _msgs = list(state.get("messages") or [])
        _msgs.append(nudge_msg)
        state = dict(state)
        state["messages"] = _msgs

    msg = _llm_call(state, provider=provider, model=model,
                     force_no_tools=force_no_tools)

    # ── Normalize tool_calls field ──
    # The router (_route_after_assistant) checks `last.get("tool_calls")`.
    # An empty list and a missing key both evaluate falsy, so we don't
    # NEED to set the field. And we MUST NOT — DeepSeek's API rejects
    # any assistant with `tool_calls: []`:
    #   "Invalid 'messages[N].tool_calls': empty array. Expected min 1"
    # So if the field is empty / None, drop it entirely. The conditional
    # routing still works correctly because both `None` and `[]` evaluate
    # falsy.
    has_tcs = bool(msg.get("tool_calls"))
    if not has_tcs and "tool_calls" in msg:
        msg.pop("tool_calls", None)

    return {
        "messages": [msg],
        "iteration": iteration,
        "last_finish_reason": "tool_calls" if has_tcs else "stop",
    }


def _tool_node(state: ChatState) -> dict:
    """Execute the latest assistant message's tool_calls.

    Routing priority:
      1. ``state["_agent_ref"]`` exists → use ``agent._execute_tool_with_policy``
         (full V1 path: sandbox + approval + spill + caller_agent injection).
      2. Otherwise fall back to direct ``_TOOL_FUNCS`` (PoC / standalone).
    """
    msgs = state.get("messages") or []
    if not msgs:
        return {}
    last = msgs[-1]
    tcs = last.get("tool_calls") or []
    if not tcs:
        return {}

    agent = state.get("_agent_ref")

    out_msgs: list[dict] = []
    for tc in tcs:
        if not isinstance(tc, dict):
            continue
        tcid = tc.get("id") or ""
        fn = tc.get("function") or {}
        name = fn.get("name", "") if isinstance(fn, dict) else ""
        args_raw = fn.get("arguments", "{}") if isinstance(fn, dict) else "{}"
        try:
            args = json.loads(args_raw) if isinstance(args_raw, str) else (args_raw or {})
        except (json.JSONDecodeError, TypeError):
            args = {}
        if not isinstance(args, dict):
            args = {"raw": str(args)}

        result: Any
        # Prefer the agent's policy-aware dispatch when wired in.
        if agent is not None and hasattr(agent, "_execute_tool_with_policy"):
            try:
                result = agent._execute_tool_with_policy(name, args)
            except Exception as e:
                result = f"[tool error] {type(e).__name__}: {e}"
        else:
            from app.tools import _TOOL_FUNCS
            handler = _TOOL_FUNCS.get(name)
            if handler is None:
                result = f"[error: unknown tool '{name}']"
            else:
                try:
                    result = handler(**args)
                except TypeError:
                    try:
                        result = handler(args)
                    except Exception as e:
                        result = f"[tool error] {type(e).__name__}: {e}"
                except Exception as e:
                    result = f"[tool error] {type(e).__name__}: {e}"

        out_msgs.append({
            "role": "tool",
            "tool_call_id": tcid,
            "content": result if isinstance(result, str) else json.dumps(
                result, ensure_ascii=False, default=str),
        })
        logger.info("[graph.chat.tool] %s → %d chars",
                     name, len(out_msgs[-1]["content"]))

    return {"messages": out_msgs}


# ─────────────────────────────────────────────────────────────────────
# Routing
# ─────────────────────────────────────────────────────────────────────


def _route_after_assistant(state: ChatState) -> str:
    """If the last assistant message has tool_calls, run them; else end.

    Includes a hard safety: if iteration exceeds ``max_iterations``,
    end regardless (prevents infinite tool-call loops).
    """
    iteration = state.get("iteration", 0)
    max_iter = state.get("max_iterations", 20)
    if iteration >= max_iter:
        logger.warning("[graph.chat] iteration cap %d hit; force end", max_iter)
        return "end"

    msgs = state.get("messages") or []
    if not msgs:
        return "end"
    last = msgs[-1]
    if last.get("role") != "assistant":
        return "end"
    return "tools" if (last.get("tool_calls") or []) else "end"


# ─────────────────────────────────────────────────────────────────────
# Graph builder
# ─────────────────────────────────────────────────────────────────────


def build_chat_graph(*, checkpoint_db: str = ""):
    """Compile the chat StateGraph.

    Pass ``checkpoint_db=""`` (default) for in-memory mode. Pass a
    SQLite path to enable resume — re-running the graph with the same
    ``thread_id`` config picks up where the last run left off (any
    interrupted assistant/tool turn restarts cleanly).
    """
    from langgraph.graph import StateGraph, END

    g = StateGraph(ChatState)
    g.add_node("assistant", _assistant_node)
    g.add_node("tools",     _tool_node)

    g.set_entry_point("assistant")
    g.add_conditional_edges(
        "assistant", _route_after_assistant,
        {"tools": "tools", "end": END},
    )
    # After tools run, loop back to assistant for the next decision
    g.add_edge("tools", "assistant")

    # Checkpointer (optional)
    checkpointer = None
    if checkpoint_db:
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver
            os.makedirs(os.path.dirname(checkpoint_db) or ".", exist_ok=True)
            conn = sqlite3.connect(checkpoint_db, check_same_thread=False)
            checkpointer = SqliteSaver(conn)
        except Exception as e:
            logger.warning("graph.chat: checkpointer disabled (%s)", e)

    if checkpointer is not None:
        return g.compile(checkpointer=checkpointer)
    return g.compile()


# ─────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────


def run_chat(
    user_message: str,
    *,
    agent_id: str = "graph_chat_poc",
    role: str = "default",
    name: str = "Agent",
    language: str = "zh-CN",
    max_iterations: int = 20,
    thread_id: str = "",
    checkpoint_db: str = "",
) -> ChatState:
    """Run a single user message through the chat graph to completion.

    Returns the final state, including the full messages list (system
    + user + N×(assistant ± tool)).
    """
    graph = build_chat_graph(checkpoint_db=checkpoint_db)
    initial: ChatState = {
        "messages": [{"role": "user", "content": user_message}],
        "agent_id": agent_id,
        "role": role,
        "name": name,
        "language": language,
        "iteration": 0,
        "max_iterations": max_iterations,
        "last_finish_reason": "",
    }
    config: dict = {}
    if thread_id and checkpoint_db:
        config = {"configurable": {"thread_id": thread_id}}
    return graph.invoke(initial, config=config)


# ─────────────────────────────────────────────────────────────────────
# Smoke test (real LLM call!)
# ─────────────────────────────────────────────────────────────────────


def _smoke_main() -> None:
    """End-to-end smoke that hits a REAL LLM. Reads
    config.yaml's global provider/model — make sure it's set before
    running.

    Usage::
        python -m app.graph.agent_chat_graph "你好"
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    user_msg = sys.argv[1] if len(sys.argv) > 1 else "请用一句话介绍你自己。"
    print(f"\n=== Chat graph smoke: {user_msg!r} ===\n")

    from app import llm as _llm
    cfg = _llm.get_config()
    if not cfg.get("provider") or not cfg.get("model"):
        print("⚠ No global provider/model configured in config.yaml — "
              "smoke test will likely fail. Set it via the portal first.")
        return

    final = run_chat(user_msg, max_iterations=8)
    print(f"\nfinal.iteration       = {final.get('iteration')}")
    print(f"final.last_finish     = {final.get('last_finish_reason')}")
    print(f"final.messages count  = {len(final.get('messages') or [])}")
    print()
    print("--- Conversation transcript ---")
    for m in (final.get("messages") or []):
        role = m.get("role", "?")
        if role == "system":
            continue   # skip system to keep output short
        if role == "tool":
            content = (m.get("content") or "")[:200]
            print(f"[tool {m.get('tool_call_id', '')[:14]}] {content}...")
        elif role == "assistant":
            content = m.get("content") or ""
            tcs = m.get("tool_calls") or []
            if tcs:
                names = [
                    (tc.get("function") or {}).get("name", "?")
                    for tc in tcs
                ]
                print(f"[assistant tool_call] → {', '.join(names)}")
            if content:
                print(f"[assistant] {content[:500]}")
        elif role == "user":
            print(f"[user] {m.get('content')!r}")
    print("\n=== Smoke complete ===")


if __name__ == "__main__":
    _smoke_main()
