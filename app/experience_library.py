"""
Experience Library Engine — 经验库引擎

实现 Agent 自我改进的双驱动闭环：
    1. 复盘经验固化 (Retrospective) — 任务执行后的总结学习
    2. 主动学习经验固化 (Active Learning) — 主动上网/查文档/学教程获取知识

架构：
    ExperienceLibrary (全局, per-role)
        ├── 经验模板 (Experience Template) — 统一结构化存储
        ├── 经验生成 (Generation) — 复盘+主动学习双渠道
        ├── 经验检索 (Retrieval) — 场景匹配、优先级、成功率排序
        ├── 经验更新 (Update) — 自动更新有效性、优先级、淘汰
        └── 文件轮转 (File Rotation) — 每日/每周文件、大小限制

全局经验库设计：
    data/experience/
        ├── {role}/
        │   ├── exp_{role}_YYYYMMDD.json      (每日文件)
        │   ├── exp_{role}_weekly_YYYYWNN.json (每周汇总)
        │   └── exp_{role}_core.json           (核心高优先级经验)
        └── _meta.json                         (全局元数据)

使用：
    lib = ExperienceLibrary(data_dir="data/experience")
    lib.add_experience(role="coder", exp=Experience(...))
    matches = lib.search(role="coder", scene="编码时遇到参数校验问题")
    lib.update_effectiveness(exp_id="coder-001", success=True)
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("tudou.experience")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_DAILY_FILE_SIZE = 512 * 1024     # 512 KB per daily file
MAX_WEEKLY_FILE_SIZE = 1024 * 1024   # 1 MB per weekly file
MAX_CORE_FILE_SIZE = 256 * 1024      # 256 KB core file
MAX_EXPERIENCES_PER_ROLE = 500       # max total experiences per role
CORE_EXPERIENCE_THRESHOLD = 0.75     # success rate >= 75% to be core
PURGE_THRESHOLD = 0.20               # success rate <= 20% gets purged
PURGE_CONSECUTIVE_FAILS = 3          # 3 consecutive fails = purge

ROLE_ABBREVIATIONS = {
    "ceo": "CEO", "cto": "CTO", "coder": "DEV", "reviewer": "REV",
    "researcher": "RES", "architect": "ARC", "devops": "OPS",
    "designer": "DES", "pm": "PM", "tester": "TST",
    "data": "DAT", "general": "GEN",
    # Chinese mapping
    "市场": "MKT", "产品": "PRD", "研发": "DEV",
}

# ---------------------------------------------------------------------------
# Experience data model
# ---------------------------------------------------------------------------

@dataclass
class Experience:
    """统一经验模板 — 复盘/主动学习通用"""
    id: str = ""                       # e.g. DEV-001
    exp_type: str = "retrospective"    # "retrospective" | "active_learning"
    source: str = ""                   # 来源说明
    scene: str = ""                    # 适用场景（触发条件）
    core_knowledge: str = ""           # 核心问题/知识点
    action_rules: list[str] = field(default_factory=list)   # 行动规则 (1-3条)
    taboo_rules: list[str] = field(default_factory=list)    # 禁忌规则 (1-2条)
    priority: str = "medium"           # "high" | "medium" | "low"
    success_count: int = 0
    fail_count: int = 0
    consecutive_fails: int = 0
    is_valid: bool = True              # False = marked for purge
    role: str = ""                     # which role this belongs to
    tags: list[str] = field(default_factory=list)
    # Sprint 3.2 — evidence references. Each entry is a free-form but
    # conventionally-shaped pointer to the source of truth this lesson
    # was mined from: "path/to/file.py:LINE" or "docs/SPEC.md#section".
    # When the experience is later cited (in prompt injection, portal
    # display, etc.) these references let the agent / reviewer jump
    # back to the raw evidence rather than trust the distilled summary.
    evidence: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.fail_count
        if total == 0:
            return 0.5  # neutral for new experiences
        return self.success_count / total

    @property
    def total_uses(self) -> int:
        return self.success_count + self.fail_count

    def to_dict(self) -> dict:
        return {
            "id": self.id, "exp_type": self.exp_type, "source": self.source,
            "scene": self.scene, "core_knowledge": self.core_knowledge,
            "action_rules": self.action_rules, "taboo_rules": self.taboo_rules,
            "priority": self.priority,
            "success_count": self.success_count, "fail_count": self.fail_count,
            "consecutive_fails": self.consecutive_fails,
            "is_valid": self.is_valid, "role": self.role,
            "tags": self.tags,
            "evidence": self.evidence,
            "created_at": self.created_at, "updated_at": self.updated_at,
        }

    @staticmethod
    def from_dict(d: dict) -> Experience:
        return Experience(
            id=d.get("id", ""),
            exp_type=d.get("exp_type", "retrospective"),
            source=d.get("source", ""),
            scene=d.get("scene", ""),
            core_knowledge=d.get("core_knowledge", ""),
            action_rules=d.get("action_rules", []),
            taboo_rules=d.get("taboo_rules", []),
            priority=d.get("priority", "medium"),
            success_count=d.get("success_count", 0),
            fail_count=d.get("fail_count", 0),
            consecutive_fails=d.get("consecutive_fails", 0),
            is_valid=d.get("is_valid", True),
            role=d.get("role", ""),
            tags=d.get("tags", []),
            # Backward-compat: older persisted entries lack this field;
            # default to empty list so existing libraries still load.
            evidence=d.get("evidence", []),
            created_at=d.get("created_at", time.time()),
            updated_at=d.get("updated_at", time.time()),
        )

    def to_prompt_text(self) -> str:
        """Format for injection into agent system prompt."""
        lines = [f"【{self.id}】({self.exp_type}) P={self.priority} "
                 f"成功率={self.success_rate:.0%}"]
        lines.append(f"  场景: {self.scene}")
        lines.append(f"  知识: {self.core_knowledge}")
        if self.action_rules:
            for i, r in enumerate(self.action_rules, 1):
                lines.append(f"  行动{i}: {r}")
        if self.taboo_rules:
            for i, r in enumerate(self.taboo_rules, 1):
                lines.append(f"  禁忌{i}: {r}")
        # Citations — listed compactly. The agent can fetch details via
        # read_file when a reference looks like `path:line` or open the
        # doc if it is a markdown anchor.
        if self.evidence:
            refs_display = ", ".join(self.evidence[:5])
            if len(self.evidence) > 5:
                refs_display += f" (+{len(self.evidence) - 5} more)"
            lines.append(f"  依据: {refs_display}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Retrospective result
# ---------------------------------------------------------------------------

@dataclass
class RetrospectiveResult:
    """复盘结果"""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    agent_id: str = ""
    agent_name: str = ""
    role: str = ""
    trigger: str = "manual"   # manual | task_complete | daily | weekly
    task_summary: str = ""    # 任务摘要

    # 复盘五步
    what_happened: str = ""      # 发生了什么？
    what_went_well: str = ""     # 哪些做得好？
    what_went_wrong: str = ""    # 哪些做得不好？
    root_cause: str = ""         # 根本原因分析
    improvement_plan: str = ""   # 改进方案

    # 生成的经验条目
    new_experiences: list[dict] = field(default_factory=list)
    updated_experiences: list[str] = field(default_factory=list)  # IDs

    raw_output: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "agent_id": self.agent_id,
            "agent_name": self.agent_name, "role": self.role,
            "trigger": self.trigger, "task_summary": self.task_summary,
            "what_happened": self.what_happened,
            "what_went_well": self.what_went_well,
            "what_went_wrong": self.what_went_wrong,
            "root_cause": self.root_cause,
            "improvement_plan": self.improvement_plan,
            "new_experiences": self.new_experiences,
            "updated_experiences": self.updated_experiences,
            "raw_output": self.raw_output,
            "created_at": self.created_at,
        }

    @staticmethod
    def from_dict(d: dict) -> RetrospectiveResult:
        return RetrospectiveResult(**{k: d[k] for k in d if k in RetrospectiveResult.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Active Learning result
# ---------------------------------------------------------------------------

@dataclass
class ActiveLearningResult:
    """主动学习结果"""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    agent_id: str = ""
    agent_name: str = ""
    role: str = ""
    trigger: str = "manual"   # manual | knowledge_gap | scheduled | trend

    learning_goal: str = ""      # 学习目标
    source_type: str = ""        # web_search | book | doc | tutorial
    source_detail: str = ""      # 具体来源
    key_findings: str = ""       # 关键发现
    applicable_scenes: str = ""  # 可应用场景

    new_experiences: list[dict] = field(default_factory=list)
    raw_output: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "agent_id": self.agent_id,
            "agent_name": self.agent_name, "role": self.role,
            "trigger": self.trigger,
            "learning_goal": self.learning_goal,
            "source_type": self.source_type,
            "source_detail": self.source_detail,
            "key_findings": self.key_findings,
            "applicable_scenes": self.applicable_scenes,
            "new_experiences": self.new_experiences,
            "raw_output": self.raw_output,
            "created_at": self.created_at,
        }


# ---------------------------------------------------------------------------
# ExperienceLibrary — global per-role experience storage
# ---------------------------------------------------------------------------

class ExperienceLibrary:
    """
    全局经验库管理器。

    经验按角色分目录存储，每日/每周自动轮转文件。
    核心高优先级经验单独存储在 core 文件中。
    """

    def __init__(self, data_dir: str = ""):
        if not data_dir:
            # Runtime state lives under user home, NOT inside the code tree.
            # Respect TUDOU_CLAW_HOME override if set.
            import os as _os
            _home = _os.environ.get("TUDOU_CLAW_HOME", "").strip()
            if _home:
                base = Path(_home).expanduser().resolve()
            else:
                base = Path.home() / ".tudou_claw"
            data_dir = str(base / "experience")
            # Migrate legacy in-code path if present and target is empty
            try:
                legacy = Path(__file__).resolve().parent / "data" / "experience"
                target = Path(data_dir)
                if legacy.exists() and legacy.is_dir() and not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    import shutil as _shutil
                    _shutil.copytree(str(legacy), str(target))
                    logger.info(
                        "Migrated experience library: %s -> %s", legacy, target
                    )
            except Exception as _mig_err:
                logger.warning("Experience library migration skipped: %s", _mig_err)
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._meta = self._load_meta()
        # In-memory cache: role -> list of Experience
        self._cache: dict[str, list[Experience]] = {}
        # SQLite backend
        self._db = self._init_db()
        logger.info(f"ExperienceLibrary initialized at {self.data_dir}")

    def _init_db(self):
        try:
            from .infra.database import get_database
            return get_database()
        except Exception:
            try:
                from app.infra.database import get_database
                return get_database()
            except Exception:
                return None

    # ---- Meta ----

    def _meta_path(self) -> Path:
        return self.data_dir / "_meta.json"

    def _load_meta(self) -> dict:
        p = self._meta_path()
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"roles": {}, "created_at": time.time(), "last_cleanup": 0}

    def _save_meta(self):
        try:
            self._meta_path().write_text(
                json.dumps(self._meta, ensure_ascii=False, indent=2),
                encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to save meta: {e}")

    # ---- Role directory management ----

    def _role_dir(self, role: str) -> Path:
        d = self.data_dir / role
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _daily_file(self, role: str, date: Optional[datetime] = None) -> Path:
        if date is None:
            date = datetime.now()
        ds = date.strftime("%Y%m%d")
        return self._role_dir(role) / f"exp_{role}_{ds}.json"

    def _weekly_file(self, role: str, date: Optional[datetime] = None) -> Path:
        if date is None:
            date = datetime.now()
        iso = date.isocalendar()
        ws = f"{iso[0]}W{iso[1]:02d}"
        return self._role_dir(role) / f"exp_{role}_weekly_{ws}.json"

    def _core_file(self, role: str) -> Path:
        return self._role_dir(role) / f"exp_{role}_core.json"

    # ---- File I/O helpers ----

    def _read_exp_file(self, path: Path) -> list[Experience]:
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return [Experience.from_dict(d) for d in data if isinstance(d, dict)]
        except Exception as e:
            logger.warning(f"Failed to read {path}: {e}")
            return []

    def _write_exp_file(self, path: Path, experiences: list[Experience],
                        max_size: int = MAX_DAILY_FILE_SIZE):
        """Write experiences to file, respecting size limit."""
        data = [e.to_dict() for e in experiences if e.is_valid]
        text = json.dumps(data, ensure_ascii=False, indent=1)
        # If over size limit, trim oldest entries
        while len(text.encode("utf-8")) > max_size and len(data) > 1:
            data.pop(0)  # remove oldest
            text = json.dumps(data, ensure_ascii=False, indent=1)
        try:
            path.write_text(text, encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to write {path}: {e}")

    # ---- Core operations ----

    def _next_id(self, role: str) -> str:
        """Generate next experience ID: e.g. DEV-042"""
        abbr = ROLE_ABBREVIATIONS.get(role, role.upper()[:3])
        # Get current count from meta
        role_meta = self._meta.get("roles", {}).get(role, {})
        seq = role_meta.get("next_seq", 1)
        # Update meta
        if "roles" not in self._meta:
            self._meta["roles"] = {}
        if role not in self._meta["roles"]:
            self._meta["roles"][role] = {}
        self._meta["roles"][role]["next_seq"] = seq + 1
        self._save_meta()
        return f"{abbr}-{seq:03d}"

    def add_experience(self, role: str, exp: Experience) -> Experience:
        """Add a new experience to the library."""
        with self._lock:
            if not exp.id:
                exp.id = self._next_id(role)
            exp.role = role
            exp.created_at = time.time()
            exp.updated_at = time.time()

            # SQLite primary
            if self._db:
                try:
                    d = exp.to_dict()
                    d["role"] = role
                    d["period"] = datetime.now().strftime("%Y%m%d")
                    d["priority"] = {"high": 3, "medium": 2, "low": 1}.get(
                        str(exp.priority), 0)
                    self._db.save_experience(d)
                except Exception as e:
                    logger.warning(f"SQLite experience save failed: {e}")

            # Write to daily file (backup)
            daily = self._daily_file(role)
            existing = self._read_exp_file(daily)
            existing.append(exp)
            self._write_exp_file(daily, existing, MAX_DAILY_FILE_SIZE)

            # If high priority + good success rate, also add to core
            if exp.priority == "high":
                self._add_to_core(role, exp)

            # Update meta
            rm = self._meta.get("roles", {}).get(role, {})
            rm["total_count"] = rm.get("total_count", 0) + 1
            rm["last_updated"] = time.time()
            if "roles" not in self._meta:
                self._meta["roles"] = {}
            self._meta["roles"][role] = rm
            self._save_meta()

            # Invalidate cache
            self._cache.pop(role, None)

            logger.info(f"Added experience {exp.id} to role={role}")
            return exp

    def _add_to_core(self, role: str, exp: Experience):
        """Add/update experience in core file."""
        core_path = self._core_file(role)
        core_exps = self._read_exp_file(core_path)
        # Replace if same ID exists
        core_exps = [e for e in core_exps if e.id != exp.id]
        core_exps.append(exp)
        self._write_exp_file(core_path, core_exps, MAX_CORE_FILE_SIZE)

    def get_all_experiences(self, role: str) -> list[Experience]:
        """Get all valid experiences for a role (with caching)."""
        if role in self._cache:
            return self._cache[role]

        all_exps: dict[str, Experience] = {}

        # 优先从 SQLite 读取
        if self._db and self._db.count("experiences", "role=?", (role,)) > 0:
            try:
                for d in self._db.load_experiences(role=role):
                    e = Experience.from_dict(d)
                    if e.is_valid:
                        all_exps[e.id] = e
                result = sorted(all_exps.values(),
                                key=lambda x: x.created_at, reverse=True)
                self._cache[role] = result
                return result
            except Exception as e_err:
                logger.warning(f"SQLite experience load failed: {e_err}")
                all_exps.clear()

        # Read core first
        for e in self._read_exp_file(self._core_file(role)):
            if e.is_valid:
                all_exps[e.id] = e

        # Read daily files (last 30 days)
        rd = self._role_dir(role)
        if rd.exists():
            for f in sorted(rd.glob(f"exp_{role}_*.json")):
                if "core" in f.name or "weekly" in f.name:
                    continue
                for e in self._read_exp_file(f):
                    if e.is_valid:
                        all_exps[e.id] = e  # newer overrides older

        result = list(all_exps.values())
        self._cache[role] = result
        return result

    def get_experience_count(self, role: str) -> int:
        """Get total experience count for a role."""
        rm = self._meta.get("roles", {}).get(role, {})
        cached = rm.get("total_count", 0)
        if cached > 0:
            return cached
        return len(self.get_all_experiences(role))

    def get_all_role_counts(self) -> dict[str, int]:
        """Get experience counts for all roles."""
        counts = {}
        for role in self._meta.get("roles", {}):
            counts[role] = self.get_experience_count(role)
        return counts

    def search(self, role: str, scene: str = "", tags: list[str] = None,
               min_priority: str = "low", min_success_rate: float = 0.0,
               limit: int = 10) -> list[Experience]:
        """Search experiences by scene match, priority, and success rate."""
        all_exps = self.get_all_experiences(role)

        priority_order = {"high": 3, "medium": 2, "low": 1}
        min_p = priority_order.get(min_priority, 0)

        results = []
        for e in all_exps:
            if not e.is_valid:
                continue
            if priority_order.get(e.priority, 0) < min_p:
                continue
            if e.total_uses > 0 and e.success_rate < min_success_rate:
                continue

            # Scene keyword matching
            score = 0
            if scene:
                scene_lower = scene.lower()
                if scene_lower in e.scene.lower():
                    score += 10
                if scene_lower in e.core_knowledge.lower():
                    score += 5
                # Keyword overlap
                scene_words = set(scene_lower.split())
                exp_words = set(e.scene.lower().split()) | set(e.core_knowledge.lower().split())
                overlap = scene_words & exp_words
                score += len(overlap) * 2

            # Tag matching
            if tags:
                tag_set = set(t.lower() for t in tags)
                exp_tags = set(t.lower() for t in e.tags)
                score += len(tag_set & exp_tags) * 3

            # Priority boost
            score += priority_order.get(e.priority, 0) * 2

            # Success rate boost
            if e.total_uses > 0:
                score += e.success_rate * 5

            if score > 0 or not scene:
                results.append((score, e))

        results.sort(key=lambda x: (-x[0], -priority_order.get(x[1].priority, 0)))
        return [e for _, e in results[:limit]]

    def update_effectiveness(self, role: str, exp_id: str, success: bool) -> Optional[Experience]:
        """Update experience effectiveness after use."""
        with self._lock:
            all_exps = self.get_all_experiences(role)
            target = None
            for e in all_exps:
                if e.id == exp_id:
                    target = e
                    break
            if not target:
                return None

            if success:
                target.success_count += 1
                target.consecutive_fails = 0
            else:
                target.fail_count += 1
                target.consecutive_fails += 1

            target.updated_at = time.time()

            # Auto-adjust priority
            rate = target.success_rate
            if rate >= 0.80 and target.priority != "high":
                old = target.priority
                target.priority = {"low": "medium", "medium": "high"}.get(old, old)
                logger.info(f"Experience {exp_id} priority ↑ {old} → {target.priority}")
            elif rate <= 0.30 and target.priority != "low":
                old = target.priority
                target.priority = {"high": "medium", "medium": "low"}.get(old, old)
                logger.info(f"Experience {exp_id} priority ↓ {old} → {target.priority}")

            # Auto-purge
            if target.consecutive_fails >= PURGE_CONSECUTIVE_FAILS or \
               (target.total_uses >= 3 and rate <= PURGE_THRESHOLD):
                target.is_valid = False
                logger.info(f"Experience {exp_id} purged (rate={rate:.0%}, fails={target.consecutive_fails})")

            # If high priority, update core
            if target.priority == "high" and target.is_valid:
                self._add_to_core(role, target)

            # Write back to daily file
            daily = self._daily_file(role)
            daily_exps = self._read_exp_file(daily)
            for i, e in enumerate(daily_exps):
                if e.id == exp_id:
                    daily_exps[i] = target
                    break
            else:
                daily_exps.append(target)
            self._write_exp_file(daily, daily_exps, MAX_DAILY_FILE_SIZE)

            self._cache.pop(role, None)
            return target

    def weekly_consolidation(self, role: str):
        """Weekly consolidation: merge daily files into weekly, prune invalid."""
        with self._lock:
            rd = self._role_dir(role)
            now = datetime.now()
            week_start = now - timedelta(days=now.weekday())
            all_week_exps: dict[str, Experience] = {}

            # Collect from daily files of past 7 days
            for i in range(7):
                d = now - timedelta(days=i)
                daily = self._daily_file(role, d)
                for e in self._read_exp_file(daily):
                    if e.is_valid:
                        all_week_exps[e.id] = e

            if all_week_exps:
                weekly = self._weekly_file(role)
                existing = self._read_exp_file(weekly)
                for e in existing:
                    if e.id not in all_week_exps and e.is_valid:
                        all_week_exps[e.id] = e

                self._write_exp_file(
                    weekly,
                    list(all_week_exps.values()),
                    MAX_WEEKLY_FILE_SIZE
                )

            # Update core: keep only high priority + valid
            core_exps = self._read_exp_file(self._core_file(role))
            core_exps = [e for e in core_exps
                         if e.is_valid and e.priority == "high"
                         and (e.total_uses == 0 or e.success_rate >= CORE_EXPERIENCE_THRESHOLD)]
            self._write_exp_file(self._core_file(role), core_exps, MAX_CORE_FILE_SIZE)

            self._cache.pop(role, None)
            logger.info(f"Weekly consolidation for role={role}: {len(all_week_exps)} experiences")

    def get_core_experiences(self, role: str) -> list[Experience]:
        """Get core (high priority, high success) experiences for a role."""
        return self._read_exp_file(self._core_file(role))

    def import_to_agent(self, role: str, limit: int = 50) -> list[Experience]:
        """
        Import experiences for a new agent of given role.
        Returns the most relevant experiences, prioritized by:
        1. Core (high priority) experiences
        2. High success rate experiences
        3. Recent experiences
        """
        core = self.get_core_experiences(role)
        all_exps = self.get_all_experiences(role)

        # Deduplicate
        imported: dict[str, Experience] = {}
        for e in core:
            if e.is_valid:
                imported[e.id] = e
        for e in sorted(all_exps, key=lambda x: (
            -{"high": 3, "medium": 2, "low": 1}.get(x.priority, 0),
            -x.success_rate,
            -x.created_at
        )):
            if e.is_valid and e.id not in imported:
                imported[e.id] = e
            if len(imported) >= limit:
                break

        return list(imported.values())[:limit]

    def import_cross_role(self, source_role: str, target_role: str,
                          topic: str = "", limit: int = 5) -> list[Experience]:
        """Import high-quality experiences from another role.

        This enables cross-role learning: a PM can learn design skills
        from a designer's experience pool.
        """
        source_exps = self.get_all_experiences(source_role)
        if not source_exps:
            return []

        # Filter to valid experiences only
        source_exps = [e for e in source_exps if e.is_valid]

        # Filter by topic if specified
        if topic:
            topic_lower = topic.lower()
            source_exps = [
                e for e in source_exps
                if topic_lower in (e.scene or "").lower()
                or topic_lower in (e.core_knowledge or "").lower()
                or any(topic_lower in tag.lower() for tag in (e.tags or []))
            ]

        # Sort by quality: high priority first, then by success rate, then use count
        priority_order = {"high": 3, "medium": 2, "low": 1}
        source_exps.sort(key=lambda e: (
            -priority_order.get(e.priority, 0),
            -e.success_rate,
            -e.total_uses,
        ))

        return source_exps[:limit]

    def load_seeds_if_empty(self, role: str):
        """Load seed experiences for a role if no experiences exist yet."""
        existing = self.get_all_experiences(role)
        if existing:
            return  # Already has experiences

        seeds_file = Path(__file__).resolve().parent / "static" / "config" / "experience_seeds.json"
        if not seeds_file.exists():
            return
        try:
            data = json.loads(seeds_file.read_text(encoding="utf-8"))
            seeds = data.get("seeds", {}).get(role, [])
            for sd in seeds:
                exp = Experience(
                    exp_type=sd.get("exp_type", "active_learning"),
                    source=sd.get("source", "seed"),
                    scene=sd.get("scene", ""),
                    core_knowledge=sd.get("core_knowledge", ""),
                    action_rules=sd.get("action_rules", []),
                    taboo_rules=sd.get("taboo_rules", []),
                    priority=sd.get("priority", "medium"),
                    tags=sd.get("tags", []),
                )
                self.add_experience(role, exp)
            if seeds:
                logger.info(f"Loaded {len(seeds)} seed experiences for role={role}")
        except Exception as e:
            logger.warning(f"Failed to load seeds for {role}: {e}")

    def get_stats(self) -> dict:
        """Get global experience library statistics."""
        stats = {
            "data_dir": str(self.data_dir),
            "roles": {},
            "total_experiences": 0,
        }
        for role, meta in self._meta.get("roles", {}).items():
            count = meta.get("total_count", 0)
            stats["roles"][role] = {
                "total": count,
                "last_updated": meta.get("last_updated", 0),
                "core_count": len(self._read_exp_file(self._core_file(role))),
            }
            stats["total_experiences"] += count
        return stats


# ---------------------------------------------------------------------------
# SelfImprovementEngine — per-agent engine combining retrospective + learning
# ---------------------------------------------------------------------------

class SelfImprovementEngine:
    """
    Agent 自我改进引擎。
    每个 agent 一个实例，负责：
    1. 触发复盘 (retrospective)
    2. 触发主动学习 (active learning)
    3. 从全局经验库检索经验注入 system prompt
    4. 在执行后更新经验有效性
    """

    def __init__(self, agent=None, role: str = "",
                 library: ExperienceLibrary = None):
        self.agent = agent
        self.role = role or (agent.role if agent else "general")
        self.library = library or _get_global_library()
        self.enabled = False
        self.auto_retrospective = True      # 自动在任务完成后复盘
        self.auto_learning_interval = 0     # 0 = disabled, else seconds
        self.imported_experience_ids: list[str] = []  # imported from library
        self.retrospective_history: list[dict] = []   # last N retros
        self.learning_history: list[dict] = []        # last N learnings
        self._last_learning_at = 0.0
        self._lock = threading.Lock()
        self._learning_paused: bool = False
        self._learning_queue: list[dict] = []  # Queued learning tasks
        self._current_learning: dict | None = None  # Currently executing learning
        self.quality_history: list[dict] = []   # [{timestamp, task_summary, overall_score, goal_scores: {goal_id: score}}]

    def enable(self, auto_retro: bool = True, auto_learn_interval: int = 0,
               import_experience: bool = True, import_limit: int = 50):
        """Enable self-improvement for this agent."""
        self.enabled = True
        self.auto_retrospective = auto_retro
        self.auto_learning_interval = auto_learn_interval
        # Load seed experiences if this role has none yet
        self.library.load_seeds_if_empty(self.role)
        if import_experience:
            self.import_role_experience(limit=import_limit)
        logger.info(f"SelfImprovement enabled for agent role={self.role}")

    def disable(self):
        self.enabled = False

    def import_role_experience(self, limit: int = 50) -> int:
        """Import experiences from global library for this role."""
        exps = self.library.import_to_agent(self.role, limit=limit)
        self.imported_experience_ids = [e.id for e in exps]
        logger.info(f"Imported {len(exps)} experiences for role={self.role}")
        return len(exps)

    def get_imported_experiences(self) -> list[Experience]:
        """Get the actual imported experience objects."""
        all_exps = self.library.get_all_experiences(self.role)
        id_set = set(self.imported_experience_ids)
        return [e for e in all_exps if e.id in id_set]

    def should_pause_for_tasks(self) -> bool:
        """Check if learning should pause because agent has pending tasks/projects."""
        if not self.agent:
            return False
        # Check agent's task queue
        tasks = getattr(self.agent, 'tasks', [])
        has_pending = any(
            t.status in ('TODO', 'IN_PROGRESS')
            for t in tasks if hasattr(t, 'status')
        )
        # Check if agent is currently chatting / busy
        is_busy = getattr(self.agent, 'status', None) in ('chatting', 'busy', 'working')
        return has_pending or is_busy

    def queue_learning(self, learning_goal: str, knowledge_gap: str = "") -> dict:
        """Queue a learning task. Requires a non-empty, meaningful goal.

        Empty or placeholder goals are rejected — they produce "未设定目标"
        noise in the learning plan board and never converge to experiences.
        """
        goal = (learning_goal or "").strip()
        if not goal or goal in ("(未设定)", "未设定", "未设定目标", "自我反思与经验沉淀"):
            raise ValueError(
                "learning_goal must be a specific, non-empty study objective "
                "(e.g. '排查最近 3 次 bash 拒绝的根因', "
                "not an empty string or generic placeholder)"
            )
        if len(goal) < 6:
            raise ValueError(
                f"learning_goal too short ({len(goal)} chars); describe a "
                "concrete objective in at least a few words"
            )
        task = {
            "id": uuid.uuid4().hex[:10],
            "learning_goal": goal,
            "knowledge_gap": (knowledge_gap or "").strip(),
            "status": "queued",
            "queued_at": time.time(),
            "started_at": None,
            "completed_at": None,
        }
        self._learning_queue.append(task)
        return task

    def check_and_resume_learning(self) -> dict | None:
        """Called periodically. If agent is idle and has queued learning, execute next one."""
        if self.should_pause_for_tasks():
            return None
        if not self._learning_queue:
            return None
        # Pop next task
        task = self._learning_queue.pop(0)
        task["status"] = "in_progress"
        task["started_at"] = time.time()
        self._current_learning = task
        return task

    # ---- Retrospective ----

    def build_retrospective_prompt(self, task_summary: str = "",
                                    context: str = "") -> str:
        """Build prompt for agent to perform self-retrospective."""
        role_focus = _ROLE_RETRO_FOCUS.get(self.role, _ROLE_RETRO_FOCUS["general"])

        # Get relevant existing experiences
        relevant = self.library.search(
            role=self.role, scene=task_summary, limit=5)
        relevant_text = ""
        if relevant:
            relevant_text = "\n## 相关已有经验 (Existing Relevant Experiences)\n"
            for e in relevant:
                relevant_text += e.to_prompt_text() + "\n\n"

        prompt = f"""# 自我复盘 (Self-Retrospective)

