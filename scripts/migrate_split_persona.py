"""Split each agent's persona text into two semantic fields.

Background
----------
Audit (2026-04-25) found that 4 of 5 production agents had identical
``system_prompt`` and ``soul_md`` text. After the system_prompt.py
refactor, these two fields have distinct jobs:

  system_prompt   — Identity & Expertise (what the agent does, the
                    rules of its profession).
  soul_md         — Communication & Behavior (how it speaks, tone,
                    mannerisms).

This script walks every agent in ``~/.tudou_claw/agents.json`` whose
two fields are byte-equal, asks the configured LLM to split the
unified text into the two semantic halves, and writes the split back.

Run modes
---------
``--dry-run``   (default): print the split for human review, do NOT save.
``--execute``  : write the split back to agents.json + SQLite.
``--agent ID`` : limit to one agent id (prefix match) for spot test.

Always backs up agents.json before writing.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

# Make app modules importable when run as a script
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
sys.path.insert(0, str(_ROOT))


SPLIT_PROMPT = """\
你是文档结构分析助手。任务: 把下面的 agent persona markdown 拆分成两段。

**system_prompt** 段 — 专业身份 / 角色 / 专业规则:
  - 这个 agent 是谁、做什么、专业领域
  - 写作 / 分析 / 编码等领域的硬性规则
  - 知识深度 / 能力边界声明

**soul_md** 段 — 沟通风格 / 行为方式:
  - 语气、口头禅、性格特征
  - 沟通节奏、回复结构偏好
  - 互动方式

规则:
1. 只能用原文里的句子。**不要新增内容,不要改写。**
2. 内容只能各属一段,不能两段都有。
3. 都属于"身份"的内容统一进 system_prompt。
4. 没有明显沟通风格描述时,soul_md 留空字符串。
5. 输出严格的 JSON: {"system_prompt": "...", "soul_md": "..."}
6. 不要 markdown fence,不要任何额外文字。

待拆分原文:
---
{TEXT}
---
"""


def _load_agents_json(path: Path) -> tuple[dict | list, list]:
    """Return (raw_data, agents_list). Schema: list at top level OR
    {"agents": [...]}. Returns the same shape for save."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data, data
    if isinstance(data, dict) and isinstance(data.get("agents"), list):
        return data, data["agents"]
    raise ValueError(f"Unexpected agents.json shape: {type(data)}")


def _save_agents_json(path: Path, raw_data: dict | list) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(raw_data, f, ensure_ascii=False, indent=2)


def _llm_split(text: str) -> tuple[str, str]:
    """Ask LLM to split. Returns (system_prompt, soul_md)."""
    from app import llm
    cfg = llm.get_config()
    prov = cfg.get("provider", "")
    mdl = cfg.get("model", "")
    if not prov or not mdl:
        # config has no global default — pick the first enabled provider
        reg = llm.get_registry()
        providers = [p for p in reg.list_all() if p.enabled]
        if not providers:
            raise RuntimeError("No enabled LLM provider found.")
        prov = providers[0].id
        mdl = (providers[0].manual_models or providers[0].models_cache or [""])[0]
        if not mdl:
            raise RuntimeError(f"Provider '{prov}' has no model.")

    prompt = SPLIT_PROMPT.replace("{TEXT}", text)
    resp = llm.chat_no_stream(
        messages=[{"role": "user", "content": prompt}],
        provider=prov, model=mdl,
    )
    raw = ""
    if isinstance(resp, dict):
        m = resp.get("message") or resp
        if isinstance(m, dict):
            raw = str(m.get("content") or "")
    if not raw:
        raise RuntimeError(f"Empty LLM response: {resp!r}")

    # Strip code fences if any
    raw = raw.strip()
    if raw.startswith("```"):
        # remove the first fence line
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # try to extract the first {...} block
        import re
        m = re.search(r"\{[\s\S]+\}", raw)
        if not m:
            raise RuntimeError(f"Could not parse JSON from LLM: {raw[:200]!r}")
        parsed = json.loads(m.group(0))

    sp = str(parsed.get("system_prompt") or "").strip()
    sm = str(parsed.get("soul_md") or "").strip()
    return sp, sm


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--execute", action="store_true",
                    help="Write the split back to agents.json (default: dry-run).")
    ap.add_argument("--agent", default="",
                    help="Limit to agent id prefix.")
    ap.add_argument("--data-dir", default=os.path.expanduser("~/.tudou_claw"),
                    help="Override agents.json directory.")
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    agents_path = data_dir / "agents.json"
    if not agents_path.exists():
        print(f"[error] agents.json not found at {agents_path}")
        return 2

    raw_data, agents = _load_agents_json(agents_path)
    candidates: list[dict] = []
    for a in agents:
        if not isinstance(a, dict):
            continue
        if args.agent and not str(a.get("id", "")).startswith(args.agent):
            continue
        sp = (a.get("system_prompt") or "").strip()
        sm = (a.get("soul_md") or "").strip()
        if sp and sm and sp == sm:
            candidates.append(a)

    if not candidates:
        print("[info] no agents match (sp == sm) — nothing to migrate.")
        return 0

    print(f"[info] {len(candidates)} agent(s) need splitting:")
    for a in candidates:
        print(f"   - {a.get('id', '?')[:8]}  {a.get('name', '?')}  "
              f"sp_len={len(a.get('system_prompt') or '')}")
    print()

    # Process each
    changes: list[tuple[dict, str, str]] = []
    for a in candidates:
        text = a.get("system_prompt") or ""
        print(f"\n=== {a.get('name','?')} ({a.get('id','?')[:8]}) ===")
        print(f"original  ({len(text)} chars):")
        print(f"  {text[:300]}{'…' if len(text) > 300 else ''}")
        try:
            new_sp, new_sm = _llm_split(text)
        except Exception as e:
            print(f"  [skip] LLM split failed: {e}")
            continue

        print(f"\nsystem_prompt  ({len(new_sp)} chars):")
        print(f"  {new_sp[:400]}{'…' if len(new_sp) > 400 else ''}")
        print(f"\nsoul_md       ({len(new_sm)} chars):")
        print(f"  {new_sm[:400]}{'…' if len(new_sm) > 400 else ''}")
        # Sanity: combined length shouldn't shrink dramatically (LLM
        # might have dropped content). Warn if total < 80% of original.
        if (len(new_sp) + len(new_sm)) < int(len(text) * 0.8):
            print(f"  [warn] split total {len(new_sp)+len(new_sm)} chars "
                   f"is < 80% of original {len(text)}; LLM may have dropped "
                   f"content — review carefully.")
        changes.append((a, new_sp, new_sm))

    if not args.execute:
        print(f"\n[dry-run] would update {len(changes)} agent(s). "
              f"Run with --execute to commit.")
        return 0

    # Backup before writing
    backup_path = agents_path.with_suffix(
        f".bak-split_persona-{int(time.time())}")
    shutil.copy2(agents_path, backup_path)
    print(f"\n[backup] {backup_path}")

    for a, new_sp, new_sm in changes:
        a["system_prompt"] = new_sp
        a["soul_md"] = new_sm

    _save_agents_json(agents_path, raw_data)
    print(f"[saved] {len(changes)} agent(s) updated in {agents_path}")
    print("[note] SQLite mirror will sync on next portal restart "
          "(Hub._save_agents writes both stores).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
