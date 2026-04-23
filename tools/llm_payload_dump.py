"""Dump the actual OpenAI-style request payload sent to the LLM, for one agent.

Shows you:
  * exact `messages` array (role + content preview + size per message)
  * exact `tools` array (tool names + arg names — no full schemas)
  * total payload size

Usage:
    python tools/llm_payload_dump.py <agent_id_prefix> [--full]

Without --full, each message's content is truncated to 200 chars.
"""
from __future__ import annotations

import json
import os
import sys


def tok(n_chars: int) -> int:
    return max(1, n_chars // 4)


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    full = "--full" in sys.argv[1:]
    prefix = args[0] if args else "3ea6b18d"

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # Load the agent from persisted state.
    path = os.path.expanduser("~/.tudou_claw/agents.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    agents = data.get("agents", data) if isinstance(data, dict) else data
    agent = None
    for a in agents:
        if isinstance(a, dict) and a.get("id", "").startswith(prefix):
            agent = a
            break
    if agent is None:
        print(f"❌ agent with prefix {prefix} not found")
        sys.exit(1)

    msgs = agent.get("messages") or []
    prof = agent.get("profile", {}) or {}
    max_ctx = int(prof.get("max_context_messages") or 50)

    # Simulate _trim_context: keep system[0] + last max_ctx non-system
    kept = msgs
    if max_ctx > 0 and len(msgs) > max_ctx + 1:
        sys_msg = msgs[0] if msgs[0].get("role") == "system" else None
        kept = ([sys_msg] if sys_msg else []) + msgs[-max_ctx:]

    # Grab effective tools.
    from app import tools as _tools
    try:
        from app.auth import get_auth
        denied_global = set(get_auth().tool_policy.list_global_denylist())
    except Exception:
        denied_global = set()
    allowed = set(prof.get("allowed_tools") or [])
    denied = set(prof.get("denied_tools") or [])
    defs = _tools.get_tool_definitions()

    def _n(d):
        return d.get("function", {}).get("name") or d.get("name") or ""

    eff = [d for d in defs
           if (not allowed or _n(d) in allowed)
           and _n(d) not in denied
           and _n(d) not in denied_global]

    print(f"\n===== LLM payload for agent {agent['id']} ({agent.get('name')}) =====")
    print(f"model (inferred from profile): {prof.get('model') or '(provider default)'}")
    print(f"allowed_tools: {sorted(allowed) if allowed else '[] (= ALL)'}")
    print(f"denied_tools:  {sorted(denied) if denied else '[]'}")
    print(f"global denylist: {sorted(denied_global) if denied_global else '[]'}")
    print(f"max_context_messages: {max_ctx}")
    print(f"stored messages: {len(msgs)}    sent to LLM (after trim): {len(kept)}\n")

    # ── messages array ────────────────────────────────────────────
    print("─" * 78)
    print("messages = [")
    total_msg_chars = 0
    for i, m in enumerate(kept):
        role = m.get("role", "?")
        content = m.get("content", "")
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False, default=str)
        extras = {k: m[k] for k in ("tool_calls", "tool_call_id", "name", "source")
                  if k in m}
        n = len(content) + len(json.dumps(extras, ensure_ascii=False, default=str) if extras else "")
        total_msg_chars += n
        if full:
            disp = content
        else:
            one = content.replace("\n", " ⏎ ")
            disp = (one[:200] + "…") if len(one) > 200 else one
        extra_s = f"  extras={list(extras.keys())}" if extras else ""
        print(f"  [{i:>2}] role={role:<10s} {n:>6} chars  ~{tok(n):>5} tok{extra_s}")
        print(f"       │ {disp}")
    print("]")

    # ── tools array ───────────────────────────────────────────────
    tools_json = json.dumps(eff, ensure_ascii=False)
    print("\n" + "─" * 78)
    print(f"tools = [  # {len(eff)} entries, total {len(tools_json)} chars ~{tok(len(tools_json))} tokens")
    for d in eff:
        name = _n(d)
        fn = d.get("function", {})
        params = (fn.get("parameters") or {}).get("properties") or {}
        required = (fn.get("parameters") or {}).get("required") or []
        sz = len(json.dumps(d, ensure_ascii=False))
        arg_list = []
        for k in params:
            tag = "*" if k in required else ""
            arg_list.append(f"{k}{tag}")
        arg_str = ", ".join(arg_list[:8])
        if len(arg_list) > 8:
            arg_str += f", …+{len(arg_list)-8}"
        desc = (fn.get("description") or "").replace("\n", " ")
        desc_s = (desc[:60] + "…") if len(desc) > 60 else desc
        print(f"  {name:<30s} {sz:>5} ch ~{tok(sz):>4} tok  args({arg_str})")
        print(f"      │ {desc_s}")
    print("]")

    # ── totals ────────────────────────────────────────────────────
    msg_tokens = tok(total_msg_chars)
    tool_tokens = tok(len(tools_json))
    total = msg_tokens + tool_tokens
    print("\n" + "=" * 78)
    print(f"EFFECTIVE PAYLOAD  (what actually goes on the wire to the LLM):")
    print(f"   messages:  {total_msg_chars:>8} chars  ~{msg_tokens:>6} tokens  ({len(kept)} messages)")
    print(f"   tools:     {len(tools_json):>8} chars  ~{tool_tokens:>6} tokens  ({len(eff)} tools)")
    print(f"   ─────")
    print(f"   total:                    ~{total:>6} tokens  (per LLM round-trip)")
    print()


if __name__ == "__main__":
    main()
