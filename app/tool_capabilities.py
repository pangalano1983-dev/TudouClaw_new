"""Tool-tier classification: core vs capability-skill-gated.

Problem this module solves
--------------------------
Before this refactor every TOOL_DEFINITIONS entry was sent to every
agent's LLM regardless of what the agent was supposed to do. A fresh
meeting turn burned ~22k input tokens, most of it tool schemas the
agent would never call. User observation: "项目管理 那 5 个工具没授
权给 agent 啊" — confirmed: no gating layer existed.

Design
------
Three tiers, enforced by ``filter_tools_by_capability``:

  CORE                     always shipped to every agent's LLM
                           (agent identity / basic filesystem / web /
                            memory / scheduler / MCP bridge). Hardcoded.

  GLOBAL DEFAULT CAPS      admin-editable list of capability skills that
                           every agent gets implicitly. Admins set this
                           in ~/.tudou_claw/capability_defaults.json or
                           via Portal UI.

  PER-AGENT GRANTS         ``agent.granted_skills``. Extra capabilities
                           on top of the global defaults for this
                           specific agent.

Effective capabilities for an agent = GLOBAL_DEFAULTS ∪ granted_skills.
A tool ships iff it is CORE or its gating capability is in that set.

Why the two-layer (global + per-agent) split
--------------------------------------------
Without a global layer admins would have to toggle the same capability
on every single agent one-by-one. Without a per-agent layer the
one-off "only my PM agent should have project-management" cases
become impossible. Both knobs make sense; this module exposes both.

Why not map to existing workflow skill IDs
------------------------------------------
Workflow skills ("test-driven-development", "brainstorming") are
methodology docs, not capability unlocks — agents follow them but
don't gain new tools from granting them. Capability skills are a
different concept: granting them unlocks a bundle of TOOL_DEFINITIONS
entries. We use dedicated names to keep the two kinds separate.

Exception: `pptx-author` already exists AS a workflow skill AND would
be the natural capability-skill name for the two pptx tools. Reusing
is fine since the semantics line up (granting pptx-author = "this
agent should be able to create pptx"). We accept the overload.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger("tudou.capabilities")


# ── CORE tier ───────────────────────────────────────────────────────
# Shipped to every agent unconditionally. These are the tools that
# constitute an agent's basic identity rather than an optional
# capability — a filesystem-less agent, a web-less agent, or a
# memoryless agent is not really the kind of assistant users expect.
CORE_TOOLS: frozenset[str] = frozenset({
    # Filesystem read
    "read_file", "search_files", "glob_files",
    # Filesystem write + shell exec (core dev capability)
    "write_file", "edit_file", "bash",
    # Data processing utilities
    "datetime_calc", "json_process", "text_process",
    # Web basics (search + read)
    "web_search", "web_fetch",
    # Memory and knowledge (agent identity)
    "knowledge_lookup", "save_experience",
    "share_knowledge", "learn_from_peers",
    # UI visibility
    "plan_update", "emit_ui_block",
    # User scheduling interface ("remind me in 5 min")
    "task_update",
    # Inter-agent messaging (communication primitive)
    "send_message",
    # Must be core so granted skills are usable
    "get_skill_guide",
    # MCP bridge — MCP binding is its own authorization layer
    "mcp_call",
})


# ── SKILL-GATED tier ───────────────────────────────────────────────
# { capability_skill_name: [tool_name, ...] }
# An agent sees these tools only if the skill is in its granted_skills.
# Dict ordering preserved for reviewer readability.
CAPABILITY_SKILLS: dict[str, list[str]] = {
    "project-management": [
        "submit_deliverable",
        "create_goal",
        "update_goal_progress",
        "create_milestone",
        "update_milestone_status",
    ],
    "pptx-author": [
        "create_pptx",
        "create_pptx_advanced",
    ],
    "video-forge": [
        "create_video",
    ],
    "screenshot": [
        "web_screenshot",
        "desktop_screenshot",
    ],
    "http-client": [
        "http_request",
    ],
    "multi-agent": [
        "handoff_request",
        "team_create",
    ],
    "admin-ops": [
        "pip_install",
        "request_web_login",
        "propose_skill",
        "submit_skill",
    ],
}


# ── Computed reverse lookups ────────────────────────────────────────
# tool_name → capability_skill_name  (or None if core / unregistered)
_TOOL_TO_CAPABILITY: dict[str, str] = {}
for _skill, _tool_list in CAPABILITY_SKILLS.items():
    for _tool_name in _tool_list:
        _TOOL_TO_CAPABILITY[_tool_name] = _skill


# All capability-skill identifiers (for UI / migration).
CAPABILITY_SKILL_IDS: frozenset[str] = frozenset(CAPABILITY_SKILLS.keys())


def get_tool_capability(tool_name: str) -> Optional[str]:
    """Return the capability skill that gates this tool, or None if
    the tool is in the CORE tier (or not registered at all)."""
    return _TOOL_TO_CAPABILITY.get(tool_name)


def is_core_tool(tool_name: str) -> bool:
    """True if the tool is in the always-on CORE tier."""
    return tool_name in CORE_TOOLS


# ── Global default capability layer ────────────────────────────────
# Admin-editable file mapping name → list of capability skill ids that
# apply to EVERY agent implicitly. Lives alongside tool_denylist.json
# so users who configured one already know where to look for the other.
_DEFAULTS_FILENAME = "capability_defaults.json"

# Factory default: no global capabilities. Admin explicitly opts each
# one in via the UI (or by editing the file). We ship with NONE so
# token savings are immediate — the opposite of "grant everything and
# hope the admin revokes".
_FACTORY_DEFAULT_CAPABILITIES: list[str] = []


def _default_home() -> Path:
    """Resolve the data directory (~/.tudou_claw or $TUDOU_CLAW_HOME)."""
    home = os.environ.get("TUDOU_CLAW_HOME", "").strip()
    if home:
        return Path(home).expanduser().resolve()
    return Path.home() / ".tudou_claw"


def load_global_default_capabilities(path: Path | None = None) -> list[str]:
    """Load the admin-configured global default capability skill list.

    Never raises — missing file / malformed file both yield the
    factory default. Unknown capability names (not in CAPABILITY_SKILLS)
    are silently dropped with a warning, so a typo in the config file
    won't silently unlock the wrong thing.
    """
    target = path or (_default_home() / _DEFAULTS_FILENAME)
    if not target.is_file():
        return list(_FACTORY_DEFAULT_CAPABILITIES)
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(
            "capability_defaults.json unreadable (%s); falling back to none.", e)
        return list(_FACTORY_DEFAULT_CAPABILITIES)

    raw = data.get("defaults") or []
    if not isinstance(raw, list):
        return list(_FACTORY_DEFAULT_CAPABILITIES)

    cleaned: list[str] = []
    unknown: list[str] = []
    for entry in raw:
        name = str(entry).strip()
        if not name:
            continue
        if name in CAPABILITY_SKILLS:
            cleaned.append(name)
        else:
            unknown.append(name)
    if unknown:
        logger.warning(
            "capability_defaults.json has unknown names (ignored): %s",
            unknown,
        )
    return cleaned


def save_global_default_capabilities(
    caps: list[str], path: Path | None = None,
) -> None:
    """Persist the admin-configured global default capability list.

    Writes atomically (tmp + rename) so a crash mid-write can't corrupt
    the file. Unknown names rejected at write time.
    """
    target = path or (_default_home() / _DEFAULTS_FILENAME)
    target.parent.mkdir(parents=True, exist_ok=True)

    cleaned = []
    for entry in caps:
        name = str(entry).strip()
        if not name:
            continue
        if name not in CAPABILITY_SKILLS:
            raise ValueError(
                f"Unknown capability skill: {name!r}. "
                f"Valid: {sorted(CAPABILITY_SKILL_IDS)}"
            )
        cleaned.append(name)
    cleaned = sorted(set(cleaned))

    tmp = target.with_suffix(target.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump({"defaults": cleaned}, f, ensure_ascii=False, indent=2)
    os.replace(tmp, target)


def filter_tools_by_capability(
    tools_list: list[dict],
    granted_skills: list[str] | None,
    global_defaults: list[str] | None = None,
) -> list[dict]:
    """Apply the capability-tier filter.

    Keeps a tool iff ANY of:
      1. It is in CORE_TOOLS (always on).
      2. Its gating capability is in ``global_defaults`` (admin-wide).
      3. Its gating capability is in ``granted_skills`` (per-agent).
      4. It isn't classified at all (unknown-tool fail-open — admin
         can classify later without breaking things).

    If ``global_defaults`` is None, it's loaded from disk via
    ``load_global_default_capabilities()``. Pass an explicit empty list
    to disable the global layer in tests.
    """
    if global_defaults is None:
        global_defaults = load_global_default_capabilities()
    effective_caps = set(global_defaults) | set(granted_skills or ())
    kept: list[dict] = []
    for t in tools_list:
        name = t.get("function", {}).get("name", "")
        if name in CORE_TOOLS:
            kept.append(t)
            continue
        cap = _TOOL_TO_CAPABILITY.get(name)
        if cap is None:
            # Unknown tool — allow through. The admin can add it to the
            # classification tables later if they want gating.
            kept.append(t)
            continue
        if cap in effective_caps:
            kept.append(t)
    return kept


def sanity_check() -> tuple[set[str], set[str]]:
    """Dev helper: returns (tools_in_core_AND_capability, tools_missing_classification).

    Run from a script when adding new tools to catch drift between
    TOOL_DEFINITIONS and this module.
    """
    from . import tools as _tools_mod
    all_defined = {t["function"]["name"] for t in _tools_mod.TOOL_DEFINITIONS}
    both = CORE_TOOLS & set(_TOOL_TO_CAPABILITY)
    missing = all_defined - CORE_TOOLS - set(_TOOL_TO_CAPABILITY)
    return both, missing
