#!/usr/bin/env python3
"""One-shot migration: stamp owner_id on every existing agent.

Context
-------
Before the permissions overhaul, Agent had no owner_id field. Every
admin could see and manage every agent. The new permission model
(see app/permissions.py) requires owner_id to scope MANAGE_AGENT.
This script fills in the missing field for existing data.

Policy
------
Default: assign every agent without an owner_id to the sole
superAdmin user in the admin manager. Rationale:
  - Keeps current admin's effective access unchanged.
  - Safe: superAdmin's implicit "own everything" applies anyway, but
    explicit ownership records are needed so the *next* admin /
    user can be granted delegation cleanly.
  - If multiple superAdmins exist → pick the first one created.

Safety
------
DRY-RUN by default — prints a plan, touches nothing. Pass --apply
to write. Always makes a .bak-<ts> of agents.json before mutating.

Usage
-----
    python scripts/migrate_agent_ownership.py              # dry-run
    python scripts/migrate_agent_ownership.py --apply      # really update
    python scripts/migrate_agent_ownership.py --apply --owner <user_id>
                                                           # force specific owner
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path


def _data_dir() -> Path:
    env = os.environ.get("TUDOU_CLAW_DATA_DIR", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return Path.home() / ".tudou_claw"


def _find_super_admin_id(data_dir: Path) -> str:
    """Load the admins file and pick the first superAdmin user_id."""
    admins_file = data_dir / ".tudou_admins.json"
    if not admins_file.exists():
        return ""
    try:
        with open(admins_file) as f:
            admins = json.load(f) or []
    except Exception:
        return ""
    if not isinstance(admins, list):
        return ""
    # Prefer earliest-created superAdmin (stable pick across runs)
    supers = [a for a in admins
              if isinstance(a, dict) and a.get("role") == "superAdmin"
              and a.get("active", True)]
    if not supers:
        return ""
    supers.sort(key=lambda a: a.get("created_at", 0))
    return str(supers[0].get("user_id") or "")


def _load_agents(data_dir: Path) -> tuple[Path, dict]:
    path = data_dir / "agents.json"
    if not path.exists():
        return path, {}
    with open(path) as f:
        raw = json.load(f)
    return path, raw


def _iter_agents(raw):
    """Yield (container, index_or_key, agent_dict) so caller can mutate.

    agents.json shape is a top-level {"agents": [ {...}, {...} ]} or
    occasionally a flat list. Handle both.
    """
    if isinstance(raw, dict) and isinstance(raw.get("agents"), list):
        for i, a in enumerate(raw["agents"]):
            yield raw["agents"], i, a
    elif isinstance(raw, list):
        for i, a in enumerate(raw):
            yield raw, i, a


def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--apply", action="store_true",
                   help="Actually mutate agents.json. Default is dry-run.")
    p.add_argument("--owner",
                   help="Force a specific user_id as owner (otherwise "
                        "auto-picks first superAdmin).")
    args = p.parse_args()

    dd = _data_dir()
    print(f"# data_dir = {dd}")
    print(f"# mode     = {'APPLY' if args.apply else 'dry-run'}")

    owner_id = args.owner or _find_super_admin_id(dd)
    if not owner_id:
        print("ERROR: could not find any superAdmin in .tudou_admins.json")
        print("       Pass --owner <user_id> explicitly if you want to "
              "proceed.")
        return 2

    print(f"# owner   = {owner_id}")
    print()

    path, raw = _load_agents(dd)
    if not raw:
        print(f"(no agents file at {path})")
        return 0

    have_owner = 0
    missing_owner = []
    for _container, _idx, agent in _iter_agents(raw):
        if not isinstance(agent, dict):
            continue
        aid = agent.get("id", "?")
        name = agent.get("name", "?")
        oid = (agent.get("owner_id") or "").strip()
        if oid:
            have_owner += 1
        else:
            missing_owner.append((aid, name))

    total = have_owner + len(missing_owner)
    print(f"Agents total: {total}")
    print(f"  already own: {have_owner}")
    print(f"  need stamp:  {len(missing_owner)}")
    if missing_owner:
        print("\n  Will assign owner_id to:")
        for aid, name in missing_owner[:20]:
            print(f"    {aid:14s} {name}")
        if len(missing_owner) > 20:
            print(f"    ... and {len(missing_owner) - 20} more")

    if not args.apply:
        print("\nDRY-RUN complete. Re-run with --apply to write.")
        return 0

    if not missing_owner:
        print("\nNothing to do.")
        return 0

    # Backup
    bak = path.with_suffix(path.suffix + f".bak-{int(time.time())}")
    shutil.copy2(path, bak)
    print(f"\nBackup: {bak}")

    # Mutate in place
    for _container, _idx, agent in _iter_agents(raw):
        if not isinstance(agent, dict):
            continue
        if not (agent.get("owner_id") or "").strip():
            agent["owner_id"] = owner_id

    with open(path, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)
    print(f"Wrote {path}")
    print(f"Stamped owner_id={owner_id} on {len(missing_owner)} agent(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
