"""
ExecutionAnalyzer — 执行自动分析器 (P0)

参考 OpenSpace 的 post-execution analysis 机制:
任务执行完成后，自动分析对话历史和工具调用链，提取结构化洞察，
并将分析结果反馈到 GrowthTracker 养成系统。

闭环: 任务完成 → 自动分析 → 生成 execution_note + tool_issues + skill_judgments
     → 写入 GrowthTracker.growth_events → 更新 SkillProgress
"""
from __future__ import annotations
import re
import time
from dataclasses import dataclass, field
from typing import Any

from ..infra.logging import get_logger

logger = get_logger("tudou.execution_analyzer")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ToolIssue:
    """A single identified tool issue from execution analysis."""
    tool_name: str = ""
    issue_type: str = ""   # "error", "timeout", "wrong_args", "no_result", "repeated_fail"
    description: str = ""
    severity: str = "low"  # "low", "medium", "high"
    count: int = 1

    def to_dict(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "issue_type": self.issue_type,
            "description": self.description,
            "severity": self.severity,
            "count": self.count,
        }

    @staticmethod
    def from_dict(d: dict) -> ToolIssue:
        return ToolIssue(
            tool_name=d.get("tool_name", ""),
            issue_type=d.get("issue_type", ""),
            description=d.get("description", ""),
            severity=d.get("severity", "low"),
            count=d.get("count", 1),
        )


@dataclass
class SkillJudgment:
    """Assessment of whether a skill was effectively used."""
    skill_id: str = ""
    skill_applied: bool = False
    effectiveness: str = ""  # "effective", "partial", "unused", "counterproductive"
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "skill_id": self.skill_id,
            "skill_applied": self.skill_applied,
            "effectiveness": self.effectiveness,
            "note": self.note,
        }

    @staticmethod
    def from_dict(d: dict) -> SkillJudgment:
        return SkillJudgment(
            skill_id=d.get("skill_id", ""),
            skill_applied=d.get("skill_applied", False),
            effectiveness=d.get("effectiveness", ""),
            note=d.get("note", ""),
        )


@dataclass
class ExecutionAnalysis:
    """Structured analysis result for a single task execution."""
    task_id: str = ""
    agent_id: str = ""
    task_completed: bool = False
    auto_rating: int = 0          # 1-5 auto-estimated quality
    execution_note: str = ""      # natural language summary
    tool_issues: list[ToolIssue] = field(default_factory=list)
    skill_judgments: list[SkillJudgment] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    tool_call_count: int = 0
    error_count: int = 0
    total_duration: float = 0.0   # seconds
    analyzed_at: float = field(default_factory=time.time)
    # Inferred skill tags from execution (for auto-tagging tasks)
    inferred_skill_tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "task_completed": self.task_completed,
            "auto_rating": self.auto_rating,
            "execution_note": self.execution_note,
            "tool_issues": [t.to_dict() for t in self.tool_issues],
            "skill_judgments": [s.to_dict() for s in self.skill_judgments],
            "tools_used": self.tools_used,
            "tool_call_count": self.tool_call_count,
            "error_count": self.error_count,
            "total_duration": round(self.total_duration, 2),
            "analyzed_at": self.analyzed_at,
            "inferred_skill_tags": self.inferred_skill_tags,
        }

    @staticmethod
    def from_dict(d: dict) -> ExecutionAnalysis:
        return ExecutionAnalysis(
            task_id=d.get("task_id", ""),
            agent_id=d.get("agent_id", ""),
            task_completed=d.get("task_completed", False),
            auto_rating=d.get("auto_rating", 0),
            execution_note=d.get("execution_note", ""),
            tool_issues=[ToolIssue.from_dict(t) for t in d.get("tool_issues", [])],
            skill_judgments=[SkillJudgment.from_dict(s) for s in d.get("skill_judgments", [])],
            tools_used=d.get("tools_used", []),
            tool_call_count=d.get("tool_call_count", 0),
            error_count=d.get("error_count", 0),
            total_duration=d.get("total_duration", 0.0),
            analyzed_at=d.get("analyzed_at", time.time()),
            inferred_skill_tags=d.get("inferred_skill_tags", []),
        )


# ---------------------------------------------------------------------------
# Analyzer Engine
# ---------------------------------------------------------------------------

# Tool name → skill tag mapping (heuristic)
_TOOL_SKILL_MAP = {
    "bash": "shell",
    "read_file": "file_ops",
    "write_file": "file_ops",
    "edit_file": "code_editing",
    "search_files": "search",
    "glob_files": "search",
    "mcp_call": "mcp_integration",
    "web_fetch": "web_research",
    "team_create": "delegation",
    "send_message": "communication",
}


