#!/usr/bin/env python3
"""
migrate_workspaces.py — 一键把所有 TudouClaw agent 的 workspace 搬回标准布局。

标准布局 (来自 app/__init__.py 注释)：
    $DATA_DIR/workspaces/agents/{agent_id}/workspace/

做了什么：
  1. 从 SQLite (~/.tudou_claw/tudou_claw.db 的 agents 表) + agents.json 双向
     读取所有 agent，过滤出 working_dir 不在标准位置的那些。
  2. 把每个偏离 agent 的整个 working_dir 目录 `shutil.move` 到标准位置。
  3. 把 SQLite / agents.json / per-agent `workspaces/{id}/agent.json` 里的
     `working_dir` 字段全部清空，让下次启动时走默认解析。
  4. 扫一遍代码仓库 (cwd) 找 "孤儿 workspace"（有 Project.md 且 header 里带
     "Agent: XXX" 但不匹配任何已知 agent），只报告、不动。

安全措施：
  * 默认 dry-run。要真改必须加 --apply。
  * 改 sqlite/json 之前先备份成 `<file>.premigration-<timestamp>`。
  * 目标目录已存在且非空 → SKIP（不覆盖）。目标为空 → 删掉再 rename。
  * 跑之前先检查 :9090 是不是还在监听；是的话打印警告。
  * 永远不 `rm -rf`。任何无法完成的迁移都会写进最终的 Skipped 列表里。

用法：
    # 0. 停掉 TudouClaw 服务
    # 1. 先预览 (不会改任何东西)
    python tools/migrate_workspaces.py

    # 2. 加上 --scan 也扫一遍当前目录找孤儿 workspace
    python tools/migrate_workspaces.py --scan

    # 3. 确认计划 OK 之后真跑
    python tools/migrate_workspaces.py --apply

    # 自定义数据根：
    TUDOU_CLAW_DATA_DIR=/data/tudou_claw python tools/migrate_workspaces.py
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import sqlite3
import sys
import time
from pathlib import Path

# ─────────────────────────── 配置 ───────────────────────────
DATA_DIR = Path(os.environ.get("TUDOU_CLAW_DATA_DIR")
                or os.path.expanduser("~/.tudou_claw")).resolve()
DB_PATH = DATA_DIR / "tudou_claw.db"
AGENTS_JSON = DATA_DIR / "agents.json"
WORKSPACES_ROOT = DATA_DIR / "workspaces"
STD_AGENTS_ROOT = WORKSPACES_ROOT / "agents"
TS = time.strftime("%Y%m%d-%H%M%S")


# ─────────────────────────── 工具函数 ───────────────────────────
def check_server_stopped(port: int = 9090) -> None:
    """如果服务还在跑，只警告不拦截。"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                print(f"\n⚠  端口 {port} 还在监听 —— 请先停掉 TudouClaw 服务再 --apply。\n")
    except Exception:
        pass


def standard_workspace_for(agent_id: str) -> Path:
    return (STD_AGENTS_ROOT / agent_id / "workspace").resolve()


def is_already_standard(wd: str, agent_id: str) -> bool:
    if not wd:
        return True  # 空串 = 用默认 = 已经在标准位置
    try:
        return Path(wd).resolve() == standard_workspace_for(agent_id)
    except Exception:
        return False


def backup_file(path: Path) -> Path | None:
    if not path.is_file():
        return None
    bak = path.with_name(path.name + f".premigration-{TS}")
    shutil.copy2(str(path), str(bak))
    return bak


# ─────────────────────── 读取 agent 列表 ───────────────────────
def load_agents_from_db() -> list[dict]:
    if not DB_PATH.is_file():
        return []
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.cursor()
        try:
            cur.execute("SELECT agent_id, name, role, data FROM agents")
        except sqlite3.OperationalError:
            return []
        out = []
        for aid, name, role, data in cur.fetchall():
            try:
                d = json.loads(data) if data else {}
            except Exception:
                d = {}
            out.append({
                "id": aid,
                "name": name or d.get("name", ""),
                "role": role or d.get("role", ""),
                "working_dir": (d.get("working_dir") or "").strip(),
                "source": "sqlite",
            })
        return out
    finally:
        conn.close()


def load_agents_from_json() -> list[dict]:
    if not AGENTS_JSON.is_file():
        return []
    try:
        with open(AGENTS_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"WARN: 读取 {AGENTS_JSON} 失败: {e}")
        return []
    raw = data.get("agents", []) if isinstance(data, dict) else []
    out = []
    for a in raw:
        out.append({
            "id": a.get("id", ""),
            "name": a.get("name", ""),
            "role": a.get("role", ""),
            "working_dir": (a.get("working_dir") or "").strip(),
            "source": "json",
        })
    return out


def merge_agent_lists(*lists: list[dict]) -> list[dict]:
    """以 id 为 key 合并多来源的 agent 列表，sqlite 优先。"""
    merged: dict[str, dict] = {}
    for src in lists:
        for a in src:
            if not a.get("id"):
                continue
            if a["id"] not in merged:
                merged[a["id"]] = a
    return list(merged.values())


