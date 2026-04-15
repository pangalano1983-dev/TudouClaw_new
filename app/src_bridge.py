"""
src_bridge.py — Bridge between src/ porting workspace and app/ runtime.

Integrates all src/ capabilities into the running Tudou Claws application:
- PortRuntime: intelligent prompt-to-agent routing
- ExecutionRegistry: mirrored tool/command metadata
- ToolPool: permission-aware tool surface assembly
- BootstrapGraph: system initialization stages
- CommandGraph: command categorization
- Setup/Context: workspace analysis and health info
- ParityAudit: codebase health check
- QueryEngine: session summary and transcript management
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Any

# Ensure src is importable
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from src.runtime import PortRuntime, RuntimeSession, RoutedMatch
from src.execution_registry import (
    ExecutionRegistry, MirroredCommand, MirroredTool,
    build_execution_registry,
)
from src.tool_pool import ToolPool, assemble_tool_pool
from src.permissions import ToolPermissionContext
from src.bootstrap_graph import BootstrapGraph, build_bootstrap_graph
from src.command_graph import CommandGraph, build_command_graph
from src.setup import WorkspaceSetup, SetupReport, run_setup, build_workspace_setup
from src.context import PortContext, build_port_context, render_context
from src.port_manifest import PortManifest, build_port_manifest
from src.parity_audit import run_parity_audit, ParityAuditResult
from src.query_engine import QueryEnginePort, QueryEngineConfig, TurnResult
from src.session_store import StoredSession, save_session, load_session
from src.cost_tracker import CostTracker
from src.costHook import apply_cost_hook
from src.history import HistoryLog, HistoryEvent
from src.transcript import TranscriptStore
from src.tools import (
    PORTED_TOOLS, build_tool_backlog, render_tool_index,
    find_tools as src_find_tools, tool_names as src_tool_names,
)
from src.commands import PORTED_COMMANDS, build_command_backlog
from src.system_init import build_system_init_message


# ---------------------------------------------------------------------------
# Singleton bridge instance
# ---------------------------------------------------------------------------

class SrcBridge:
    """
    Central bridge that lazily initializes and caches all src capabilities.
    Thread-safe singleton — call get_bridge() to access.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._runtime: PortRuntime | None = None
        self._registry: ExecutionRegistry | None = None
        self._bootstrap: BootstrapGraph | None = None
        self._command_graph: CommandGraph | None = None
        self._setup_report: SetupReport | None = None
        self._manifest: PortManifest | None = None
        self._context: PortContext | None = None
        self._query_engine: QueryEnginePort | None = None

    # ---- Lazy initialization ----

    @property
    def runtime(self) -> PortRuntime:
        if self._runtime is None:
            with self._lock:
                if self._runtime is None:
                    self._runtime = PortRuntime()
        return self._runtime

    @property
    def registry(self) -> ExecutionRegistry:
        if self._registry is None:
            with self._lock:
                if self._registry is None:
                    self._registry = build_execution_registry()
        return self._registry

    @property
    def bootstrap(self) -> BootstrapGraph:
        if self._bootstrap is None:
            self._bootstrap = build_bootstrap_graph()
        return self._bootstrap

    @property
    def command_graph(self) -> CommandGraph:
        if self._command_graph is None:
            self._command_graph = build_command_graph()
        return self._command_graph

    @property
    def setup_report(self) -> SetupReport:
        if self._setup_report is None:
            self._setup_report = run_setup()
        return self._setup_report

    @property
    def manifest(self) -> PortManifest:
        if self._manifest is None:
            self._manifest = build_port_manifest()
        return self._manifest

    @property
    def context(self) -> PortContext:
        if self._context is None:
            self._context = build_port_context()
        return self._context

    @property
    def query_engine(self) -> QueryEnginePort:
        if self._query_engine is None:
            self._query_engine = QueryEnginePort.from_workspace()
        return self._query_engine

    # ---- Routing: find best agent for a prompt ----

    def route_prompt(self, prompt: str, limit: int = 5) -> list[RoutedMatch]:
        """
        Use PortRuntime to find the best matching tools/commands for a prompt.
        Can be used to pick the best agent for a task.
        """
        return self.runtime.route_prompt(prompt, limit=limit)

    def route_to_agent_role(self, prompt: str,
                             agents: dict[str, Any]) -> str | None:
        """
        Route a user prompt to the best-suited agent based on tool/command matching.
        Returns agent_id or None.

        Strategy: match prompt keywords to agent roles and expertise.
        """
        matches = self.route_prompt(prompt, limit=10)
        if not matches:
            return None

        # Score each agent based on how well their role/expertise
        # aligns with the matched tools/commands
        agent_scores: dict[str, int] = {}
        for aid, agent in agents.items():
            score = 0
            role = getattr(agent, 'role', '').lower()
            expertise = [e.lower() for e in
                         getattr(getattr(agent, 'profile', None),
                                 'expertise', [])]
            name = getattr(agent, 'name', '').lower()

            for match in matches:
                # Check if agent's role/expertise matches the tool category
                hint = match.source_hint.lower()
                mname = match.name.lower()
                keywords = set(hint.split('/') + hint.split(' ')
                               + mname.split(' '))

                if role in keywords or any(e in hint for e in expertise):
                    score += match.score * 2
                if any(kw in name for kw in keywords if len(kw) > 2):
                    score += match.score

                # Role-based heuristics
                if match.kind == 'tool':
                    if 'bash' in mname and role in ('coder', 'devops'):
                        score += 3
                    if 'file' in mname and role in ('coder', 'reviewer'):
                        score += 2
                    if 'search' in mname and role == 'researcher':
                        score += 3
                    if 'test' in mname and role == 'tester':
                        score += 3

            if score > 0:
                agent_scores[aid] = score

        if not agent_scores:
            return None
        return max(agent_scores, key=agent_scores.get)

    # ---- Tool pool: permission-aware tool assembly ----

    def build_tool_pool(self, denied_tools: list[str] | None = None,
                         denied_prefixes: list[str] | None = None,
                         simple_mode: bool = False) -> ToolPool:
        """Build a permission-filtered tool pool."""
        ctx = None
        if denied_tools or denied_prefixes:
            ctx = ToolPermissionContext.from_iterables(
                deny_names=denied_tools,
                deny_prefixes=denied_prefixes,
            )
        return assemble_tool_pool(
            simple_mode=simple_mode,
            permission_context=ctx,
        )

    # ---- System info ----

    def get_system_info(self) -> dict:
        """Comprehensive system info for dashboard/API."""
        setup = self.setup_report
        ctx = self.context
        manifest = self.manifest
        cg = self.command_graph
        bg = self.bootstrap

        return {
            "python_version": setup.setup.python_version,
            "implementation": setup.setup.implementation,
            "platform": setup.setup.platform_name,
            "trusted": setup.trusted,
            "cwd": str(setup.cwd),
            "src_files": ctx.python_file_count,
            "test_files": ctx.test_file_count,
            "asset_files": ctx.asset_file_count,
            "archive_available": ctx.archive_available,
            "manifest_modules": len(manifest.top_level_modules),
            "mirrored_commands": len(PORTED_COMMANDS),
            "mirrored_tools": len(PORTED_TOOLS),
            "command_graph": {
                "builtins": len(cg.builtins),
                "plugin_like": len(cg.plugin_like),
                "skill_like": len(cg.skill_like),
            },
            "bootstrap_stages": len(bg.stages),
            "startup_steps": list(setup.setup.startup_steps()),
        }

    def get_parity_report(self) -> dict:
        """Run parity audit and return results."""
        result = run_parity_audit()
        return {
            "archive_present": result.archive_present,
            "root_file_coverage": result.root_file_coverage,
            "directory_coverage": result.directory_coverage,
            "total_file_ratio": result.total_file_ratio,
            "command_entry_ratio": result.command_entry_ratio,
            "tool_entry_ratio": result.tool_entry_ratio,
            "missing_root_targets": result.missing_root_targets,
            "missing_directory_targets": result.missing_directory_targets,
        }

    def get_system_init_message(self) -> str:
        """Build system initialization summary."""
        return build_system_init_message()

    def get_summary(self) -> str:
        """Get full workspace summary from QueryEngine."""
        return self.query_engine.render_summary()

    # ---- Session management ----

    def create_session_engine(self,
                              max_turns: int = 8,
                              max_budget: int = 2000) -> QueryEnginePort:
        """Create a fresh QueryEngine session for a workflow or agent."""
        config = QueryEngineConfig(
            max_turns=max_turns,
            max_budget_tokens=max_budget,
        )
        engine = QueryEnginePort.from_workspace()
        engine.config = config
        return engine

    def persist_engine_session(self, engine: QueryEnginePort,
                                directory: Path | None = None) -> str:
        """Persist a query engine session to disk."""
        return engine.persist_session()

    def restore_engine_session(self, session_id: str) -> QueryEnginePort:
        """Restore a previously saved query engine session."""
        return QueryEnginePort.from_saved_session(session_id)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_bridge: SrcBridge | None = None
_bridge_lock = threading.Lock()


def get_bridge() -> SrcBridge:
    """Get the global SrcBridge singleton."""
    global _bridge
    if _bridge is None:
        with _bridge_lock:
            if _bridge is None:
                _bridge = SrcBridge()
    return _bridge