class ExecutionAnalyzer:
    """
    Analyzes completed chat/task executions by inspecting the agent's
    event log and message history. Produces structured ExecutionAnalysis
    that feeds into the GrowthTracker.

    This is a rule-based analyzer (no LLM call required) that extracts
    patterns from tool call sequences, errors, and outcomes.
    """

    def __init__(self):
        self._analyses: dict[str, ExecutionAnalysis] = {}  # task_id → analysis

    def analyze_chat_events(self, agent: Any, task_id: str = "",
                            start_time: float = 0.0) -> ExecutionAnalysis:
        """
        Analyze an agent's recent events to produce an ExecutionAnalysis.

        Args:
            agent: Agent instance with .events and .messages
            task_id: Optional task ID to associate (auto-generated if empty)
            start_time: Only analyze events after this timestamp

        Returns:
            ExecutionAnalysis with structured insights
        """
        if not task_id:
            task_id = f"chat_{int(time.time())}"

        analysis = ExecutionAnalysis(
            task_id=task_id,
            agent_id=getattr(agent, "id", ""),
        )

        events = getattr(agent, "events", [])
        if not events:
            analysis.execution_note = "No events to analyze"
            return analysis

        # Filter to relevant time window
        if start_time > 0:
            events = [e for e in events if e.timestamp >= start_time]

        if not events:
            analysis.execution_note = "No events in time window"
            return analysis

        # --- Extract tool calls and results ---
        tool_calls = []
        tool_results = []
        errors = []
        has_assistant_response = False
        first_ts = events[0].timestamp
        last_ts = events[-1].timestamp

        for evt in events:
            kind = evt.kind
            data = evt.data if isinstance(evt.data, dict) else {}

            if kind == "tool_call":
                tool_calls.append(data)
            elif kind == "tool_result":
                tool_results.append(data)
                result_text = str(data.get("result", ""))
                if result_text.startswith("Error"):
                    errors.append({
                        "tool": data.get("name", ""),
                        "error": result_text[:200],
                    })
            elif kind == "error":
                errors.append({"tool": "system", "error": str(data.get("error", ""))[:200]})
            elif kind == "message" and data.get("role") == "assistant":
                has_assistant_response = True

        analysis.tool_call_count = len(tool_calls)
        analysis.error_count = len(errors)
        analysis.total_duration = last_ts - first_ts

        # --- Determine tools used ---
        tools_used_counter: dict[str, int] = {}
        for tc in tool_calls:
            name = tc.get("name", "unknown")
            tools_used_counter[name] = tools_used_counter.get(name, 0) + 1
        analysis.tools_used = list(tools_used_counter.keys())

        # --- Identify tool issues ---
        tool_error_counter: dict[str, list[str]] = {}
        for err in errors:
            tool = err.get("tool", "unknown")
            if tool not in tool_error_counter:
                tool_error_counter[tool] = []
            tool_error_counter[tool].append(err.get("error", ""))

        for tool_name, errs in tool_error_counter.items():
            count = len(errs)
            # Determine severity
            severity = "low"
            if count >= 3:
                severity = "high"
            elif count >= 2:
                severity = "medium"

            # Determine issue type
            first_err = errs[0].lower()
            issue_type = "error"
            if "timeout" in first_err or "timed out" in first_err:
                issue_type = "timeout"
            elif "unknown tool" in first_err:
                issue_type = "wrong_args"
            elif "connection" in first_err or "refused" in first_err:
                issue_type = "connection_error"

            analysis.tool_issues.append(ToolIssue(
                tool_name=tool_name,
                issue_type=issue_type,
                description=errs[0][:150],
                severity=severity,
                count=count,
            ))

        # --- Check for repeated failures (same tool called 3+ times with errors) ---
        for tool_name, call_count in tools_used_counter.items():
            error_count = len(tool_error_counter.get(tool_name, []))
            if call_count >= 3 and error_count >= 2:
                # Check if already tracked
                existing = [ti for ti in analysis.tool_issues if ti.tool_name == tool_name]
                if not existing:
                    analysis.tool_issues.append(ToolIssue(
                        tool_name=tool_name,
                        issue_type="repeated_fail",
                        description=f"Tool '{tool_name}' called {call_count} times with {error_count} errors",
                        severity="high",
                        count=error_count,
                    ))

        # --- Infer skill tags from tools used ---
        skill_tags_set = set()
        for tool_name in analysis.tools_used:
            tag = _TOOL_SKILL_MAP.get(tool_name)
            if tag:
                skill_tags_set.add(tag)
        # Also infer from bash commands
        for tc in tool_calls:
            if tc.get("name") == "bash":
                cmd = str(tc.get("arguments", {}).get("command", ""))
                if any(kw in cmd for kw in ["git ", "commit", "branch", "merge"]):
                    skill_tags_set.add("git")
                if any(kw in cmd for kw in ["python", "pip", "pytest"]):
                    skill_tags_set.add("python")
                if any(kw in cmd for kw in ["npm", "node", "yarn"]):
                    skill_tags_set.add("javascript")
                if any(kw in cmd for kw in ["docker", "kubectl"]):
                    skill_tags_set.add("devops")
                if any(kw in cmd for kw in ["curl", "wget", "http"]):
                    skill_tags_set.add("web_research")
        analysis.inferred_skill_tags = sorted(skill_tags_set)

        # --- Determine completion and auto-rating ---
        analysis.task_completed = has_assistant_response and analysis.error_count == 0

        # Auto-rating heuristic:
        # 5: No errors, task completed, used tools effectively
        # 4: Minor issues but completed
        # 3: Completed with some errors
        # 2: Partially completed, significant errors
        # 1: Failed or no meaningful output
        if not has_assistant_response:
            analysis.auto_rating = 1
            analysis.task_completed = False
        elif analysis.error_count == 0:
            if analysis.tool_call_count > 0:
                analysis.auto_rating = 5
            else:
                analysis.auto_rating = 4  # Simple Q&A, no tools needed
        elif analysis.error_count <= 1:
            analysis.auto_rating = 4
            analysis.task_completed = True
        elif analysis.error_count <= 3:
            analysis.auto_rating = 3
            analysis.task_completed = True
        else:
            high_severity = sum(1 for ti in analysis.tool_issues if ti.severity == "high")
            if high_severity >= 2:
                analysis.auto_rating = 2
                analysis.task_completed = False
            else:
                analysis.auto_rating = 3
                analysis.task_completed = True

        # --- Generate execution note ---
        parts = []
        if analysis.task_completed:
            parts.append(f"任务完成 (auto_rating={analysis.auto_rating}/5)")
        else:
            parts.append(f"任务未完成 (auto_rating={analysis.auto_rating}/5)")

        if analysis.tool_call_count > 0:
            parts.append(f"调用了 {analysis.tool_call_count} 次工具: {', '.join(analysis.tools_used[:5])}")

        if analysis.error_count > 0:
            parts.append(f"发生 {analysis.error_count} 个错误")
            for ti in analysis.tool_issues[:3]:
                parts.append(f"  - {ti.tool_name}: {ti.issue_type} ({ti.severity})")

        if analysis.inferred_skill_tags:
            parts.append(f"涉及技能: {', '.join(analysis.inferred_skill_tags)}")

        parts.append(f"耗时 {analysis.total_duration:.1f}s")
        analysis.execution_note = "; ".join(parts)

        # Cache
        self._analyses[task_id] = analysis
        logger.info("ExecutionAnalyzer: analyzed task %s → rating=%d, tools=%d, errors=%d",
                     task_id, analysis.auto_rating, analysis.tool_call_count, analysis.error_count)

        return analysis

    def get_analysis(self, task_id: str) -> ExecutionAnalysis | None:
        return self._analyses.get(task_id)

    def get_recent_analyses(self, limit: int = 20) -> list[ExecutionAnalysis]:
        analyses = sorted(self._analyses.values(),
                          key=lambda a: a.analyzed_at, reverse=True)
        return analyses[:limit]

    def to_dict(self) -> dict:
        return {
            "analyses": {k: v.to_dict() for k, v in self._analyses.items()},
        }

    @staticmethod
    def from_dict(d: dict) -> ExecutionAnalyzer:
        ea = ExecutionAnalyzer()
        for k, v in d.get("analyses", {}).items():
            ea._analyses[k] = ExecutionAnalysis.from_dict(v)
        return ea


