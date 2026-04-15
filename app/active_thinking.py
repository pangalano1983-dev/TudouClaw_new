"""
Active Thinking Engine — 主动思考引擎

让 Agent 具备自主思考能力：不被动等待指令，按照角色职责主动分析、发现问题、
提出方案、反思优化。

架构：
    ActiveThinkingEngine (per-agent)
        ├── 7步思考循环 (Seven-Step Thinking Loop)
        ├── 4种触发机制 (Four Trigger Types)
        ├── 思考历史记录 (Thinking History)
        └── 思考结果注入 (Result Injection into Agent Context)

触发机制：
    1. 时间驱动 — 定时触发（如每小时、每天）
    2. 状态变化 — 关键指标变化时触发
    3. 目标差距 — 发现目标与现实差距时触发
    4. 信息缺口 — 发现知识空白时触发

使用：
    engine = ActiveThinkingEngine(agent, role="coder")
    engine.enable()

    # 手动触发一次思考
    result = engine.think_now(trigger="manual")

    # 定时触发（由 scheduler 调用）
    result = engine.think_now(trigger="time_driven",
                              context="Daily standup analysis")
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("tudou.active_thinking")

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ThinkingResult:
    """一次主动思考的完整结果。"""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    agent_id: str = ""
    agent_name: str = ""
    role: str = ""
    trigger: str = "manual"  # manual | time_driven | state_change | goal_gap | info_gap
    trigger_context: str = ""  # 触发上下文

    # 7步思考循环结果
    step1_goal: str = ""        # 我当前负责的目标是什么？
    step2_gap: str = ""         # 现状距离目标还差多少？
    step3_problem: str = ""     # 现在最大的问题/机会是什么？
    step4_actions: str = ""     # 我能做哪3件事改善？
    step5_best_action: str = "" # 哪件事性价比最高、最快见效？
    step6_execution: str = ""   # 执行方案/结果
    step7_reflection: str = ""  # 反思：效果如何？下次怎么更好？

    # 元数据
    raw_output: str = ""        # LLM 完整原始输出
    created_at: float = field(default_factory=time.time)
    duration_secs: float = 0.0  # 思考耗时
    quality_score: int = 0      # 0-100 自评分数

    # 行动追踪
    proposed_actions: list[str] = field(default_factory=list)
    executed_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "role": self.role,
            "trigger": self.trigger,
            "trigger_context": self.trigger_context,
            "step1_goal": self.step1_goal,
            "step2_gap": self.step2_gap,
            "step3_problem": self.step3_problem,
            "step4_actions": self.step4_actions,
            "step5_best_action": self.step5_best_action,
            "step6_execution": self.step6_execution,
            "step7_reflection": self.step7_reflection,
            "raw_output": self.raw_output[:2000],
            "created_at": self.created_at,
            "duration_secs": self.duration_secs,
            "quality_score": self.quality_score,
            "proposed_actions": self.proposed_actions,
            "executed_actions": self.executed_actions,
        }

    @staticmethod
    def from_dict(d: dict) -> ThinkingResult:
        r = ThinkingResult()
        for k, v in d.items():
            if hasattr(r, k):
                setattr(r, k, v)
        return r

    def summary(self) -> str:
        """生成思考摘要（一段话）。"""
        parts = []
        if self.step3_problem:
            parts.append(f"核心问题: {self.step3_problem[:100]}")
        if self.step5_best_action:
            parts.append(f"最佳行动: {self.step5_best_action[:100]}")
        if self.step7_reflection:
            parts.append(f"反思: {self.step7_reflection[:100]}")
        return " | ".join(parts) if parts else "(空思考)"


@dataclass
class ThinkingConfig:
    """主动思考配置。"""
    enabled: bool = False

    # 触发配置
    time_interval_minutes: int = 60   # 时间驱动间隔（分钟）
    auto_think_on_idle: bool = True   # Agent 空闲时自动思考
    idle_threshold_minutes: int = 30  # 空闲多久后触发

    # 思考深度
    max_thinking_tokens: int = 2000   # LLM 生成上限
    thinking_temperature: float = 0.8 # 略高温度，鼓励创造性思考
    include_context: bool = True      # 是否注入当前任务/数据上下文

    # 历史
    max_history: int = 50             # 保留最近 N 次思考

    # 自动执行
    auto_execute_actions: bool = False # 是否自动执行思考产生的行动
    require_approval: bool = True      # 行动是否需要审批

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "time_interval_minutes": self.time_interval_minutes,
            "auto_think_on_idle": self.auto_think_on_idle,
            "idle_threshold_minutes": self.idle_threshold_minutes,
            "max_thinking_tokens": self.max_thinking_tokens,
            "thinking_temperature": self.thinking_temperature,
            "include_context": self.include_context,
            "max_history": self.max_history,
            "auto_execute_actions": self.auto_execute_actions,
            "require_approval": self.require_approval,
        }

    @staticmethod
    def from_dict(d: dict) -> ThinkingConfig:
        c = ThinkingConfig()
        for k, v in d.items():
            if hasattr(c, k):
                setattr(c, k, v)
        return c


# ---------------------------------------------------------------------------
# 7步思考循环 Prompt 构建
# ---------------------------------------------------------------------------

_THINKING_LOOP_PROMPT = """你正在执行【主动思考循环】。不需要等待用户指令，你自己主动分析和思考。