你是 {self.role} 角色的智能体，现在需要对刚完成的工作进行复盘。

## 复盘重点 (Focus Areas)
{role_focus}

## 任务摘要 (Task Summary)
{task_summary or '(请基于最近的对话和工作内容进行复盘)'}

{f'## 额外上下文{chr(10)}{context}' if context else ''}

{relevant_text}

## 输出要求 (Output Requirements)

请严格按照以下JSON格式输出（不要添加其他内容）：

```json
{{
  "what_happened": "发生了什么？简述任务过程和结果",
  "what_went_well": "哪些做得好？具体成功点",
  "what_went_wrong": "哪些做得不好？具体失败点或不足",
  "root_cause": "根本原因分析",
  "improvement_plan": "具体改进方案（可执行）",
  "new_experiences": [
    {{
      "exp_type": "retrospective",
      "source": "复盘来源描述",
      "scene": "适用场景（触发条件）",
      "core_knowledge": "核心知识点/教训",
      "action_rules": ["行动规则1", "行动规则2"],
      "taboo_rules": ["禁忌规则1"],
      "priority": "high/medium/low",
      "tags": ["tag1", "tag2"]
    }}
  ],
  "updated_experience_ids": ["已有经验ID列表，如需更新其有效性"],
  "updated_experience_results": ["success/fail 对应每个ID"]
}}
```

