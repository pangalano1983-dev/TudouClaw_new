#!/usr/bin/env python3
"""
One-shot cleanup: remove test-leak trash from the shared knowledge
wiki and the domain KB registry.

What gets removed
-----------------
Shared Knowledge Wiki (~/.tudou_claw/shared_knowledge.json):
  - Entries whose title is in the known pytest-fixture set:
      {"Python style guide", "X", "Updated", "A", "B", "C"}
  - (Heuristic: these are the exact titles
    test_knowledge_router_audit.py and friends stamp. Real user
    entries don't use such short/generic titles.)

Domain Knowledge Bases (~/.tudou_claw/domain_knowledge_bases.json):
  - KBs whose name is in the known throwaway set:
      {"法律知识库", "A", "B", "T", "NT", "upload-test"}
  - Any KB with an empty / whitespace-only name.
  - Plus their backing ChromaDB collection (unless --keep-chroma).

The single real production KB — name="云技术服务知识库",
id=dkb_882418499d — is allow-listed and NEVER touched unless the
caller passes --i-really-mean-it.

Safety
------
Default is DRY-RUN (prints a plan, writes nothing). Pass --apply to
actually mutate. Always makes a .bak-<timestamp> of the JSON files
before writing.

Usage
-----
    python scripts/cleanup_trash_kb.py              # dry-run, see what would happen
    python scripts/cleanup_trash_kb.py --apply      # really do it
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path


# ── Config ───────────────────────────────────────────────────────

# pytest-fixture titles that leak into shared_knowledge.json when a
# test run doesn't properly isolate its data dir.
TEST_TITLES = {
    "Python style guide",
    "X",
    "Updated",
    "A", "B", "C",
}

# Throwaway domain-KB names that accumulate from UI testing.
TEST_KB_NAMES = {
    "法律知识库",
    "A", "B", "T", "NT",
    "upload-test",
}

# KBs that are NEVER touched. Extend here if the user has more
# real production KBs.
PROTECTED_KB_IDS = {
    "dkb_882418499d",   # 云技术服务知识库 — 7187 docs, real production
}


def _data_dir() -> Path:
    """Respect TUDOU_CLAW_DATA_DIR env override; fall back to default."""
    env = os.environ.get("TUDOU_CLAW_DATA_DIR", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return Path.home() / ".tudou_claw"


def _backup(path: Path) -> Path | None:
    """Copy to .bak-<ts> before mutating. Returns backup path."""
    if not path.exists():
        return None
    bak = path.with_suffix(path.suffix + f".bak-{int(time.time())}")
    shutil.copy2(path, bak)
    return bak


# ── Shared knowledge wiki ────────────────────────────────────────


def plan_shared_wiki(data_dir: Path) -> dict:
    """Return what we'd remove from shared_knowledge.json."""
    path = data_dir / "shared_knowledge.json"
    if not path.exists():
        return {"path": str(path), "missing": True, "remove": [], "keep": []}
    with open(path) as f:
        entries = json.load(f)
    if not isinstance(entries, list):
        return {"path": str(path), "error": "not a list", "remove": [], "keep": []}
    remove, keep = [], []
    for e in entries:
        title = (e.get("title") or "").strip()
        if title in TEST_TITLES:
            remove.append(e)
        else:
            keep.append(e)
    return {
        "path": str(path),
        "total": len(entries),
        "remove": remove,
        "keep": keep,
    }