# ─────────────────────── 迁移计划 ───────────────────────
def plan_migration(agents: list[dict]) -> list[tuple[dict, Path, Path]]:
    plan = []
    for a in agents:
        wd = a["working_dir"]
        if is_already_standard(wd, a["id"]):
            continue
        if not wd:
            continue
        try:
            src = Path(wd).resolve()
        except Exception:
            src = Path(wd)
        dst = standard_workspace_for(a["id"])
        plan.append((a, src, dst))
    return plan


def do_move(src: Path, dst: Path) -> tuple[bool, str]:
    if not src.exists():
        return False, f"source missing: {src}"
    if not src.is_dir():
        return False, f"source is not a directory: {src}"
    if dst.exists():
        try:
            if dst.is_dir() and not any(dst.iterdir()):
                dst.rmdir()
            else:
                return False, f"target exists and is non-empty: {dst}"
        except Exception as e:
            return False, f"target inspect failed: {e}"
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(src), str(dst))
        return True, "moved"
    except Exception as e:
        return False, f"move failed: {e}"


# ──────────── 清掉 working_dir 字段（三处都要改） ────────────
def clear_db_working_dir(ids: list[str]) -> int:
    if not DB_PATH.is_file() or not ids:
        return 0
    backup_file(DB_PATH)
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.cursor()
        cur.execute("BEGIN")
        n = 0
        for aid in ids:
            cur.execute("SELECT data FROM agents WHERE agent_id = ?", (aid,))
            row = cur.fetchone()
            if not row or not row[0]:
                continue
            try:
                d = json.loads(row[0])
            except Exception:
                continue
            if d.get("working_dir"):
                d["working_dir"] = ""
                cur.execute(
                    "UPDATE agents SET data = ? WHERE agent_id = ?",
                    (json.dumps(d, ensure_ascii=False), aid))
                n += 1
        conn.commit()
        return n
    except Exception as e:
        conn.rollback()
        print(f"DB update error: {e}")
        return 0
    finally:
        conn.close()


def clear_json_working_dir(ids: list[str]) -> int:
    if not AGENTS_JSON.is_file() or not ids:
        return 0
    backup_file(AGENTS_JSON)
    try:
        with open(AGENTS_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"agents.json read error: {e}")
        return 0
    agents = data.get("agents", []) if isinstance(data, dict) else []
    id_set = set(ids)
    n = 0
    for a in agents:
        if a.get("id") in id_set and a.get("working_dir"):
            a["working_dir"] = ""
            n += 1
    if n:
        try:
            with open(AGENTS_JSON, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"agents.json write error: {e}")
            return 0
    return n


