"""诊断脚本：分解一个 agent 每轮 chat() 喂给 LLM 的 token 组成。

用法：
    python tools/token_breakdown.py <agent_id_prefix>

输出：各段字符数 / 估算 token 数（4 char ≈ 1 token）+ 占比。
"""
from __future__ import annotations

import json
import os
import sys


def tok(s: str | None) -> int:
    """Rough char/4 heuristic; good enough for order-of-magnitude breakdown."""
    if not s:
        return 0
    return max(1, len(s) // 4)


def hfmt(n: int) -> str:
    if n >= 1000:
        return f"{n/1000:.1f}k"
    return str(n)


def load_agent(agent_id_prefix: str) -> dict | None:
    path = os.path.expanduser("~/.tudou_claw/agents.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    agents = data.get("agents", data) if isinstance(data, dict) else data
    for a in agents:
        if isinstance(a, dict) and a.get("id", "").startswith(agent_id_prefix):
            return a
    return None


def main() -> None:
    agent_id_prefix = sys.argv[1] if len(sys.argv) > 1 else "3ea6b18d"
    a = load_agent(agent_id_prefix)
    if a is None:
        print(f"❌ agent with prefix {agent_id_prefix} not found")
        sys.exit(1)

    print(f"\n===== Agent: {a['id']} ({a.get('name')}) role={a.get('role')} =====\n")

    # ── 1. Tool schemas ───────────────────────────────────────────
    # Import here so CLAUDE_DATA_DIR etc. in ambient env don't break
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app import tools as _tools

    all_defs = _tools.get_tool_definitions()
    all_defs_json = json.dumps(all_defs, ensure_ascii=False)

    prof = a.get("profile", {}) or {}
    allowed = set(prof.get("allowed_tools") or [])
    denied = set(prof.get("denied_tools") or [])

    def _fname(d):
        return (d.get("function", {}).get("name") or d.get("name") or "")

    effective_defs = all_defs
    # Mirror the new _get_effective_tools logic in app/agent.py:
    #  profile.allowed_tools → role_preset.allowed_tools → MINIMAL_DEFAULT_TOOLS
    if not allowed:
        # Try role preset
        try:
            from app.role_preset_registry import get_registry
            role = a.get("role") or ""
            preset = get_registry().get(role) if role else None
            if preset is not None and getattr(preset, "allowed_tools", None):
                allowed = set(preset.allowed_tools)
        except Exception:
            pass
    if not allowed:
        # Final fallback — keep this list in sync with
        # app.agent.Agent._MINIMAL_DEFAULT_TOOLS
        allowed = {"read_file", "write_file", "edit_file",
                   "search_files", "glob_files",
                   "bash", "run_tests",
                   "web_search", "web_fetch",
                   "plan_update", "complete_step",
                   "get_skill_guide"}
    effective_defs = [d for d in effective_defs if _fname(d) in allowed]
    if denied:
        effective_defs = [d for d in effective_defs if _fname(d) not in denied]
    # Also honor global denylist
    try:
        from app.auth import get_auth
        _dn = set(get_auth().tool_policy.list_global_denylist())
        effective_defs = [d for d in effective_defs if _fname(d) not in _dn]
    except Exception:
        pass

    eff_json = json.dumps(effective_defs, ensure_ascii=False)

    print("── 1. 工具 schemas ──")
    print(f"   全部可用工具:   {len(all_defs)} 个,  {len(all_defs_json):>8} chars  ~{tok(all_defs_json):>6} tokens")
    print(f"   该 agent 实际喂给 LLM:  {len(effective_defs)} 个,  {len(eff_json):>8} chars  ~{tok(eff_json):>6} tokens")
    if allowed:
        print(f"   (allowed_tools = {sorted(allowed)[:8]}{'...' if len(allowed)>8 else ''})")
    else:
        print(f"   ⚠️  allowed_tools = [] → agent 拿到了全部 {len(all_defs)} 个工具的完整 schema")

    # Top 10 largest tool schemas
    tool_sizes = [(_fname(d), len(json.dumps(d, ensure_ascii=False))) for d in effective_defs]
    tool_sizes.sort(key=lambda x: -x[1])
    print(f"   Top 10 最大工具 schema:")
    for i, (n, sz) in enumerate(tool_sizes[:10], 1):
        print(f"      {i:2d}. {n:<28s} {sz:>6} chars  ~{tok(str(sz)*1):>4} tokens… actually ~{tok('x'*sz):>4} tokens")

    # ── 2. 消息历史 ──────────────────────────────────────────────
    msgs = a.get("messages") or []
    total_msgs_chars = 0
    by_role: dict[str, int] = {}
    by_role_count: dict[str, int] = {}
    large_msgs: list[tuple[int, str, int]] = []
    for i, m in enumerate(msgs):
        role = m.get("role", "unknown")
        content = m.get("content", "")
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False, default=str)
        # Tool-call / tool_result also live on messages
        extra = ""
        for k in ("tool_calls", "tool_call_id", "name"):
            v = m.get(k)
            if v:
                extra += json.dumps(v, ensure_ascii=False, default=str)
        total = len(content) + len(extra)
        total_msgs_chars += total
        by_role[role] = by_role.get(role, 0) + total
        by_role_count[role] = by_role_count.get(role, 0) + 1
        if total > 2000:
            preview = (content[:80] + "…") if len(content) > 80 else content
            preview = preview.replace("\n", " ")
            large_msgs.append((total, f"[{i}] {role}: {preview}", i))

    max_ctx = int(prof.get("max_context_messages") or 0)
    print("\n── 2. 消息历史 ──")
    print(f"   总消息条数: {len(msgs)}   max_context_messages={max_ctx or '(不限)'}")
    print(f"   全部消息累计: {total_msgs_chars:>8} chars  ~{tok('x'*total_msgs_chars):>6} tokens")
    if max_ctx and len(msgs) > max_ctx:
        # simulate trim: keep first system + last max_ctx
        sys_msg = msgs[0] if msgs and msgs[0].get("role") == "system" else None
        trimmed = ([sys_msg] if sys_msg else []) + msgs[-max_ctx:]
        trimmed_chars = 0
        for m in trimmed:
            c = m.get("content", "")
            if not isinstance(c, str):
                c = json.dumps(c, ensure_ascii=False, default=str)
            trimmed_chars += len(c)
        print(f"   ⚠️  被裁后保留 {len(trimmed)} 条,  {trimmed_chars:>8} chars  ~{tok('x'*trimmed_chars):>6} tokens")
    print(f"   按 role 分布:")
    for role in sorted(by_role.keys(), key=lambda r: -by_role[r]):
        chars = by_role[role]
        print(f"      {role:<10s} {by_role_count[role]:>3d} 条  {chars:>7} chars  ~{tok('x'*chars):>6} tokens")

    if large_msgs:
        large_msgs.sort(key=lambda x: -x[0])
        print(f"   Top 5 最大单条消息 (>2000 chars):")
        for sz, preview, _i in large_msgs[:5]:
            print(f"      {sz:>6} chars  {preview}")

    # ── 3. System prompt ────────────────────────────────────────
    sys_msg = msgs[0] if msgs and msgs[0].get("role") == "system" else None
    print("\n── 3. System prompt (messages[0]) ──")
    if sys_msg:
        sc = sys_msg.get("content", "")
        if not isinstance(sc, str):
            sc = json.dumps(sc, ensure_ascii=False, default=str)
        print(f"   长度: {len(sc):>8} chars  ~{tok('x'*len(sc)):>6} tokens")
        # Show top-level sections by heuristic (lines starting with #, ## etc.)
        sections = []
        cur_head = ""
        cur_buf: list[str] = []
        for line in sc.splitlines():
            if line.startswith("##") or line.startswith("# "):
                if cur_head or cur_buf:
                    sections.append((cur_head, sum(len(l) for l in cur_buf)))
                cur_head = line.strip()[:80]
                cur_buf = []
            else:
                cur_buf.append(line)
        if cur_head or cur_buf:
            sections.append((cur_head, sum(len(l) for l in cur_buf)))
        if sections:
            print(f"   主要段落 (按大小 top 8):")
            for h, sz in sorted(sections, key=lambda x: -x[1])[:8]:
                print(f"      ~{tok('x'*sz):>5} tokens  {h or '(前言)'}")
    else:
        print("   ⚠️  没有 system 消息（或第一条不是 system）")

    # ── 4. 总预算 ───────────────────────────────────────────────
    eff_tools_tokens = tok("x" * len(eff_json))
    msgs_tokens = tok("x" * total_msgs_chars)
    sys_tokens = tok("x" * len(sys_msg.get("content", ""))) if sys_msg else 0

    # sys_msg is in msgs[0], 所以直接加 msgs_tokens 包含了 sys_tokens
    grand_total = eff_tools_tokens + msgs_tokens  # system already in msgs

    print("\n── 4. 单次 LLM call 估算 ──")
    print(f"   工具 schemas:  ~{eff_tools_tokens:>6} tokens")
    print(f"   消息历史全量: ~{msgs_tokens:>6} tokens (含 system prompt)")
    print(f"   ───")
    print(f"   合计:          ~{grand_total:>6} tokens  (你 log 里是 47867, 误差 ±20% 属于估算正常)")

    # ── 5. 建议 ─────────────────────────────────────────────────
    print("\n── 5. 最大省 token 点 ──")
    if not allowed:
        saved = eff_tools_tokens - tok("x" * 3500)  # ~6 工具约 3500 chars
        print(f"   ⭐ 设 allowed_tools 只留 5-8 个:  省 ~{saved} tokens/次")
    # L1 window vs max_context_messages
    l1_maxt = "未启用三层记忆,走 max_context_messages={}".format(max_ctx)
    try:
        from app.memory_config import MemoryConfig as _MC  # noqa
        l1_maxt = "见 memory_config"
    except Exception:
        pass
    print(f"   ⚙️ 消息裁剪当前策略: {l1_maxt}")
    if len(msgs) > 30:
        # if we'd trim to 20 turns ≈ 40 msgs
        kept = min(40, len(msgs))
        kept_chars = sum(len(m.get("content", "") if isinstance(m.get("content"), str)
                             else json.dumps(m.get("content"), ensure_ascii=False, default=str))
                         for m in msgs[-kept:])
        save2 = msgs_tokens - tok("x" * kept_chars)
        print(f"   ⭐ max_context_messages=50 → 40 或启 L3 压缩:  省 ~{save2} tokens/次")

    print()


if __name__ == "__main__":
    main()