# ---------------------------------------------------------------------------
# Integration: analyze + feed into GrowthTracker
# ---------------------------------------------------------------------------

def analyze_and_grow(agent: Any, task_id: str = "",
                     start_time: float = 0.0) -> ExecutionAnalysis:
    """
    Convenience function: analyze execution → auto-feed GrowthTracker.

    This is the main integration point. Call after each chat/task completes.
    Returns the analysis and updates agent.growth_tracker with events.
    """
    # Get or create analyzer on agent
    if not hasattr(agent, '_execution_analyzer') or agent._execution_analyzer is None:
        agent._execution_analyzer = ExecutionAnalyzer()

    analyzer: ExecutionAnalyzer = agent._execution_analyzer
    analysis = analyzer.analyze_chat_events(agent, task_id, start_time)

    # Feed into GrowthTracker
    growth_tracker = getattr(agent, 'growth_tracker', None)
    if growth_tracker is None:
        return analysis

    # Auto-tag: if task exists, enrich its skill_tags
    tasks = getattr(agent, 'tasks', [])
    matched_task = None
    for t in tasks:
        if t.id == task_id:
            matched_task = t
            break

    if matched_task and analysis.inferred_skill_tags:
        # Merge inferred tags with existing
        existing = set(matched_task.skill_tags or [])
        existing.update(analysis.inferred_skill_tags)
        matched_task.skill_tags = sorted(existing)

    # Generate growth events from analysis
    events = []

    # 1. Record as auto-analysis event
    events.append({
        "ts": time.time(),
        "type": "auto_analysis",
        "task_id": analysis.task_id,
        "auto_rating": analysis.auto_rating,
        "task_completed": analysis.task_completed,
        "tool_count": analysis.tool_call_count,
        "error_count": analysis.error_count,
        "note": analysis.execution_note[:200],
    })

    # 2. Update skills based on auto-rating (if user hasn't manually rated)
    if matched_task and matched_task.rating == 0:
        # Use auto_rating as a softer signal (half weight)
        skill_tags = matched_task.skill_tags or analysis.inferred_skill_tags or ["general"]
        for skill_id in skill_tags:
            sp = growth_tracker.get_or_create_skill(skill_id)
            # Auto-analysis uses softer scoring: rating scaled down
            soft_rating = max(1, analysis.auto_rating - 1)  # auto=5→4, auto=4→3, etc.
            result = sp.apply_feedback(soft_rating)
            if result["proficiency_gain"] > 0:
                events.append({
                    "ts": time.time(),
                    "type": "auto_skill_growth",
                    "skill": skill_id,
                    "gain": result["proficiency_gain"],
                    "level": result["new_level"],
                    "source": "auto_analysis",
                    "auto_rating": analysis.auto_rating,
                })
                if result["leveled_up"]:
                    events.append({
                        "ts": time.time(),
                        "type": "level_up",
                        "skill": skill_id,
                        "new_level": result["new_level"],
                        "source": "auto_analysis",
                    })

    # 3. Record tool issues as learning events
    for ti in analysis.tool_issues:
        if ti.severity in ("medium", "high"):
            events.append({
                "ts": time.time(),
                "type": "tool_issue",
                "tool": ti.tool_name,
                "issue_type": ti.issue_type,
                "severity": ti.severity,
                "description": ti.description[:100],
            })

    # Write events to growth tracker
    growth_tracker.growth_events.extend(events)
    if len(growth_tracker.growth_events) > 500:
        growth_tracker.growth_events = growth_tracker.growth_events[-400:]

    # Increment task count
    growth_tracker.total_tasks_completed += 1

    # ---- CLOSED-LOOP: auto-enqueue learning goals from analysis findings ----
    # When the analyzer spots a low rating or a high-severity tool issue,
    # push a concrete learning goal into the self-improvement queue so the
    # growth engine can act on it later. This turns a passive analyzer into
    # a feedback loop: analysis → learning plan → experience sedimentation.
    try:
        self_imp = getattr(agent, 'self_improvement', None)
        if self_imp is not None and hasattr(self_imp, 'queue_learning'):
            queued_goals: list[str] = []

            # (a) Low auto-rating → goal derived from skill tags + note
            if analysis.auto_rating <= 2 and not analysis.task_completed:
                tags = (analysis.inferred_skill_tags or ["general"])[:3]
                goal = f"提升任务 {task_id or '近期任务'} 中的能力: {'、'.join(tags)}"
                gap = analysis.execution_note[:200] or "任务评分低，需复盘根因"
                try:
                    self_imp.queue_learning(learning_goal=goal, knowledge_gap=gap)
                    queued_goals.append(goal)
                except ValueError:
                    pass  # goal too vague, skip

            # (b) High-severity tool issues → one goal per unique tool
            seen_tools: set[str] = set()
            for ti in analysis.tool_issues:
                if ti.severity != "high":
                    continue
                if ti.tool_name in seen_tools:
                    continue
                seen_tools.add(ti.tool_name)
                goal = (
                    f"修正工具使用错误: {ti.tool_name} — {ti.issue_type}"
                )
                gap = (ti.description or "")[:200]
                try:
                    self_imp.queue_learning(learning_goal=goal, knowledge_gap=gap)
                    queued_goals.append(goal)
                except ValueError:
                    pass

            if queued_goals:
                events.append({
                    "ts": time.time(),
                    "type": "learning_enqueued",
                    "source": "auto_analysis",
                    "count": len(queued_goals),
                    "goals": queued_goals[:5],
                })
                logger.info(
                    "analyze_and_grow: enqueued %d learning goals from analysis",
                    len(queued_goals),
                )
    except Exception as _loop_err:
        logger.debug("closed-loop learning enqueue skipped: %s", _loop_err)

    logger.info("analyze_and_grow: agent=%s task=%s auto_rating=%d events=%d",
                getattr(agent, 'name', '?'), task_id,
                analysis.auto_rating, len(events))

    return analysis