请严格按照以下7步循环输出你的思考结果：

## 第1步：目标确认
我当前负责的目标是什么？（列出你角色范围内最重要的1-3个目标）

## 第2步：差距评估
现状距离目标还差多少？（用具体指标、事实描述，不要含糊）

## 第3步：问题/机会发现
现在最大的问题或机会是什么？（深度分析根本原因，不停留在表面）

## 第4步：行动方案
我能做哪3件事来改善？（具体可执行的方案，不是空话）

## 第5步：最优选择
哪件事性价比最高、最快见效？（给出理由）

## 第6步：执行方案
立刻执行或提出详细方案（如果需要审批，说明需要谁审批什么）

## 第7步：反思优化
预测执行效果，以及下次如何做得更好？

---
要求：
- 禁止空泛回答，每一步都要具体
- 结合你的角色职责和当前上下文
- 如果发现需要其他角色协助，明确说出来
- 最后用 JSON 格式输出你提议的行动列表：
```json
{"proposed_actions": ["行动1", "行动2", "行动3"]}
```
"""

# Role-specific thinking focus prompts
_ROLE_THINKING_FOCUS: dict[str, str] = {
    "ceo": (
        "你是 CEO，关注：公司战略、营收利润、增长机会、风险管控、资源配置、团队效能。\n"
        "思考重点：公司现在最大的战略风险是什么？增长是否在放缓？资源是否分配合理？"
    ),
    "cto": (
        "你是 CTO，关注：技术方向、架构健康、工程文化、创新投入、技术债务、安全态势。\n"
        "思考重点：当前技术架构能支撑未来6个月的需求吗？有哪些技术债务必须尽快还？"
    ),
    "coder": (
        "你是开发工程师，关注：代码质量、Bug率、系统稳定性、开发效率、测试覆盖。\n"
        "思考重点：最近哪些代码容易出Bug？架构有没有耦合问题？如何提升代码质量？"
    ),
    "reviewer": (
        "你是代码审查员，关注：代码质量趋势、常见错误模式、安全漏洞、团队规范一致性。\n"
        "思考重点：团队代码中有哪些反复出现的问题？代码规范是否在退化？"
    ),
    "researcher": (
        "你是研究员，关注：技术前沿、竞品动态、行业趋势、团队知识盲区。\n"
        "思考重点：有哪些新技术/趋势值得关注？竞品最近有什么动作？团队缺少什么知识？"
    ),
    "architect": (
        "你是架构师，关注：系统架构健康、扩展性、可维护性、服务边界、数据流。\n"
        "思考重点：当前架构的最大瓶颈在哪里？哪些服务需要重构或拆分？"
    ),
    "devops": (
        "你是运维工程师，关注：系统可靠性、部署效率、监控覆盖、安全加固、成本优化。\n"
        "思考重点：最近有哪些故障隐患？部署流程是否够快够安全？监控有没有盲区？"
    ),
    "designer": (
        "你是设计师，关注：用户体验、设计一致性、可访问性、用户反馈。\n"
        "思考重点：用户在哪些地方体验最差？设计系统是否一致？有没有可访问性问题？"
    ),
    "pm": (
        "你是产品经理，关注：用户满意度、功能采纳率、流失原因、需求优先级。\n"
        "思考重点：用户最大的痛点是什么？最近的功能上线效果如何？下一步该做什么？"
    ),
    "tester": (
        "你是测试工程师，关注：测试覆盖率、回归风险、不稳定测试、发布质量。\n"
        "思考重点：测试覆盖率的薄弱点在哪里？有哪些高风险区域缺少测试？"
    ),
    "data": (
        "你是数据工程师，关注：数据质量、管道可靠性、数据时效性、治理合规。\n"
        "思考重点：数据质量有没有问题？管道有没有故障风险？有没有洞察机会？"
    ),
    "marketer": (
        "你是市场人员，关注：用户痛点、竞品弱点、市场趋势、获客效率、品牌差异化。\n"
        "思考重点：用户有哪些未被满足的需求？竞品的盲区在哪里？哪个渠道ROI最高？"
    ),
    "general": (
        "你是通用助手，关注：待办任务、阻塞项、流程效率、跨团队协调。\n"
        "思考重点：有什么待办事项被忽略了？有什么流程可以改进？团队需要什么支持？"
    ),
}


def build_thinking_prompt(role: str, trigger: str = "manual",
                          context: str = "",
                          role_template: str = "") -> str:
    """构建完整的主动思考 prompt。"""
    parts = []

    # 角色聚焦
    focus = _ROLE_THINKING_FOCUS.get(role, _ROLE_THINKING_FOCUS["general"])
    parts.append(focus)

    # 触发上下文
    trigger_labels = {
        "manual": "手动触发",
        "time_driven": "定时触发（时间驱动）",
        "state_change": "状态变化触发",
        "goal_gap": "目标差距触发",
        "info_gap": "信息缺口触发",
        "idle": "空闲触发",
    }
    parts.append(f"\n【触发原因】{trigger_labels.get(trigger, trigger)}")

    # 额外上下文
    if context:
        parts.append(f"\n【当前上下文】\n{context[:2000]}")

    # 角色专属模板（从 active_thinking_*.md 加载）
    if role_template:
        parts.append(f"\n【角色思考模板参考】\n{role_template[:3000]}")

    # 7步循环
    parts.append(f"\n{_THINKING_LOOP_PROMPT}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# ActiveThinkingEngine — 主动思考引擎
# ---------------------------------------------------------------------------

class ActiveThinkingEngine:
    """Per-agent active thinking engine.

    Manages the thinking loop, trigger detection, history, and
    result injection back into the agent's context.
    """

    def __init__(self, agent: Any = None, role: str = ""):
        self.agent = agent
        self.role = role or (agent.role if agent else "general")
        self.config = ThinkingConfig()
        self.history: list[ThinkingResult] = []
        self._lock = threading.Lock()
        self._last_think_time: float = 0.0
        self._role_template: str = ""  # Cached from file

        # Load role-specific template
        self._load_role_template()

    def _load_role_template(self):
        """Load the active_thinking_*.md template for this role."""
        try:
            base = os.path.join(os.path.dirname(__file__),
                                "static", "templates", "thinking")
            path = os.path.join(base, f"active_thinking_{self.role}.md")
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as f:
                    self._role_template = f.read()
            else:
                # Fallback to general
                path = os.path.join(base, "active_thinking_general.md")
                if os.path.isfile(path):
                    with open(path, "r", encoding="utf-8") as f:
                        self._role_template = f.read()
        except Exception as e:
            logger.warning("Failed to load thinking template for %s: %s",
                           self.role, e)

    def enable(self, **kwargs):
        """Enable active thinking with optional config overrides."""
        self.config.enabled = True
        for k, v in kwargs.items():
            if hasattr(self.config, k):
                setattr(self.config, k, v)
        logger.info("Active thinking enabled for agent %s (role=%s)",
                     getattr(self.agent, 'name', '?'), self.role)

    def disable(self):
        """Disable active thinking."""
        self.config.enabled = False

    def should_think(self) -> tuple[bool, str]:
        """Check if it's time to think. Returns (should_think, trigger_type)."""
        if not self.config.enabled:
            return False, ""

        now = time.time()

        # Time-driven: interval elapsed
        if self._last_think_time > 0:
            elapsed_min = (now - self._last_think_time) / 60
            if elapsed_min >= self.config.time_interval_minutes:
                return True, "time_driven"
        elif self._last_think_time == 0 and self.config.enabled:
            # First time — trigger initial thinking
            return True, "time_driven"

        # Idle-driven: agent has been idle
        if self.config.auto_think_on_idle and self.agent:
            from .agent import AgentStatus
            if self.agent.status == AgentStatus.IDLE:
                # Check last activity
                last_msg_time = 0.0
                if self.agent.messages:
                    last_msg = self.agent.messages[-1]
                    # Rough: use created_at or last event time
                    last_msg_time = getattr(self.agent, '_last_save_time', 0)
                idle_min = (now - max(last_msg_time,
                                      self._last_think_time)) / 60
                if idle_min >= self.config.idle_threshold_minutes:
                    return True, "idle"

        return False, ""

    def think_now(self, trigger: str = "manual",
                  context: str = "") -> ThinkingResult:
        """Execute one thinking cycle. Calls agent.chat() internally.

        This is the core method — builds a thinking prompt, sends it to the
        agent's LLM, parses the result, and stores it.
        """
        with self._lock:
            start = time.time()
            result = ThinkingResult(
                agent_id=getattr(self.agent, 'id', ''),
                agent_name=getattr(self.agent, 'name', ''),
                role=self.role,
                trigger=trigger,
                trigger_context=context,
            )

            # Build context from agent state
            agent_context = context
            if self.config.include_context and self.agent:
                agent_context = self._gather_agent_context(context)

            # Build prompt
            prompt = build_thinking_prompt(
                role=self.role,
                trigger=trigger,
                context=agent_context,
                role_template=self._role_template,
            )

            # Call LLM via agent.chat()
            try:
                if self.agent:
                    raw = self.agent.chat(
                        prompt,
                        source="system:active_thinking",
                    )
                    result.raw_output = raw or ""
                    self._parse_output(result, raw or "")
                else:
                    result.raw_output = "(no agent attached)"
            except Exception as e:
                logger.error("Active thinking failed: %s", e, exc_info=True)
                result.raw_output = f"Error: {e}"

            result.duration_secs = time.time() - start
            self._last_think_time = time.time()

            # Store in history
            self.history.append(result)
            if len(self.history) > self.config.max_history:
                self.history = self.history[-self.config.max_history:]

            # Write to workspace file
            self._write_thinking_md(result)

            logger.info(
                "Active thinking completed: agent=%s trigger=%s duration=%.1fs",
                result.agent_name, trigger, result.duration_secs)

            return result

    def _gather_agent_context(self, extra: str = "") -> str:
        """Gather current agent context for thinking prompt."""
        parts = []
        if extra:
            parts.append(extra)

        agent = self.agent
        if not agent:
            return "\n".join(parts)

        # Current tasks
        pending = [t for t in agent.tasks
                   if t.status.value in ("todo", "in_progress")]
        if pending:
            task_lines = [f"- [{t.status.value}] {t.title}" for t in pending[:10]]
            parts.append("【当前任务】\n" + "\n".join(task_lines))

        # Recent events (last 5)
        if agent.events:
            recent = agent.events[-5:]
            event_lines = [f"- [{e.kind}] {str(e.data)[:100]}" for e in recent]
            parts.append("【最近事件】\n" + "\n".join(event_lines))

        # MCP capabilities
        mcps = getattr(agent.profile, 'mcp_servers', []) or []
        if mcps:
            mcp_names = [f"{m.name}({m.id})" for m in mcps]
            parts.append(f"【可用 MCP】{', '.join(mcp_names)}")

        # Previous thinking results (last 2 summaries)
        if self.history:
            prev = self.history[-2:]
            prev_lines = [f"- [{r.trigger}] {r.summary()}" for r in prev]
            parts.append("【上次思考摘要】\n" + "\n".join(prev_lines))

        return "\n".join(parts)

    def _parse_output(self, result: ThinkingResult, raw: str):
        """Parse the 7-step thinking output from LLM response."""
        # Extract sections by step headers
        import re

        step_map = {
            "1": "step1_goal",
            "2": "step2_gap",
            "3": "step3_problem",
            "4": "step4_actions",
            "5": "step5_best_action",
            "6": "step6_execution",
            "7": "step7_reflection",
        }

        # Match ## 第N步 or ## Step N patterns
        pattern = r'##\s*(?:第(\d)步|Step\s*(\d))[：:：]?\s*(.*?)(?=##\s*(?:第\d步|Step\s*\d)|```json|$)'
        for m in re.finditer(pattern, raw, re.DOTALL | re.IGNORECASE):
            num = m.group(1) or m.group(2)
            content = m.group(3).strip()
            attr = step_map.get(num)
            if attr:
                setattr(result, attr, content[:500])

        # Extract proposed actions JSON
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', raw, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                actions = data.get("proposed_actions", [])
                result.proposed_actions = [str(a)[:200] for a in actions[:10]]
            except (json.JSONDecodeError, TypeError):
                pass

        # Simple quality score based on completeness
        filled = sum(1 for attr in step_map.values()
                     if getattr(result, attr, ""))
        result.quality_score = int((filled / 7) * 100)

    def _write_thinking_md(self, result: ThinkingResult):
        """Write thinking result to agent's workspace as ActiveThinking.md."""
        if not self.agent:
            return
        try:
            ws = Path(getattr(self.agent, 'working_dir', ''))
            if not ws.exists():
                return
            ws_dir = ws / "workspace"
            ws_dir.mkdir(parents=True, exist_ok=True)

            md_path = ws_dir / "ActiveThinking.md"
            dt = datetime.fromtimestamp(result.created_at)

            # Build markdown
            lines = [
                f"# Active Thinking — {result.agent_name} ({result.role})",
                f"Last updated: {dt.strftime('%Y-%m-%d %H:%M')}",
                f"Trigger: {result.trigger} | Quality: {result.quality_score}/100",
                "",
                "## 第1步：目标确认",
                result.step1_goal or "(未填写)",
                "",
                "## 第2步：差距评估",
                result.step2_gap or "(未填写)",
                "",
                "## 第3步：问题/机会发现",
                result.step3_problem or "(未填写)",
                "",
                "## 第4步：行动方案",
                result.step4_actions or "(未填写)",
                "",
                "## 第5步：最优选择",
                result.step5_best_action or "(未填写)",
                "",
                "## 第6步：执行方案",
                result.step6_execution or "(未填写)",
                "",
                "## 第7步：反思优化",
                result.step7_reflection or "(未填写)",
                "",
            ]

            if result.proposed_actions:
                lines.append("## 提议行动")
                for i, a in enumerate(result.proposed_actions, 1):
                    lines.append(f"{i}. {a}")
                lines.append("")

            # History (last 5)
            if len(self.history) > 1:
                lines.append("## 历史思考 (最近5次)")
                for h in self.history[-6:-1]:
                    dt_h = datetime.fromtimestamp(h.created_at)
                    lines.append(f"- [{dt_h.strftime('%m-%d %H:%M')}] "
                                 f"[{h.trigger}] {h.summary()}")
                lines.append("")

            md_path.write_text("\n".join(lines), encoding="utf-8")
            logger.debug("Wrote ActiveThinking.md for %s", result.agent_name)
        except Exception as e:
            logger.warning("Failed to write ActiveThinking.md: %s", e)

    # ---- Persistence ----

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "config": self.config.to_dict(),
            "history": [r.to_dict() for r in self.history[-20:]],
            "last_think_time": self._last_think_time,
        }

    @staticmethod
    def from_dict(d: dict, agent: Any = None) -> ActiveThinkingEngine:
        eng = ActiveThinkingEngine(agent=agent, role=d.get("role", "general"))
        eng.config = ThinkingConfig.from_dict(d.get("config", {}))
        eng.history = [ThinkingResult.from_dict(r)
                       for r in d.get("history", [])]
        eng._last_think_time = d.get("last_think_time", 0.0)
        return eng

    def get_stats(self) -> dict:
        """Get thinking engine stats for API/UI."""
        return {
            "enabled": self.config.enabled,
            "role": self.role,
            "total_thinks": len(self.history),
            "last_think_time": self._last_think_time,
            "last_quality_score": (self.history[-1].quality_score
                                   if self.history else 0),
            "avg_quality_score": (
                sum(r.quality_score for r in self.history) // len(self.history)
                if self.history else 0
            ),
            "config": self.config.to_dict(),
        }