def apply_shared_wiki(plan: dict) -> None:
    if plan.get("missing") or plan.get("error"):
        return
    path = Path(plan["path"])
    _backup(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(plan["keep"], f, ensure_ascii=False, indent=2)


# ── Domain KB registry ───────────────────────────────────────────


def plan_domain_kbs(data_dir: Path) -> dict:
    path = data_dir / "domain_knowledge_bases.json"
    if not path.exists():
        return {"path": str(path), "missing": True,
                "remove": [], "keep": []}
    with open(path) as f:
        data = json.load(f)
    kbs = data.get("knowledge_bases") if isinstance(data, dict) else data
    if not isinstance(kbs, list):
        return {"path": str(path), "error": "not a list",
                "remove": [], "keep": []}

    remove, keep = [], []
    for kb in kbs:
        kb_id = (kb.get("id") or "").strip()
        name  = (kb.get("name") or "").strip()
        # Always protect allow-listed ids.
        if kb_id in PROTECTED_KB_IDS:
            keep.append(kb)
            continue
        # Test-name or empty-name → remove.
        if not name or name in TEST_KB_NAMES:
            remove.append(kb)
        else:
            keep.append(kb)
    return {
        "path": str(path),
        "raw": data,
        "total": len(kbs),
        "remove": remove,
        "keep": keep,
    }


def apply_domain_kbs(plan: dict) -> None:
    if plan.get("missing") or plan.get("error"):
        return
    path = Path(plan["path"])
    _backup(path)
    data = plan["raw"]
    if isinstance(data, dict):
        data["knowledge_bases"] = plan["keep"]
        out = data
    else:
        out = plan["keep"]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


# ── ChromaDB collections ─────────────────────────────────────────


def _chroma_client(data_dir: Path):
    """Load the chroma client; returns None on any failure."""
    try:
        import chromadb  # noqa
    except ImportError:
        return None
    chroma_dir = data_dir / "chromadb"
    if not chroma_dir.is_dir():
        return None
    try:
        import chromadb
        return chromadb.PersistentClient(path=str(chroma_dir))
    except Exception:
        return None


def plan_chroma_cleanup(data_dir: Path, kept_kbs: list[dict],
                        purge_nonempty: bool = False) -> dict:
    """Plan Chroma collection deletions.

    A collection is an "orphan" if its name looks domain-KB-ish
    (``tudou_domain_dkb_*`` or ``domain_dkb_*``) but is NOT referenced
    by any KB in the current registry.

    SAFETY: by default we only delete **empty** orphans. A non-empty
    orphan means vector data exists for a KB whose registry record
    was deleted — this is usually user data that got detached (via a
    past bug / manual JSON edit) and is salvageable by re-registering.
    We list it but don't touch it unless ``purge_nonempty`` is True.
    """
    client = _chroma_client(data_dir)
    if client is None:
        return {"collections": [], "nonempty_kept": [],
                "reason": "chroma unavailable"}

    # Which collection names are explicitly kept (registry-referenced)
    kept_names: set[str] = set()
    for kb in kept_kbs:
        c = (kb.get("collection") or "").strip()
        if c:
            kept_names.add(c)
            # Chroma actually prefixes with "tudou_" on write; accept both
            kept_names.add(f"tudou_{c}")

    empty_orphans: list[str] = []
    nonempty_kept: list[tuple[str, int]] = []
    for c in client.list_collections():
        name = c.name
        # Only touch collections that look like domain-KB shells
        if not (name.startswith("tudou_domain_dkb_")
                or name.startswith("domain_dkb_")):
            continue
        if name in kept_names:
            continue
        try:
            cnt = c.count()
        except Exception:
            cnt = -1
        if cnt == 0:
            empty_orphans.append(name)
        else:
            nonempty_kept.append((name, cnt))

    to_delete = list(empty_orphans)
    if purge_nonempty:
        to_delete.extend(n for n, _ in nonempty_kept)
    return {
        "collections": to_delete,
        "empty_orphans": empty_orphans,
        "nonempty_kept": nonempty_kept,
    }


def apply_chroma_cleanup(data_dir: Path, collection_names: list[str]) -> dict:
    """Delete ChromaDB collections by name. Returns {deleted, failed}."""
    if not collection_names:
        return {"deleted": [], "failed": []}
    client = _chroma_client(data_dir)
    if client is None:
        return {"deleted": [],
                "failed": [(n, "chroma client unavailable")
                           for n in collection_names]}
    existing = {c.name for c in client.list_collections()}
    deleted, failed = [], []
    for name in collection_names:
        if name not in existing:
            continue
        try:
            client.delete_collection(name)
            deleted.append(name)
        except Exception as e:
            failed.append((name, str(e)))
    return {"deleted": deleted, "failed": failed}


# ── CLI ──────────────────────────────────────────────────────────


def _fmt_entry(e: dict) -> str:
    title = str(e.get("title") or "")[:50]
    tags = e.get("tags") or []
    return f"id={e.get('id','?')[:10]:10s} title={title!r} tags={tags}"


def _fmt_kb(kb: dict) -> str:
    return (f"id={kb.get('id','?'):20s} name={kb.get('name',''):30s}"
            f" docs={kb.get('doc_count', 0):5d} coll={kb.get('collection','')}")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--apply", action="store_true",
                   help="Actually mutate files. Default is dry-run.")
    p.add_argument("--keep-chroma", action="store_true",
                   help="Don't delete ANY ChromaDB collection.")
    p.add_argument("--purge-nonempty", action="store_true",
                   help="Also delete orphan chroma collections that still "
                        "contain vectors. DANGEROUS — these are usually "
                        "detached-but-real user data. Default is to list "
                        "them and let you decide.")
    args = p.parse_args()

    dd = _data_dir()
    print(f"# data_dir = {dd}")
    print(f"# mode     = {'APPLY (will write)' if args.apply else 'dry-run (no changes)'}")
    print()

    # ── Shared wiki ──
    sw = plan_shared_wiki(dd)
    print("══ Shared Knowledge Wiki ═══════════════════════════════")
    if sw.get("missing"):
        print(f"  (no file at {sw['path']})")
    elif sw.get("error"):
        print(f"  ERROR: {sw['error']}")
    else:
        print(f"  Total entries:      {sw['total']}")
        print(f"  Would REMOVE:       {len(sw['remove'])}")
        print(f"  Would KEEP:         {len(sw['keep'])}")
        if sw['remove']:
            print("  --- entries to remove ---")
            for e in sw['remove'][:10]:
                print(f"    {_fmt_entry(e)}")
            if len(sw['remove']) > 10:
                print(f"    ... and {len(sw['remove']) - 10} more")
        if sw['keep']:
            print("  --- entries to keep ---")
            for e in sw['keep']:
                print(f"    {_fmt_entry(e)}")
    print()

    # ── Domain KBs ──
    dk = plan_domain_kbs(dd)
    print("══ Domain Knowledge Bases ══════════════════════════════")
    if dk.get("missing"):
        print(f"  (no file at {dk['path']})")
    elif dk.get("error"):
        print(f"  ERROR: {dk['error']}")
    else:
        print(f"  Total KBs:          {dk['total']}")
        print(f"  Would REMOVE:       {len(dk['remove'])}")
        print(f"  Would KEEP:         {len(dk['keep'])}")
        if dk['remove']:
            print("  --- KBs to remove ---")
            for kb in dk['remove']:
                print(f"    {_fmt_kb(kb)}")
        if dk['keep']:
            print("  --- KBs to keep ---")
            for kb in dk['keep']:
                print(f"    {_fmt_kb(kb)}")
    print()

    # ── Chroma ──
    print("══ ChromaDB Collections ════════════════════════════════")
    cc = None
    if args.keep_chroma:
        print("  --keep-chroma set → no ChromaDB collections will be deleted")
    else:
        kept_kbs = dk['keep'] if not dk.get('missing') else []
        cc = plan_chroma_cleanup(dd, kept_kbs,
                                 purge_nonempty=args.purge_nonempty)
        if cc.get("reason"):
            print(f"  (skipped: {cc['reason']})")
        else:
            print(f"  Empty orphans (safe to delete): {len(cc['empty_orphans'])}")
            if cc['nonempty_kept']:
                print(f"  NON-empty orphans (preserved): {len(cc['nonempty_kept'])}")
                for name, cnt in cc['nonempty_kept'][:10]:
                    print(f"    ⚠ {cnt:5d} docs  {name}")
                if not args.purge_nonempty:
                    print("    (These hold real vector data. To purge them anyway "
                          "pass --purge-nonempty.")
                    print("     To recover one, add its id back to "
                          "domain_knowledge_bases.json.)")
            print(f"  Would DELETE {len(cc['collections'])} collection(s)")
    print()

    if not args.apply:
        print("──────────────────────────────────────────────────────────")
        print("DRY-RUN complete. Re-run with --apply to actually delete.")
        return 0

    # ── Execute ──
    print("──────────────────────────────────────────────────────────")
    print("Applying...")
    apply_shared_wiki(sw)
    print(f"  ✓ shared_knowledge.json — kept {len(sw['keep'])} entries")

    apply_domain_kbs(dk)
    print(f"  ✓ domain_knowledge_bases.json — kept {len(dk['keep'])} KBs")

    if not args.keep_chroma:
        # Reuse the plan we built above so we don't re-query Chroma.
        if cc is None:
            kept_kbs = dk['keep'] if not dk.get('missing') else []
            cc = plan_chroma_cleanup(dd, kept_kbs,
                                     purge_nonempty=args.purge_nonempty)
        res = apply_chroma_cleanup(dd, cc.get('collections', []))
        print(f"  ✓ chroma: deleted {len(res['deleted'])} empty orphan collection(s)")
        if cc.get('nonempty_kept') and not args.purge_nonempty:
            print(f"  ⚠ chroma: preserved {len(cc['nonempty_kept'])} non-empty orphan(s) "
                  "(run with --purge-nonempty to also drop these)")
        for n, err in res['failed']:
            print(f"  ✗ chroma collection failed:  {n}  ({err})")
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