要求：
1. 经验必须具体、可复用，不写空泛理论
2. 行动规则必须落地可执行
3. 至少生成1条新经验
4. 如果调用了已有经验，必须标注结果
"""
        return prompt

    def process_retrospective_output(self, raw_output: str,
                                      task_summary: str = "") -> RetrospectiveResult:
        """Parse LLM retrospective output and update experience library."""
        result = RetrospectiveResult(
            agent_id=self.agent.id if self.agent else "",
            agent_name=self.agent.name if self.agent else "",
            role=self.role,
            task_summary=task_summary,
            raw_output=raw_output,
        )

        # Parse JSON from output
        parsed = _extract_json(raw_output)
        if parsed:
            result.what_happened = parsed.get("what_happened", "")
            result.what_went_well = parsed.get("what_went_well", "")
            result.what_went_wrong = parsed.get("what_went_wrong", "")
            result.root_cause = parsed.get("root_cause", "")
            result.improvement_plan = parsed.get("improvement_plan", "")

            # Process new experiences
            for exp_data in parsed.get("new_experiences", []):
                exp = Experience(
                    exp_type="retrospective",
                    source=exp_data.get("source", f"复盘-{task_summary[:30]}"),
                    scene=exp_data.get("scene", ""),
                    core_knowledge=exp_data.get("core_knowledge", ""),
                    action_rules=exp_data.get("action_rules", []),
                    taboo_rules=exp_data.get("taboo_rules", []),
                    priority=exp_data.get("priority", "medium"),
                    tags=exp_data.get("tags", []),
                )
                if exp.scene and exp.core_knowledge:
                    added = self.library.add_experience(self.role, exp)
                    result.new_experiences.append(added.to_dict())

            # Update existing experience effectiveness
            ids = parsed.get("updated_experience_ids", [])
            results_list = parsed.get("updated_experience_results", [])
            for i, eid in enumerate(ids):
                success = (results_list[i] == "success") if i < len(results_list) else True
                self.library.update_effectiveness(self.role, eid, success)
                result.updated_experiences.append(eid)

            # Sync new experiences to L3 semantic memory
            for exp_dict in result.new_experiences:
                self._sync_experience_to_memory(exp_dict)

            # Auto-share high-value experiences to knowledge base
            for exp_dict in result.new_experiences:
                sr = exp_dict.get("success_count", 0)
                fr = exp_dict.get("fail_count", 0)
                total = sr + fr
                success_rate = sr / total if total > 0 else 0.5
                if success_rate >= 0.85 and exp_dict.get("priority") == "high":
                    try:
                        from .knowledge import add_entry, search
                        scene = exp_dict.get("scene", "")
                        # Check if already shared (avoid duplicates)
                        existing = search(scene)
                        already_shared = any(
                            scene.lower() in (e.get("title", "")).lower()
                            for e in existing
                        )
                        if not already_shared:
                            ck = exp_dict.get("core_knowledge", "")
                            rules = exp_dict.get("action_rules", [])
                            content = f"Category: {exp_dict.get('exp_type', 'retrospective')}\n\nKnowledge:\n{ck}"
                            if rules:
                                content += "\n\nAction rules:\n" + "\n".join(f"- {r}" for r in rules)
                            add_entry(
                                title=f"[{self.role}] {scene}",
                                content=content,
                                tags=["auto-shared", self.role] + exp_dict.get("tags", []),
                            )
                            logger.info("Auto-shared high-value experience to knowledge base: %s", scene)
                    except Exception as e:
                        logger.debug("Auto-share to knowledge failed: %s", e)

        # Store in history
        self.retrospective_history.append(result.to_dict())
        if len(self.retrospective_history) > 50:
            self.retrospective_history = self.retrospective_history[-50:]

        # Evaluate task quality against evolution goals
        if self.agent and hasattr(self.agent, 'evolution_goals') and self.agent.evolution_goals:
            try:
                _task_summary = task_summary or (parsed.get("what_happened", "") if parsed else "")
                _task_result = (parsed.get("what_went_well", "") if parsed else "") or raw_output[:1000]
                eval_result = self.evaluate_task_quality(
                    _task_summary, _task_result, self.agent.evolution_goals
                )
                if eval_result:
                    overall = eval_result.get("overall_score", 0)
                    logger.info(
                        "Agent %s quality evaluation: %d/100",
                        self.agent.id[:8] if self.agent else "?", overall,
                    )
                    # Trigger learning for underperforming goals
                    for g in self.agent.evolution_goals:
                        gid = g.get("id", "")
                        target = g.get("target_score", 80)
                        gs = eval_result.get("goal_scores", {}).get(gid, {})
                        score = gs.get("score", 0) if isinstance(gs, dict) else (gs if isinstance(gs, (int, float)) else 0)
                        if score < target and eval_result.get("suggestions"):
                            goal_desc = g.get("description", gid)
                            suggestions_text = "; ".join(eval_result["suggestions"][:3])
                            try:
                                self.queue_learning(
                                    learning_goal=f"Improve on goal '{goal_desc}' (scored {score}/{target}): {suggestions_text}",
                                    knowledge_gap=f"Goal gap: {target - score} points",
                                )
                            except ValueError:
                                pass  # Skip if goal text is rejected by validation
            except Exception as e:
                logger.debug("Quality evaluation in retrospective failed: %s", e)

        return result

    # ---- Active Learning ----

    def build_learning_prompt(self, learning_goal: str = "",
                               knowledge_gap: str = "") -> str:
        """Build prompt for agent to perform active learning.

        If no explicit learning_goal is given and the agent has a RoleGrowthPath,
        the next uncompleted objective from the current stage is used automatically.
        """
        # --- Growth-path integration: auto-pick objective if no goal given ---
        _growth_objective = None
        if not learning_goal and self.agent:
            try:
                obj = self.agent.get_next_learning_objective()
                if obj:
                    from app.core.role_growth_path import build_learning_task_prompt
                    _growth_objective = obj
                    gp = self.agent.growth_path
                    learning_goal = build_learning_task_prompt(
                        obj, role_name=gp.role_name if gp else self.role)
                    if not knowledge_gap:
                        knowledge_gap = f"成长阶段: {gp.current_stage.name if gp and gp.current_stage else '未知'} | 目标: {obj.title}"
            except Exception:
                pass

        role_focus = _ROLE_LEARNING_FOCUS.get(self.role, _ROLE_LEARNING_FOCUS["general"])

        # Check existing knowledge to avoid duplication
        existing = self.library.search(
            role=self.role, scene=learning_goal or knowledge_gap, limit=5)
        existing_text = ""
        if existing:
            existing_text = "\n## 已有相关经验（避免重复学习）\n"
            for e in existing:
                existing_text += f"- {e.id}: {e.core_knowledge}\n"

        prompt = f"""# 主动学习 (Active Learning)