def clear_per_agent_json_working_dir(ids: list[str]) -> int:
    """hub._save_agent_workspace 会把 agent 存到 workspaces/{id}/agent.json。"""
    n = 0
    for aid in ids:
        p = WORKSPACES_ROOT / aid / "agent.json"
        if not p.is_file():
            continue
        backup_file(p)
        try:
            with open(p, "r", encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            continue
        if d.get("working_dir"):
            d["working_dir"] = ""
            try:
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(d, f, ensure_ascii=False, indent=2)
                n += 1
            except Exception:
                pass
    return n


# ─────────────────── 孤儿 workspace 扫描 ───────────────────
def scan_orphan_workspaces(known_srcs: set[Path], scan_root: Path):
    """找 cwd 下所有含 Project.md (且 header 里写了 "Agent: XXX") 的目录。
    排除已经在标准布局下的、以及已经在本次迁移计划里的。"""
    if not scan_root.is_dir():
        return
    std_root = STD_AGENTS_ROOT.resolve()
    for p in scan_root.rglob("Project.md"):
        try:
            parent = p.parent.resolve()
        except Exception:
            continue
        # skip anything already under standard layout
        try:
            if parent == std_root or str(parent).startswith(str(std_root) + os.sep):
                continue
        except Exception:
            pass
        if parent in known_srcs:
            continue
        try:
            head = p.read_text(encoding="utf-8", errors="replace")[:200]
        except Exception:
            continue
        if "Agent:" not in head:
            continue
        try:
            name = head.split("Agent:", 1)[1].split("\n", 1)[0].strip()
        except Exception:
            name = "?"
        yield parent, name


# ─────────────────────── main ───────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(
        description="Migrate all TudouClaw agent workspaces to standard layout.")
    ap.add_argument("--apply", action="store_true",
                    help="真的执行迁移+修改 DB/JSON（默认是 dry-run 预览）")
    ap.add_argument("--config-only", action="store_true",
                    help="只清理 DB/JSON 里的 working_dir 字段，不搬任何文件。"
                         "适用于漂移目录里都是临时文件、不在乎丢失的情况。")
    ap.add_argument("--scan", action="store_true",
                    help="同时在当前目录下扫一遍孤儿 workspace (Project.md + Agent:)")
    ap.add_argument("--scan-root", default=".",
                    help="--scan 的根目录 (默认 .)")
    args = ap.parse_args()

    print("╭──────────────────────────────────────────────╮")
    print("│  TudouClaw workspace migration               │")
    print("╰──────────────────────────────────────────────╯")
    print(f"DATA_DIR       : {DATA_DIR}")
    print(f"DB             : {DB_PATH}  {'[ok]' if DB_PATH.is_file() else '[missing]'}")
    print(f"agents.json    : {AGENTS_JSON}  {'[ok]' if AGENTS_JSON.is_file() else '[missing]'}")
    print(f"standard root  : {STD_AGENTS_ROOT}")
    mode_bits = []
    mode_bits.append("APPLY (真跑)" if args.apply else "dry-run (预览)")
    if args.config_only:
        mode_bits.append("config-only (只改配置，不搬文件)")
    print(f"mode           : {'  '.join(mode_bits)}")

    if args.apply:
        check_server_stopped()

    agents = merge_agent_lists(load_agents_from_db(), load_agents_from_json())
    if not agents:
        print("\n没有从 SQLite 或 agents.json 里加载到任何 agent。")
        print("请检查 DATA_DIR 是否正确（或设置 TUDOU_CLAW_DATA_DIR）。")
        return 1

    print(f"\n加载到 {len(agents)} 个 agent：")
    for a in agents:
        state = "standard" if is_already_standard(a["working_dir"], a["id"]) else "NON-STANDARD"
        wd_disp = a["working_dir"] or "(default)"
        print(f"  {a['id']}  {a['name']:<16}  [{state}]  wd={wd_disp}")

    plan = plan_migration(agents)

    if not plan:
        print("\n✓ 所有 agent 都已经在标准布局下，没有需要迁移的。")
    elif args.config_only:
        # ── config-only：不搬文件，只把三处存储里的 working_dir 清空 ──
        print(f"\n=== config-only 计划（{len(plan)} 个 agent 需要清 working_dir）===")
        ok_ids: list[str] = []
        for a, src, dst in plan:
            print(f"\n[{a['name']} / {a['id']}]")
            print(f"  old working_dir : {src}")
            print(f"  will resolve to : {dst}  (下次启动时按默认解析)")
            print(f"  旧目录会保留原位，里面的文件你自行决定删除或保留。")
            ok_ids.append(a["id"])
            if not args.apply:
                print("  → (dry-run, 跳过)")

        if args.apply and ok_ids:
            n1 = clear_db_working_dir(ok_ids)
            n2 = clear_json_working_dir(ok_ids)
            n3 = clear_per_agent_json_working_dir(ok_ids)
            print(f"\n已清空 working_dir: sqlite={n1}  agents.json={n2}  per-agent.json={n3}")
            print("注意：这些 agent 下次启动时会在标准位置新建空 workspace。")
            print("      如果对应的标准目录已经有内容（之前跑过），会直接复用。")
    else:
        print(f"\n=== 迁移计划（{len(plan)} 个 agent 需要搬家）===")
        ok_ids: list[str] = []
        skipped: list[tuple[dict, str]] = []
        for a, src, dst in plan:
            print(f"\n[{a['name']} / {a['id']}]")
            print(f"  src: {src}")
            print(f"  dst: {dst}")
            if not args.apply:
                print("  → (dry-run, 跳过)")
                continue
            ok, msg = do_move(src, dst)
            if ok:
                print(f"  ✓ {msg}")
                ok_ids.append(a["id"])
            else:
                print(f"  ✗ SKIP: {msg}")
                skipped.append((a, msg))

        if args.apply and ok_ids:
            n1 = clear_db_working_dir(ok_ids)
            n2 = clear_json_working_dir(ok_ids)
            n3 = clear_per_agent_json_working_dir(ok_ids)
            print(f"\n已清空 working_dir: sqlite={n1}  agents.json={n2}  per-agent.json={n3}")

        if skipped:
            print("\n⚠ 以下 agent 跳过了，需要手动处理：")
            for a, msg in skipped:
                print(f"  - {a['name']} ({a['id']}): {msg}")
            print("\n  如果这些 agent 漂移目录里都是临时文件，可以改用：")
            print("    python tools/migrate_workspaces.py --config-only --apply")

    # ── 扫一遍孤儿 workspace ──
    if args.scan:
        print("\n=== 孤儿 workspace 扫描 ===")
        known = set()
        for a in agents:
            if a["working_dir"]:
                try:
                    known.add(Path(a["working_dir"]).resolve())
                except Exception:
                    pass
        scan_root = Path(args.scan_root).resolve()
        print(f"scan root: {scan_root}")
        orphans = list(scan_orphan_workspaces(known, scan_root))
        if not orphans:
            print("  (没找到)")
        else:
            for p, name in orphans:
                print(f"  • {p}  (Agent header: {name})")
            print("\n  这些目录里有 Project.md 但不属于任何已知 agent 的 working_dir。")
            print("  如果是以前的残留，手动确认内容后删除；")
            print("  如果对应某个 agent，把 agent 的 working_dir 改成这个路径后再跑一次本脚本。")

    if not args.apply:
        print("\n→ 预览完成。确认无误后加 --apply 真正执行迁移。")
        return 0
    print("\n→ 迁移完成。启动 TudouClaw 服务并用任一 agent 测试一下即可。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
