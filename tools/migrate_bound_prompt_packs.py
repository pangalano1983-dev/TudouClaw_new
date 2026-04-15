#!/usr/bin/env python3
"""
One-shot migration: rename `bound_skill_ids` → `bound_prompt_packs` in persisted
agent files.

Context:
  Phase 1-C renamed the SkillSystem subsystem to PromptEnhancer. The agent
  field `bound_skill_ids` (which always referred to prompt-pack bindings, not
  executable skill packages) was renamed to `bound_prompt_packs`.

  app/agent.py:from_dict() already reads both field names as a safety net, but
  this script proactively rewrites all on-disk agent JSON files so the old
  field is fully retired.

Scope:
  - ~/.tudou_claw/workspaces/agents.json
  - ~/.tudou_claw/workspaces/agents/<id>/agent.json
  - Any additional TUDOU_WORKSPACES_ROOT if env var set
  - SQLite agents table (if present): update the `agent_json` column

Usage:
  python tools/migrate_bound_prompt_packs.py              # dry-run
  python tools/migrate_bound_prompt_packs.py --apply      # do it
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path


def _default_workspaces_root() -> Path:
    env = os.environ.get("TUDOU_WORKSPACES_ROOT", "").strip()
    if env:
        return Path(env).expanduser()
    return Path.home() / ".tudou_claw" / "workspaces"


def _rewrite_json_file(path: Path, apply: bool) -> bool:
    """Return True if file needed rewriting."""
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"  [skip] {path}: read failed: {e}")
        return False

    changed = False

    def _walk(obj):
        nonlocal changed
        if isinstance(obj, dict):
            if "bound_skill_ids" in obj and "bound_prompt_packs" not in obj:
                obj["bound_prompt_packs"] = obj.pop("bound_skill_ids")
                changed = True
            elif "bound_skill_ids" in obj and "bound_prompt_packs" in obj:
                obj.pop("bound_skill_ids")
                changed = True
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for v in obj:
                _walk(v)

    _walk(data)

    if changed and apply:
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(path)
    return changed


def _rewrite_sqlite(db_path: Path, apply: bool) -> int:
    if not db_path.exists():
        return 0
    try:
        conn = sqlite3.connect(str(db_path))
    except Exception as e:
        print(f"  [skip] sqlite {db_path}: {e}")
        return 0
    touched = 0
    try:
        cur = conn.cursor()
        # check schema: table `agents` with column `agent_json`
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='agents'")
        if not cur.fetchone():
            return 0
        cur.execute("PRAGMA table_info(agents)")
        cols = [r[1] for r in cur.fetchall()]
        if "agent_json" not in cols:
            return 0
        cur.execute("SELECT id, agent_json FROM agents")
        rows = cur.fetchall()
        for row_id, raw in rows:
            if not raw or "bound_skill_ids" not in raw:
                continue
            try:
                obj = json.loads(raw)
            except Exception:
                continue
            dirty = False
            if isinstance(obj, dict):
                if "bound_skill_ids" in obj and "bound_prompt_packs" not in obj:
                    obj["bound_prompt_packs"] = obj.pop("bound_skill_ids")
                    dirty = True
                elif "bound_skill_ids" in obj:
                    obj.pop("bound_skill_ids")
                    dirty = True
            if dirty:
                touched += 1
                if apply:
                    new_raw = json.dumps(obj, ensure_ascii=False)
                    cur.execute("UPDATE agents SET agent_json=? WHERE id=?", (new_raw, row_id))
        if apply:
            conn.commit()
    finally:
        conn.close()
    return touched


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="actually write changes (default: dry-run)")
    ap.add_argument("--root", type=str, default="",
                    help="workspaces root (default: ~/.tudou_claw/workspaces)")
    args = ap.parse_args()

    root = Path(args.root).expanduser() if args.root else _default_workspaces_root()
    if not root.exists():
        print(f"workspaces root not found: {root}")
        return 1

    print(f"scanning: {root}  (apply={args.apply})")

    touched_json = 0
    # top-level agents.json
    top = root / "agents.json"
    if top.exists():
        if _rewrite_json_file(top, args.apply):
            touched_json += 1
            print(f"  [{'apply' if args.apply else 'dry '}] {top}")

    # per-agent agent.json
    agents_dir = root / "agents"
    if agents_dir.is_dir():
        for sub in agents_dir.iterdir():
            aj = sub / "agent.json"
            if aj.exists():
                if _rewrite_json_file(aj, args.apply):
                    touched_json += 1
                    print(f"  [{'apply' if args.apply else 'dry '}] {aj}")

    # sqlite
    touched_sql = 0
    for candidate in [root / "tudou.db", root / "hub.db", root / "agents.db"]:
        n = _rewrite_sqlite(candidate, args.apply)
        if n:
            touched_sql += n
            print(f"  [{'apply' if args.apply else 'dry '}] sqlite {candidate}: {n} rows")

    print()
    print(f"summary: json files touched={touched_json}  sqlite rows touched={touched_sql}")
    if not args.apply and (touched_json or touched_sql):
        print("re-run with --apply to write changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