你是 {self.role} 角色的智能体，现在进行主动学习以填补知识缺口。

## 学习方向 (Learning Focus)
{role_focus}

## 学习目标 (Learning Goal)
{learning_goal or '基于当前角色职责，选择最有价值的知识点进行学习'}

{f'## 知识缺口{chr(10)}{knowledge_gap}' if knowledge_gap else ''}

{existing_text}

## 输出要求 (Output Requirements)

请严格按照以下JSON格式输出：

```json
{{
  "learning_goal": "本次学习目标",
  "source_type": "web_search/book/doc/tutorial",
  "source_detail": "具体来源",
  "key_findings": "关键发现和学习收获",
  "applicable_scenes": "可应用的实际场景",
  "new_experiences": [
    {{
      "exp_type": "active_learning",
      "source": "学习来源描述",
      "scene": "适用场景",
      "core_knowledge": "核心知识点/方法论",
      "action_rules": ["可落地的行动步骤1", "行动步骤2"],
      "taboo_rules": ["应用禁忌1"],
      "priority": "high/medium/low",
      "tags": ["tag1", "tag2"]
    }}
  ]
}}
```

要求：
1. 学到的知识必须转化为可执行的行动步骤
2. 场景必须贴合 {self.role} 角色职责
3. 至少生成1条新的主动学习经验
4. 避免与已有经验重复
"""
        return prompt

    def process_learning_output(self, raw_output: str,
                                objective_id: str = "") -> ActiveLearningResult:
        """Parse LLM active learning output and update library.

        Args:
            raw_output: The LLM's learning output (JSON expected).
            objective_id: If provided, mark this growth-path objective as completed.
        """
        result = ActiveLearningResult(
            agent_id=self.agent.id if self.agent else "",
            agent_name=self.agent.name if self.agent else "",
            role=self.role,
            raw_output=raw_output,
        )

        exp_ids: list[str] = []
        parsed = _extract_json(raw_output)
        if parsed:
            result.learning_goal = parsed.get("learning_goal", "")
            result.source_type = parsed.get("source_type", "")
            result.source_detail = parsed.get("source_detail", "")
            result.key_findings = parsed.get("key_findings", "")
            result.applicable_scenes = parsed.get("applicable_scenes", "")

            for exp_data in parsed.get("new_experiences", []):
                exp = Experience(
                    exp_type="active_learning",
                    source=exp_data.get("source", ""),
                    scene=exp_data.get("scene", ""),
                    core_knowledge=exp_data.get("core_knowledge", ""),
                    action_rules=exp_data.get("action_rules", []),
                    taboo_rules=exp_data.get("taboo_rules", []),
                    priority=exp_data.get("priority", "medium"),
                    tags=exp_data.get("tags", []),
                )
                if exp.scene and exp.core_knowledge:
                    added = self.library.add_experience(self.role, exp)
                    result.new_experiences.append(added.to_dict())
                    exp_ids.append(added.id)

            # Sync new experiences to L3 semantic memory
            for exp_dict in result.new_experiences:
                self._sync_experience_to_memory(exp_dict)

        self.learning_history.append(result.to_dict())
        if len(self.learning_history) > 50:
            self.learning_history = self.learning_history[-50:]

        self._last_learning_at = time.time()

        # --- Growth-path integration: eval-driven completion (P2 #7) ---
        if objective_id and self.agent and result.new_experiences:
            try:
                gp = self.agent.growth_path
                if gp:
                    eval_fn = getattr(gp, "evaluate_and_complete", None)
                    if callable(eval_fn):
                        outcome = eval_fn(
                            objective_id,
                            result.new_experiences,
                            experience_ids=exp_ids,
                        )
                        # Store eval on the result for observability
                        try:
                            result.growth_eval = outcome  # type: ignore[attr-defined]
                        except Exception:
                            pass
                        if outcome.get("completed"):
                            gp.try_advance()
                            logger.info(
                                "Growth path objective '%s' completed for "
                                "role=%s (score=%.2f, %s)",
                                objective_id, self.role,
                                outcome.get("score", 0.0),
                                outcome.get("reason", ""),
                            )
                        else:
                            logger.info(
                                "Growth path objective '%s' needs more work "
                                "for role=%s (score=%.2f, %s)",
                                objective_id, self.role,
                                outcome.get("score", 0.0),
                                outcome.get("reason", ""),
                            )
                    else:
                        # Legacy fallback
                        gp.mark_objective_completed(objective_id, experience_ids=exp_ids)
                        gp.try_advance()
            except Exception as _ge:
                logger.debug("growth-path eval failed: %s", _ge)

        return result

    # ---- Memory integration ----

    def _sync_experience_to_memory(self, experience_dict: dict):
        """Sync an experience to agent's L3 semantic memory."""
        if not self.agent:
            return
        try:
            memory = getattr(self.agent, 'memory', None)
            if memory and hasattr(memory, 'add_semantic_fact'):
                content = (
                    f"[经验] {experience_dict.get('scene', '')}: "
                    f"{experience_dict.get('core_knowledge', '')}"
                )
                if experience_dict.get('action_rules'):
                    content += f"\n行动规则: {'; '.join(experience_dict['action_rules'])}"
                memory.add_semantic_fact(
                    agent_id=self.agent.id,
                    category="learned",
                    content=content,
                    source=f"self_improvement:{experience_dict.get('id', '')}",
                    confidence=0.8,
                )
        except Exception as e:
            import logging
            logging.getLogger("tudou.experience").warning(
                f"Failed to sync experience to L3 memory: {e}")

    # ---- Experience injection ----

    def build_experience_context(self, task_hint: str = "",
                                  limit: int = 15) -> str:
        """Build experience index for agent system prompt injection.

        Inject ONLY titles (scene + priority + usage stats), not full
        bodies. Agent calls ``knowledge_lookup(kind="experience", ...)``
        to fetch full content when it actually needs to apply one.
        Returns "" when the library is empty for this role — saves the
        ~200-char header that would otherwise be pure waste.
        """
        if not self.enabled:
            return ""

        # Get candidate experiences (title-level only)
        if task_hint:
            exps = self.library.search(self.role, scene=task_hint, limit=limit)
        else:
            exps = self.library.import_to_agent(self.role, limit=limit)

        if not exps:
            return ""

        lines = [
            f"# 经验库索引 — role={self.role} ({len(exps)} 条;"
            " 调 knowledge_lookup 取详情)",
        ]
        for e in exps:
            scene = (e.scene or "")[:50] or "(无标题)"
            stats = f"✓{e.success_count}/✗{e.fail_count}"
            lines.append(
                f"- [{e.id}] {scene} (priority={e.priority}, {stats})"
            )
        return "\n".join(lines)

    # ---- Quality evaluation (evolution goals) ----

    def evaluate_task_quality(self, task_summary: str, task_result: str,
                              goals: list[dict]) -> dict | None:
        """Evaluate task output quality against agent's evolution goals.

        Uses LLM to score how well the output meets each goal.
        Returns {overall_score, goal_scores: {id: {score, feedback}}, suggestions: []}
        """
        if not goals:
            return None

        import json as _json
        goals_text = "\n".join(
            f"- [{g.get('id', '?')}] {g.get('description', '')} (target: {g.get('target_score', 80)})"
            for g in goals
        )

        eval_prompt = (
            "Evaluate the following task output against the goals below.\n\n"
            f"Task: {task_summary}\n\n"
            f"Output/Result:\n{task_result[:3000]}\n\n"
            f"Goals:\n{goals_text}\n\n"
            "Score each goal 0-100 based on how well the output meets it.\n"
            "Return ONLY valid JSON:\n"
            '{"overall_score": <0-100>, "goal_scores": {"<goal_id>": {"score": <0-100>, "feedback": "<brief>"}}, "suggestions": ["<improvement tip>"]}'
        )

        try:
            from . import llm as _llm
            agent = self.agent
            if agent:
                prov, mdl = agent._resolve_effective_provider_model()
            else:
                cfg = _llm.get_config()
                prov = cfg.get("provider", "")
                mdl = cfg.get("model", "")

            response = _llm.chat_no_stream(
                messages=[{"role": "user", "content": eval_prompt}],
                provider=prov, model=mdl,
            )

            # Extract text from normalised Ollama-format dict
            text = response.get("message", {}).get("content", "") if isinstance(response, dict) else str(response)

            # Try to extract JSON
            import re
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                result = _json.loads(json_match.group())

                # Record in history
                self.quality_history.append({
                    "timestamp": time.time(),
                    "task_summary": task_summary[:200],
                    "overall_score": result.get("overall_score", 0),
                    "goal_scores": {
                        gid: gs.get("score", 0) if isinstance(gs, dict) else gs
                        for gid, gs in result.get("goal_scores", {}).items()
                    },
                })
                # Keep last 100 entries
                if len(self.quality_history) > 100:
                    self.quality_history = self.quality_history[-100:]

                # Update current_score on agent's goals
                if agent and hasattr(agent, 'evolution_goals'):
                    for g in agent.evolution_goals:
                        gid = g.get("id", "")
                        if gid in result.get("goal_scores", {}):
                            gs = result["goal_scores"][gid]
                            score = gs.get("score", 0) if isinstance(gs, dict) else gs
                            g["current_score"] = score

                return result
        except Exception as e:
            logger.debug("Quality evaluation failed: %s", e)
        return None

    def get_achievement_rate(self, goal_id: str = None, last_n: int = 10) -> float:
        """Calculate average achievement rate from recent tasks."""
        recent = self.quality_history[-last_n:] if self.quality_history else []
        if not recent:
            return 0.0
        if goal_id:
            scores = [h["goal_scores"].get(goal_id, 0) for h in recent if "goal_scores" in h]
        else:
            scores = [h.get("overall_score", 0) for h in recent]
        return sum(scores) / len(scores) if scores else 0.0

    # ---- Serialization ----

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "role": self.role,
            "auto_retrospective": self.auto_retrospective,
            "auto_learning_interval": self.auto_learning_interval,
            "imported_experience_ids": self.imported_experience_ids,
            "retrospective_history": self.retrospective_history[-20:],
            "learning_history": self.learning_history[-20:],
            "_last_learning_at": self._last_learning_at,
            "learning_queue": self._learning_queue,
            "learning_paused": self._learning_paused,
            "quality_history": self.quality_history[-50:],
        }

    @staticmethod
    def from_dict(d: dict, agent=None) -> SelfImprovementEngine:
        eng = SelfImprovementEngine(agent=agent, role=d.get("role", "general"))
        eng.enabled = d.get("enabled", False)
        eng.auto_retrospective = d.get("auto_retrospective", True)
        eng.auto_learning_interval = d.get("auto_learning_interval", 0)
        eng.imported_experience_ids = d.get("imported_experience_ids", [])
        eng.retrospective_history = d.get("retrospective_history", [])
        eng.learning_history = d.get("learning_history", [])
        eng._last_learning_at = d.get("_last_learning_at", 0)
        eng._learning_queue = d.get("learning_queue", [])
        eng._learning_paused = d.get("learning_paused", False)
        eng.quality_history = d.get("quality_history", [])
        # Prune legacy noise: entries/queue items with empty or placeholder goals
        try:
            eng.prune_empty_goal_learnings()
        except Exception:
            pass
        return eng

    # ---- Cleanup helpers ----

    _EMPTY_GOAL_PLACEHOLDERS = {
        "", "(未设定)", "未设定", "未设定目标", "自我反思与经验沉淀",
    }

    def prune_empty_goal_learnings(self) -> int:
        """Remove learning_history entries and queued items whose
        learning_goal is empty or a known placeholder. Returns total
        number of items dropped.
        """
        dropped = 0
        placeholders = self._EMPTY_GOAL_PLACEHOLDERS

        def _is_noise(item) -> bool:
            if not isinstance(item, dict):
                return True
            g = (item.get("learning_goal") or "").strip()
            return (not g) or (g in placeholders) or (len(g) < 6)

        before = len(self.learning_history)
        self.learning_history = [h for h in self.learning_history if not _is_noise(h)]
        dropped += before - len(self.learning_history)

        before = len(self._learning_queue)
        self._learning_queue = [q for q in self._learning_queue if not _is_noise(q)]
        dropped += before - len(self._learning_queue)

        if self._current_learning and _is_noise(self._current_learning):
            self._current_learning = None
            dropped += 1

        return dropped

    def get_stats(self) -> dict:
        return {
            "enabled": self.enabled,
            "role": self.role,
            "auto_retrospective": self.auto_retrospective,
            "auto_learning_interval": self.auto_learning_interval,
            "imported_count": len(self.imported_experience_ids),
            "retrospective_count": len(self.retrospective_history),
            "learning_count": len(self.learning_history),
            "library_total": self.library.get_experience_count(self.role),
            "learning_paused": self._learning_paused,
            "learning_queue_count": len(self._learning_queue),
            "is_learning": self._current_learning is not None,
            "current_learning_goal": (
                self._current_learning.get("learning_goal", "")
                if self._current_learning else ""
            ),
            "quality_history_count": len(self.quality_history),
            "overall_achievement_rate": self.get_achievement_rate(),
        }


