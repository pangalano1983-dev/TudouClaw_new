"""
Skill Category Registry — admin-defined two-dimensional taxonomy for the
skill store.

Why this exists
===============

Plain `tags` (free-text strings on each SKILL.md) don't give the store a
clean filter axis: every skill author writes their own variants ("PPT" vs
"pptx" vs "slides"), and operators want a stable controlled vocabulary
they can curate as the catalog grows.

This module introduces a **two-dimension category dictionary** that admins
manage explicitly:

  • **scenarios** — what business job the skill does
    e.g. design / report / data / office / marketing / research / ...

  • **agent_types** — which agent role typically uses it
    e.g. general / researcher / coder / designer / marketer / ...

Each skill in the store can be tagged with **0..N** category ids on each
dimension. The store UI then exposes filter chips for both dimensions
that the user can combine.

Data layout
===========

Persistence: `~/.tudou_claw/skill_categories.json`

```
{
  "version": 1,
  "updated_at": 1714521600.0,
  "dimensions": {
    "scenarios": [
      {"id": "design",     "name": "设计制作", "icon": "🎨", "order": 1},
      {"id": "report",     "name": "报告写作", "icon": "📝", "order": 2},
      ...
    ],
    "agent_types": [
      {"id": "general",    "name": "通用助手", "icon": "🤖", "order": 1},
      ...
    ]
  }
}
```

Skill → category mapping is stored separately in the per-skill
`SkillCatalogEntry` (`category_scenarios`, `category_agent_types` lists),
so the registry stays the single source of truth for "what categories
exist", and per-skill assignments live alongside the skill itself.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

logger = logging.getLogger("tudou.skill_categories")


# ─────────────────────────────────────────────────────────────
# Constants — the two dimensions admins curate
# ─────────────────────────────────────────────────────────────

DIMENSIONS = ("scenarios", "agent_types")


# Seed values used when the categories file doesn't exist yet. Admins can
# edit / delete / reorder freely after the first launch — these are just
# a reasonable starting point so a fresh install isn't an empty form.
_SEED_SCENARIOS = [
    {"id": "design",        "name": "设计制作",   "icon": "🎨", "order": 1},
    {"id": "report",        "name": "报告写作",   "icon": "📝", "order": 2},
    {"id": "data",          "name": "数据分析",   "icon": "📊", "order": 3},
    {"id": "office",        "name": "办公自动化", "icon": "💼", "order": 4},
    {"id": "marketing",     "name": "营销推广",   "icon": "📣", "order": 5},
    {"id": "research",      "name": "研究调研",   "icon": "🔬", "order": 6},
    {"id": "coding",        "name": "编程开发",   "icon": "💻", "order": 7},
    {"id": "communication", "name": "沟通协作",   "icon": "💬", "order": 8},
]

_SEED_AGENT_TYPES = [
    {"id": "general",    "name": "通用助手",     "icon": "🤖", "order": 1},
    {"id": "researcher", "name": "研究员",       "icon": "🔬", "order": 2},
    {"id": "coder",      "name": "编码工程师",   "icon": "💻", "order": 3},
    {"id": "designer",   "name": "设计师",       "icon": "🎨", "order": 4},
    {"id": "marketer",   "name": "营销专家",     "icon": "📣", "order": 5},
    {"id": "analyst",    "name": "数据分析师",   "icon": "📊", "order": 6},
    {"id": "writer",     "name": "文案/编辑",    "icon": "✍️", "order": 7},
    {"id": "ops",        "name": "运营/办公",    "icon": "💼", "order": 8},
]


# ─────────────────────────────────────────────────────────────
# Dataclass — single category entry
# ─────────────────────────────────────────────────────────────

@dataclass
class SkillCategory:
    """One row in either dimension. `id` is the stable handle that skills
    reference; `name` and `icon` are display-only and can change without
    breaking existing skill assignments."""
    id: str = ""
    name: str = ""
    icon: str = ""
    order: int = 0           # display order — lower first
    description: str = ""    # optional admin note

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "icon": self.icon,
            "order": self.order, "description": self.description,
        }

    @staticmethod
    def from_dict(d: dict) -> "SkillCategory":
        return SkillCategory(
            id=str(d.get("id", "")),
            name=str(d.get("name", "")),
            icon=str(d.get("icon", "")),
            order=int(d.get("order", 0) or 0),
            description=str(d.get("description", "")),
        )


# ─────────────────────────────────────────────────────────────
# Store — load / save / mutate the JSON registry
# ─────────────────────────────────────────────────────────────

class CategoryStore:
    """Thread-safe persistent store for skill categories. One JSON file,
    two dimensions. Admin-only operations are guarded at the API layer;
    this class itself just enforces structural invariants (unique id per
    dimension, dimension whitelist)."""

    def __init__(self, file_path: str | Path):
        self.file_path = Path(file_path)
        self._lock = threading.Lock()
        # In-memory: {"scenarios": [SkillCategory, ...], "agent_types": [...]}
        self._data: dict[str, list[SkillCategory]] = {dim: [] for dim in DIMENSIONS}
        self._load_or_seed()

    # ── Persistence ───────────────────────────────────────

    def _load_or_seed(self) -> None:
        with self._lock:
            if self.file_path.exists():
                try:
                    raw = json.loads(self.file_path.read_text(encoding="utf-8"))
                    dims = raw.get("dimensions") or {}
                    for dim in DIMENSIONS:
                        items = dims.get(dim) or []
                        self._data[dim] = [SkillCategory.from_dict(d) for d in items
                                           if isinstance(d, dict) and d.get("id")]
                    logger.info("loaded %d scenarios + %d agent_types from %s",
                                len(self._data["scenarios"]),
                                len(self._data["agent_types"]),
                                self.file_path)
                    return
                except Exception as e:
                    logger.warning("failed to load %s (%s); reseeding", self.file_path, e)
            # Seed fresh
            self._data["scenarios"] = [SkillCategory.from_dict(d) for d in _SEED_SCENARIOS]
            self._data["agent_types"] = [SkillCategory.from_dict(d) for d in _SEED_AGENT_TYPES]
            self._save_locked()
            logger.info("seeded fresh skill_categories.json at %s", self.file_path)

    def _save_locked(self) -> None:
        """Caller must hold self._lock."""
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": 1,
                "updated_at": time.time(),
                "dimensions": {
                    dim: [c.to_dict() for c in sorted(self._data[dim], key=lambda x: x.order)]
                    for dim in DIMENSIONS
                },
            }
            tmp = self.file_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, self.file_path)
        except Exception as e:
            logger.error("failed to save %s: %s", self.file_path, e)

    # ── Read API ─────────────────────────────────────────

    def list_all(self) -> dict[str, list[dict]]:
        """Return both dimensions as plain dicts, sorted by order then name.
        Used by the GET endpoint."""
        with self._lock:
            return {
                dim: [c.to_dict() for c in sorted(
                    self._data[dim], key=lambda x: (x.order, x.name))]
                for dim in DIMENSIONS
            }

    def get(self, dimension: str, cat_id: str) -> SkillCategory | None:
        if dimension not in DIMENSIONS:
            return None
        with self._lock:
            for c in self._data[dimension]:
                if c.id == cat_id:
                    return c
            return None

    def valid_id(self, dimension: str, cat_id: str) -> bool:
        """True if `cat_id` exists in `dimension`. Used to scrub stale
        category references from skill assignments after a delete."""
        return self.get(dimension, cat_id) is not None

    # ── Mutate API (admin only at HTTP layer) ────────────

    def upsert(self, dimension: str, cat: SkillCategory) -> SkillCategory:
        """Insert if `cat.id` is new in this dimension, else update fields
        in-place. Returns the stored entry."""
        if dimension not in DIMENSIONS:
            raise ValueError(f"unknown dimension: {dimension}")
        if not cat.id:
            raise ValueError("category id is required")
        with self._lock:
            existing = next((c for c in self._data[dimension] if c.id == cat.id), None)
            if existing is None:
                self._data[dimension].append(cat)
                stored = cat
            else:
                # Mutate in place so order/icon/name updates land
                existing.name = cat.name or existing.name
                existing.icon = cat.icon or existing.icon
                existing.order = cat.order if cat.order else existing.order
                existing.description = cat.description or existing.description
                stored = existing
            self._save_locked()
            return stored

    def delete(self, dimension: str, cat_id: str) -> bool:
        """Remove a category. Returns True if something was removed.
        Caller is responsible for cleaning up dangling skill assignments
        — `valid_id()` lets the skills layer detect them lazily."""
        if dimension not in DIMENSIONS:
            return False
        with self._lock:
            before = len(self._data[dimension])
            self._data[dimension] = [c for c in self._data[dimension] if c.id != cat_id]
            if len(self._data[dimension]) == before:
                return False
            self._save_locked()
            return True

    def reorder(self, dimension: str, ordered_ids: list[str]) -> None:
        """Rewrite `order` field on every existing category to match the
        position in `ordered_ids`. Unknown ids are silently dropped (no
        new categories are created here). Used by the drag-sort UI."""
        if dimension not in DIMENSIONS:
            return
        with self._lock:
            id_to_pos = {cid: i for i, cid in enumerate(ordered_ids)}
            for c in self._data[dimension]:
                if c.id in id_to_pos:
                    c.order = id_to_pos[c.id] + 1
            self._save_locked()


# ─────────────────────────────────────────────────────────────
# Per-skill category assignment store
# ─────────────────────────────────────────────────────────────
#
# Maps `skill_id → {scenarios: [cat_id, ...], agent_types: [...]}`
# Stored separately from CategoryStore so:
#   * admins can re-tag skills without touching the upstream SKILL.md
#     (which may come from a third-party git repo)
#   * adding/removing/renaming categories doesn't invalidate skill
#     assignments — orphan ids are simply filtered out at read time
#
# File: `~/.tudou_claw/skill_category_assignments.json`

class CategoryAssignmentStore:
    """Maps skill_id → category memberships. Multi-value on each
    dimension. Reads filter through the live CategoryStore so
    references to deleted categories vanish naturally without a
    separate migration."""

    def __init__(self, file_path: str | Path, category_store: CategoryStore):
        self.file_path = Path(file_path)
        self._cats = category_store
        self._lock = threading.Lock()
        # In-memory: {skill_id: {scenarios: set[str], agent_types: set[str]}}
        self._data: dict[str, dict[str, set[str]]] = {}
        self._load()

    def _load(self) -> None:
        with self._lock:
            if not self.file_path.exists():
                return
            try:
                raw = json.loads(self.file_path.read_text(encoding="utf-8"))
                for sid, dims in (raw.get("assignments") or {}).items():
                    if not isinstance(dims, dict): continue
                    self._data[sid] = {
                        dim: set(dims.get(dim, []) or []) for dim in DIMENSIONS
                    }
            except Exception as e:
                logger.warning("failed to load assignments %s: %s", self.file_path, e)

    def _save_locked(self) -> None:
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": 1,
                "updated_at": time.time(),
                "assignments": {
                    sid: {dim: sorted(self._data[sid].get(dim, set())) for dim in DIMENSIONS}
                    for sid in self._data
                },
            }
            tmp = self.file_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, self.file_path)
        except Exception as e:
            logger.error("failed to save %s: %s", self.file_path, e)

    def get(self, skill_id: str) -> dict[str, list[str]]:
        """Return active category memberships, filtered through the
        live CategoryStore (so deleted categories don't show up)."""
        with self._lock:
            entry = self._data.get(skill_id) or {}
        out = {}
        for dim in DIMENSIONS:
            ids = entry.get(dim, set())
            out[dim] = [cid for cid in ids if self._cats.valid_id(dim, cid)]
        return out

    def set(self, skill_id: str, scenarios: list[str], agent_types: list[str]) -> dict[str, list[str]]:
        """Replace the full membership set for one skill. Filters out
        ids that don't exist in the live CategoryStore."""
        with self._lock:
            self._data[skill_id] = {
                "scenarios":   {s for s in (scenarios or []) if self._cats.valid_id("scenarios", s)},
                "agent_types": {a for a in (agent_types or []) if self._cats.valid_id("agent_types", a)},
            }
            self._save_locked()
        return self.get(skill_id)

    def filter_skills(self, all_skill_ids: list[str], *,
                      scenarios: list[str] | None = None,
                      agent_types: list[str] | None = None) -> list[str]:
        """Return the subset of skill_ids that match ALL given filters.
        Empty filters mean "no constraint on that dimension"."""
        sel_sc = set(scenarios or [])
        sel_at = set(agent_types or [])
        if not sel_sc and not sel_at:
            return list(all_skill_ids)
        out = []
        for sid in all_skill_ids:
            asg = self.get(sid)
            if sel_sc and not (set(asg["scenarios"]) & sel_sc):
                continue
            if sel_at and not (set(asg["agent_types"]) & sel_at):
                continue
            out.append(sid)
        return out


# ─────────────────────────────────────────────────────────────
# Module-level singletons (initialized by hub on startup)
# ─────────────────────────────────────────────────────────────

_GLOBAL_CATEGORY_STORE: CategoryStore | None = None
_GLOBAL_ASSIGNMENT_STORE: CategoryAssignmentStore | None = None


def init_stores(categories_file: str | Path,
                assignments_file: str | Path) -> tuple[CategoryStore, CategoryAssignmentStore]:
    """Initialize both stores together. Hub calls this on boot."""
    global _GLOBAL_CATEGORY_STORE, _GLOBAL_ASSIGNMENT_STORE
    _GLOBAL_CATEGORY_STORE = CategoryStore(categories_file)
    _GLOBAL_ASSIGNMENT_STORE = CategoryAssignmentStore(assignments_file, _GLOBAL_CATEGORY_STORE)
    return _GLOBAL_CATEGORY_STORE, _GLOBAL_ASSIGNMENT_STORE


def get_store() -> CategoryStore | None:
    return _GLOBAL_CATEGORY_STORE


def get_assignments() -> CategoryAssignmentStore | None:
    return _GLOBAL_ASSIGNMENT_STORE