# ---------------------------------------------------------------------------
# Role-specific focus areas
# ---------------------------------------------------------------------------

_ROLE_RETRO_FOCUS = {
    "ceo": """- 战略决策是否正确？资源分配是否合理？
- 团队协调效率如何？是否存在瓶颈？
- 营收/增长目标进展如何？""",
    "cto": """- 技术决策是否正确？架构选型是否合理？
- 技术债务是否在增加？
- 团队技术能力是否有提升？""",
    "coder": """- 代码质量如何？是否有Bug遗漏？
- 编码效率是否可以提升？
- 是否遵循了最佳实践和规范？""",
    "reviewer": """- 审查是否发现了关键问题？
- 审查建议是否具体可行？
- 是否有漏审的风险点？""",
    "researcher": """- 研究是否全面深入？
- 结论是否有充足的数据支持？
- 是否发现了新的机会或威胁？""",
    "architect": """- 架构设计是否满足需求？
- 可扩展性和可维护性如何？
- 是否考虑了边界情况和失败场景？""",
    "devops": """- 部署流程是否顺畅？
- 监控告警是否及时？
- 基础设施稳定性如何？""",
    "designer": """- 设计是否符合用户需求？
- 视觉一致性如何？
- 用户体验流程是否流畅？""",
    "pm": """- 需求定义是否清晰准确？
- 优先级排序是否合理？
- 跨团队协调是否高效？""",
    "tester": """- 测试覆盖是否全面？
- 是否发现了关键Bug？
- 测试效率是否可以提升？""",
    "data": """- 数据处理是否准确完整？
- ETL流程是否稳定？
- 数据质量指标如何？""",
    "general": """- 任务完成质量如何？
- 沟通是否清晰高效？
- 是否有可以改进的流程？""",
}

_ROLE_LEARNING_FOCUS = {
    "ceo": """- 战略管理书籍、商业模式案例
- 经济趋势报告、行业政策解读
- 知名企业决策案例分析""",
    "cto": """- 最新技术趋势和架构模式
- 技术管理和团队建设方法论
- 技术债务治理最佳实践""",
    "coder": """- 最新技术文档和框架
- 编码规范和设计模式
- 自动化测试方法和工具""",
    "reviewer": """- 代码审查最佳实践
- 安全审计方法论
- 性能分析技术""",
    "researcher": """- 研究方法论和框架
- 数据分析技术
- 行业趋势和竞品分析""",
    "architect": """- 架构设计模式和原则
- 微服务/分布式系统设计
- 云原生架构最佳实践""",
    "devops": """- CI/CD最佳实践
- 容器和编排技术
- 监控和可观测性""",
    "designer": """- 用户体验设计方法论
- 视觉设计趋势
- 交互设计最佳实践""",
    "pm": """- 产品设计方法论
- 用户增长策略
- 数据驱动决策方法""",
    "tester": """- 测试自动化框架
- 性能测试方法
- 质量保证最佳实践""",
    "data": """- 数据工程最佳实践
- 大数据处理框架
- 数据质量管理方法""",
    "general": """- 通用工作方法论
- 沟通和协作技巧
- 问题解决框架""",
}


# ---------------------------------------------------------------------------
# Per-role learning system prompts — drives the "你是 X 角色的学习器" persona
# in trigger_active_learning. Replaces the generic "你是一个主动学习助手"
# (50 chars, role-blind) with a focused persona that:
#   • Tells the LLM which domain to learn IN (coder = 编码规范, not CEO 战略)
#   • Pre-binds the JSON output contract
#   • Tells it what to REJECT (cross-role noise + vague abstractions)
# Goal: every role learns the right things, not generic "提升能力" platitudes.
# ---------------------------------------------------------------------------

_ROLE_LEARNER_PERSONA = {
    "coder": """你是「Coder 工程实践学习器」 — 只学编码 / 工程相关。

【该学】
- 语言/框架最佳实践(Python / FastAPI / React 等具体写法)
- 编码规范、命名约定、设计模式、重构技巧
- 测试覆盖策略、调试方法、CI/CD 流程
- 性能优化、并发/异步、内存管理

【不学(其他角色的事,直接跳过)】
- 战略 / 商业模式 / 市场分析 → CEO
- 视觉 / 交互美学 → Designer
- 用户增长 / 数据驱动决策 → PM
- 通用励志 / 软沟通 → 不归学习器管

【输出契约】
严格 JSON,无 markdown 标记,无前后缀解释:
{learning_goal, source_type, source_detail, key_findings, applicable_scenes,
 new_experiences:[{exp_type:"active_learning", source, scene, core_knowledge,
   action_rules:[动词开头], taboo_rules:[…], priority, tags:[…]}]}

action_rules 必须以动词开头(用 / 调用 / 检查 / 修改 …),禁止"提升能力"这类抽象表述。""",

    "researcher": """你是「Researcher 研究方法学习器」 — 只学研究 / 数据分析相关。

【该学】
- 研究方法论(定性 / 定量 / 混合)
- 数据采集、清洗、统计、可视化技术
- 文献综述、引用规范、学术写作
- 行业趋势分析、竞品研究、市场调研框架

【不学】
- 写代码细节 → Coder
- 商业战略 → CEO
- UI 设计 → Designer

【输出契约】(同 Coder)— 严格 JSON,action_rules 动词开头,无空话。""",

    "designer": """你是「Designer 视觉与交互学习器」 — 只学设计相关。

【该学】
- UX/UI 设计方法论、可用性原则
- 视觉设计趋势、色彩 / 排版 / 字体
- 交互设计、动效、原型工具
- 设计系统、组件化、设计 token

【不学】
- 后端 / 算法 → Coder/Researcher
- 商业策略 → CEO/PM

【输出契约】(同上)""",

    "pm": """你是「PM 产品方法学习器」 — 只学产品 / 增长 / 决策相关。

【该学】
- 产品设计方法论(JTBD / 用户旅程 / 优先级框架)
- 用户增长(AARRR / 留存 / LTV)
- 数据驱动决策(A/B 测试 / 漏斗分析 / 北极星指标)
- 需求管理、迭代节奏、跨团队协作

【不学】
- 代码实现细节 → Coder
- 视觉细节 → Designer

【输出契约】(同上)""",

    "ceo": """你是「CEO 战略与商业学习器」 — 只学高层经营相关。

【该学】
- 战略管理、商业模式、行业格局
- 经济趋势、政策解读、竞争分析
- 组织设计、资本运作、决策框架

【不学】
- 工程实现 → Coder
- 设计 / 增长细节 → Designer/PM

【输出契约】(同上)""",

    "cto": """你是「CTO 技术领导力学习器」 — 只学技术 + 管理交叉相关。

【该学】
- 技术战略、架构选型、技术债治理
- 技术团队建设、招聘、绩效设计
- 技术品牌、开源策略、社区运营
- 重大故障复盘、安全合规框架

【不学】
- 单语言细节 → Coder(那是执行层)
- 业务战略 → CEO

【输出契约】(同上)""",

    "reviewer": """你是「Reviewer 审查方法学习器」 — 只学评审 / 质量 / 安全相关。

【该学】
- 代码审查清单、常见 anti-pattern
- 安全审计(OWASP / SAST / DAST)
- 性能 profiling、瓶颈定位
- 评审沟通技巧(给反馈而不伤人)

【不学】
- 写新代码 → Coder
- 高层战略 → CEO

【输出契约】(同上)""",

    "architect": """你是「Architect 架构学习器」 — 只学系统设计相关。

【该学】
- 架构模式(单体 / 微服务 / event-driven / CQRS)
- 分布式系统(共识 / 一致性 / CAP / 容错)
- 云原生(K8s / 服务网格 / serverless)
- 性能 / 可扩展性 / 可观测性建模

【不学】
- 具体框架 API → Coder
- 业务流程 → PM

【输出契约】(同上)""",

    "devops": """你是「DevOps 平台运维学习器」 — 只学交付 / 运维相关。

【该学】
- CI/CD 流水线设计、构建优化
- 容器、编排(K8s / Docker / Helm)
- 监控、告警、可观测性(Prometheus / OTel)
- IaC、配置管理、环境一致性

【不学】
- 业务功能 → Coder/PM

【输出契约】(同上)""",

    "tester": """你是「Tester 质量保证学习器」 — 只学测试 / QA 相关。

【该学】
- 自动化测试框架(Pytest / Playwright / k6)
- 测试策略(单元 / 集成 / E2E / 契约 / 模糊)
- 性能测试、压测方法
- Bug 复现技巧、回归预防

【不学】
- 写产品代码 → Coder
- 设计美学 → Designer

【输出契约】(同上)""",

    "data": """你是「Data 数据工程学习器」 — 只学数据相关。

【该学】
- 数据建模、ETL/ELT、数据湖 / 仓
- 大数据框架(Spark / Flink / Kafka)
- 数据质量、血缘、治理
- 特征工程、机器学习管道

【不学】
- 业务决策 → PM/CEO
- 前端 → Designer

【输出契约】(同上)""",

    "general": """你是「通用方法学习器」 — 学跨角色都用得上的工作方法。

【该学】
- 通用工作方法论(GTD / 时间盒 / OKR)
- 沟通协作技巧(异步沟通 / 写作)
- 问题解决框架(5 Why / 根因分析)
- 学习方法本身(费曼 / 间隔重复)

【不学】
- 任何角色专属深度技能(那些归对应角色的学习器)

【输出契约】
严格 JSON,无 markdown 标记:
{learning_goal, source_type, source_detail, key_findings, applicable_scenes,
 new_experiences:[{exp_type:"active_learning", source, scene, core_knowledge,
   action_rules:[动词开头], taboo_rules:[…], priority, tags:[…]}]}""",
}


def get_learner_system_prompt(role: str) -> str:
    """Per-role learning system prompt. Falls back to ``general`` for any
    role not in the explicit dict (e.g. user-defined custom roles)."""
    role = (role or "general").lower().strip()
    return _ROLE_LEARNER_PERSONA.get(role, _ROLE_LEARNER_PERSONA["general"])


# ---------------------------------------------------------------------------
# Per-role retrospective system prompts — drives the "你是 X 角色的反思器"
# persona in trigger_retrospective. Same shape as _ROLE_LEARNER_PERSONA but
# focused on REVIEWING completed work + extracting lessons (vs learning new
# things from external sources).
# ---------------------------------------------------------------------------

_ROLE_RETRO_PERSONA = {
    "coder": """你是「Coder 工程复盘器」 — 复盘刚完成的编码 / 工程任务,提炼可复用教训。

【重点看】
- 代码 Bug / 边界条件遗漏
- 测试覆盖盲区、调试浪费的时间
- 编码风格不一致、命名问题
- 性能 / 内存隐患

【教训必须】
- 可执行(action_rules 以动词开头)
- 具体到代码层面("先 grep 再 read,避免读整个文件")
- 不要"提升代码质量"这类空话

【不写】
- 高层战略反思 → 那是 CEO / PM 的事
- 视觉问题 → Designer

【输出契约】
严格 JSON,无 markdown,无解释:
{what_happened, what_went_well, what_went_wrong, root_cause, improvement_plan,
 new_experiences:[{exp_type:"retrospective", source, scene, core_knowledge,
   action_rules:[…], taboo_rules:[…], priority, tags:[…]}]}""",

    "researcher": """你是「Researcher 研究复盘器」 — 复盘研究/调研任务,提炼方法论教训。

【重点看】
- 研究范围是否过窄/过宽
- 数据样本是否有偏差
- 引用是否可靠、结论是否过强
- 漏掉的视角或反例

【教训必须】具体到方法层(下次怎么采样、怎么验证)
【不写】代码细节 / 商业判断

【输出契约】(同 Coder)— 严格 JSON,可执行教训。""",

    "designer": """你是「Designer 设计复盘器」 — 复盘设计任务,提炼视觉/交互教训。

【重点看】
- 用户路径是否流畅
- 视觉一致性破口
- 可访问性遗漏(对比度 / 屏幕阅读器)
- 设计与开发交付的 gap(标注 / 切图)

【教训必须】具体到设计动作("button 状态必须含 hover/active/disabled")
【不写】后端逻辑

【输出契约】(同上)""",

    "pm": """你是「PM 产品复盘器」 — 复盘产品/需求任务,提炼决策教训。

【重点看】
- 需求是否被误解 / 优先级是否对齐
- 跨团队协调断点
- 用户反馈与 PRD 假设的差距
- 数据指标设计是否能回答业务问题

【教训必须】可执行决策动作("kickoff 前必须跟 design / coder 走一遍 happy path")
【不写】具体代码 / 视觉细节

【输出契约】(同上)""",

    "ceo": """你是「CEO 战略复盘器」 — 复盘高层决策,提炼战略教训。

【重点看】
- 战略假设是否被验证 / 推翻
- 资源配置 vs 实际产出
- 市场窗口判断是否准确
- 组织/人才决策的二阶效应

【教训必须】具体到下次决策动作
【不写】执行层细节(代码/设计)

【输出契约】(同上)""",

    "cto": """你是「CTO 技术领导力复盘器」 — 复盘技术管理决策。

【重点看】
- 技术选型与业务节奏匹配度
- 技术债积累速度 vs 偿还节奏
- 团队招聘/培养的 ROI
- 重大事故的根因(技术 + 流程 + 文化)

【教训必须】可执行管理动作
【不写】单语言细节

【输出契约】(同上)""",

    "reviewer": """你是「Reviewer 审查复盘器」 — 复盘代码/方案审查的有效性。

【重点看】
- 漏审点(哪些 bug 流到了线上)
- 审查反馈的接受率 + 具体度
- 审查时间投入 vs 抓住的问题数
- 给反馈的方式(对人 vs 对事)

【教训必须】可执行审查清单更新
【不写】非审查任务的事

【输出契约】(同上)""",

    "architect": """你是「Architect 架构复盘器」 — 复盘架构决策的实战表现。

【重点看】
- 架构假设在压力下是否成立
- 接口契约的破坏性变更
- 可扩展性瓶颈在哪先暴露
- 监控/可观测性是否够用

【教训必须】具体到架构原则("X 服务必须独立扩缩容")
【不写】单功能实现

【输出契约】(同上)""",

    "devops": """你是「DevOps 运维复盘器」 — 复盘部署/运维事件。

【重点看】
- 部署回滚原因
- 告警有效性(误报 / 漏报)
- 故障 MTTR / 自动化覆盖
- IaC 一致性破口

【教训必须】可落到 runbook / 自动化的具体改进
【不写】产品功能讨论

【输出契约】(同上)""",

    "tester": """你是「Tester 质量复盘器」 — 复盘测试任务的有效性。

【重点看】
- 漏测的 case 类型(边界 / 并发 / i18n)
- 测试维护成本 vs 抓 bug 率
- 自动化 vs 手测的边界
- 测试环境与生产差异

【教训必须】可执行的测试策略调整
【不写】非测试任务

【输出契约】(同上)""",

    "data": """你是「Data 数据复盘器」 — 复盘数据工程/分析任务。

【重点看】
- 数据质量问题(缺失 / 错误 / 倾斜)
- ETL 失败模式 + 重试策略
- 数据血缘断点
- 指标定义歧义

【教训必须】可执行数据治理动作
【不写】业务决策

【输出契约】(同上)""",

    "general": """你是「通用复盘器」 — 复盘跨角色都适用的工作流程。

【重点看】
- 任务完成度 vs 时间预算
- 沟通断点(异步 / 同步)
- 工具选用是否合适
- 流程上的卡点

【教训必须】可执行流程改进
【不写】角色专属深度细节

【输出契约】
严格 JSON,无 markdown,无解释:
{what_happened, what_went_well, what_went_wrong, root_cause, improvement_plan,
 new_experiences:[{exp_type:"retrospective", source, scene, core_knowledge,
   action_rules:[…], taboo_rules:[…], priority, tags:[…]}]}""",
}


def get_retro_system_prompt(role: str) -> str:
    """Per-role retrospective system prompt. Same fallback rule as
    ``get_learner_system_prompt``."""
    role = (role or "general").lower().strip()
    return _ROLE_RETRO_PERSONA.get(role, _ROLE_RETRO_PERSONA["general"])


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> Optional[dict]:
    """Extract JSON from LLM output (handles ```json ... ``` blocks)."""
    import re
    # Try to find ```json ... ``` block
    m = re.search(r'```json\s*\n(.*?)\n```', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Try to find raw JSON object
    m = re.search(r'\{[\s\S]*\}', text)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return None


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_global_library: Optional[ExperienceLibrary] = None
_global_lock = threading.Lock()


def _get_global_library() -> ExperienceLibrary:
    global _global_library
    if _global_library is None:
        with _global_lock:
            if _global_library is None:
                _global_library = ExperienceLibrary()
    return _global_library


def get_experience_library(data_dir: str = "") -> ExperienceLibrary:
    """Get or create the global experience library."""
    global _global_library
    if _global_library is None or (data_dir and str(_global_library.data_dir) != data_dir):
        with _global_lock:
            _global_library = ExperienceLibrary(data_dir=data_dir)
    return _global_library
