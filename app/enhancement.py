"""
Agent Enhancement Module — 让 Agent 在特定领域变得更专业、更聪明。

Architecture:
┌───────────────────────────────────────────────────────────┐
│                    AgentEnhancer                          │
│  ┌─────────────┐ ┌──────────────┐ ┌────────────────────┐ │
│  │ KnowledgeBase│ │ReasoningChain│ │   MemoryGraph      │ │
│  │ ·domain docs │ │ ·think steps │ │ ·learned patterns  │ │
│  │ ·best practs │ │ ·reflection  │ │ ·error→fix pairs   │ │
│  │ ·patterns    │ │ ·planning    │ │ ·success templates │ │
│  │ ·constraints │ │ ·evaluation  │ │ ·concept links     │ │
│  └─────────────┘ └──────────────┘ └────────────────────┘ │
│  ┌──────────────────────────────────────────────────────┐ │
│  │             DomainToolChain                          │ │
│  │ ·preferred tool sequences for domain tasks           │ │
│  │ ·auto-generated sub-agent templates                  │ │
│  └──────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────┘

Usage:
    enhancer = AgentEnhancer.for_domain("security_audit")
    enhanced_prompt = enhancer.enhance_system_prompt(base_prompt)
    pre_think = enhancer.pre_think(user_message)
    reflection = enhancer.reflect_on_result(user_message, result)
    enhancer.learn(interaction_record)
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("tudou.enhancement")

# ---------------------------------------------------------------------------
# Knowledge Base — 领域知识库
# ---------------------------------------------------------------------------

@dataclass
class KnowledgeEntry:
    """A single piece of domain knowledge."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    category: str = "general"        # pattern | constraint | best_practice | pitfall | reference
    title: str = ""
    content: str = ""
    tags: list[str] = field(default_factory=list)
    priority: int = 0                # higher = more important, injected first
    source: str = "admin"            # admin | learned | imported
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "category": self.category,
            "title": self.title, "content": self.content,
            "tags": self.tags, "priority": self.priority,
            "source": self.source, "created_at": self.created_at,
        }

    @staticmethod
    def from_dict(d: dict) -> KnowledgeEntry:
        return KnowledgeEntry(
            id=d.get("id", uuid.uuid4().hex[:10]),
            category=d.get("category", "general"),
            title=d.get("title", ""),
            content=d.get("content", ""),
            tags=d.get("tags", []),
            priority=d.get("priority", 0),
            source=d.get("source", "admin"),
            created_at=d.get("created_at", time.time()),
        )


class KnowledgeBase:
    """Domain knowledge store for an agent.

    Stores structured knowledge entries that get injected into the agent's
    context based on relevance to the current conversation.
    """

    def __init__(self):
        self.entries: dict[str, KnowledgeEntry] = {}

    def add(self, title: str, content: str, category: str = "general",
            tags: list[str] | None = None, priority: int = 0,
            source: str = "admin") -> KnowledgeEntry:
        entry = KnowledgeEntry(
            title=title, content=content, category=category,
            tags=tags or [], priority=priority, source=source,
        )
        self.entries[entry.id] = entry
        return entry

    def remove(self, entry_id: str) -> bool:
        return self.entries.pop(entry_id, None) is not None

    def search(self, query: str, limit: int = 10) -> list[KnowledgeEntry]:
        """Simple keyword search. Returns entries ranked by relevance + priority."""
        tokens = set(query.lower().split())
        scored = []
        for entry in self.entries.values():
            score = entry.priority
            text = f"{entry.title} {entry.content} {' '.join(entry.tags)}".lower()
            for t in tokens:
                if t in text:
                    score += 2
                if t in entry.title.lower():
                    score += 3
                if t in entry.tags:
                    score += 4
            if score > entry.priority:
                scored.append((score, entry))
        scored.sort(key=lambda x: -x[0])
        return [e for _, e in scored[:limit]]

    def get_by_category(self, category: str) -> list[KnowledgeEntry]:
        return sorted(
            [e for e in self.entries.values() if e.category == category],
            key=lambda e: -e.priority,
        )

    def render_for_prompt(self, query: str = "", max_chars: int = 4000) -> str:
        """Render knowledge entries into a prompt-injectable block.

        If query is provided, returns relevant entries. Otherwise returns
        high-priority entries by category.
        """
        if query:
            entries = self.search(query, limit=20)
        else:
            entries = sorted(self.entries.values(), key=lambda e: -e.priority)

        if not entries:
            return ""

        parts = ["<domain_knowledge>"]
        char_count = 0
        by_cat: dict[str, list[str]] = {}
        for e in entries:
            line = f"- [{e.category}] {e.title}: {e.content}"
            if char_count + len(line) > max_chars:
                break
            cat = e.category
            if cat not in by_cat:
                by_cat[cat] = []
            by_cat[cat].append(line)
            char_count += len(line)

        for cat, lines in by_cat.items():
            parts.append(f"\n## {cat.replace('_', ' ').title()}")
            parts.extend(lines)

        parts.append("</domain_knowledge>")
        return "\n".join(parts)

    def to_dict(self) -> dict:
        return {"entries": [e.to_dict() for e in self.entries.values()]}

    @staticmethod
    def from_dict(d: dict) -> KnowledgeBase:
        kb = KnowledgeBase()
        for ed in d.get("entries", []):
            entry = KnowledgeEntry.from_dict(ed)
            kb.entries[entry.id] = entry
        return kb


# ---------------------------------------------------------------------------
# Reasoning Chain — 思维链与反思引擎
# ---------------------------------------------------------------------------

@dataclass
class ReasoningStep:
    """A step in a reasoning pattern."""
    name: str
    instruction: str         # what the agent should think about at this step
    output_format: str = ""  # expected output format hint

    def to_dict(self) -> dict:
        return {"name": self.name, "instruction": self.instruction,
                "output_format": self.output_format}

    @staticmethod
    def from_dict(d: dict) -> ReasoningStep:
        return ReasoningStep(
            name=d.get("name", ""),
            instruction=d.get("instruction", ""),
            output_format=d.get("output_format", ""),
        )


@dataclass
class ReasoningPattern:
    """A reusable thinking pattern for a type of task."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    name: str = ""
    description: str = ""
    trigger_keywords: list[str] = field(default_factory=list)
    steps: list[ReasoningStep] = field(default_factory=list)
    reflection_prompt: str = ""
    priority: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name,
            "description": self.description,
            "trigger_keywords": self.trigger_keywords,
            "steps": [s.to_dict() for s in self.steps],
            "reflection_prompt": self.reflection_prompt,
            "priority": self.priority,
        }

    @staticmethod
    def from_dict(d: dict) -> ReasoningPattern:
        return ReasoningPattern(
            id=d.get("id", uuid.uuid4().hex[:10]),
            name=d.get("name", ""),
            description=d.get("description", ""),
            trigger_keywords=d.get("trigger_keywords", []),
            steps=[ReasoningStep.from_dict(s) for s in d.get("steps", [])],
            reflection_prompt=d.get("reflection_prompt", ""),
            priority=d.get("priority", 0),
        )


class ReasoningEngine:
    """Provides structured thinking patterns for domain-specific tasks.

    Instead of letting the agent reason freely, this engine provides
    step-by-step thinking frameworks that guide the agent through
    domain-appropriate reasoning paths.
    """

    def __init__(self):
        self.patterns: dict[str, ReasoningPattern] = {}

    def add_pattern(self, name: str, steps: list[dict],
                    trigger_keywords: list[str] | None = None,
                    reflection_prompt: str = "",
                    description: str = "") -> ReasoningPattern:
        pattern = ReasoningPattern(
            name=name,
            description=description,
            trigger_keywords=trigger_keywords or [],
            steps=[ReasoningStep(**s) if isinstance(s, dict) else s for s in steps],
            reflection_prompt=reflection_prompt,
        )
        self.patterns[pattern.id] = pattern
        return pattern

    def match_pattern(self, message: str) -> ReasoningPattern | None:
        """Find the best matching reasoning pattern for a user message."""
        tokens = set(message.lower().split())
        best = None
        best_score = 0
        for pattern in self.patterns.values():
            score = 0
            for kw in pattern.trigger_keywords:
                if kw.lower() in message.lower():
                    score += 3
                for t in tokens:
                    if t in kw.lower():
                        score += 1
            if score > best_score:
                best_score = score
                best = pattern
        return best if best_score > 0 else None

    def generate_pre_think(self, message: str) -> str:
        """Generate a pre-thinking prompt injection.

        This gets added BEFORE the user's message in the conversation,
        guiding the agent to think step-by-step.
        """
        pattern = self.match_pattern(message)
        if not pattern:
            return ""

        parts = [f"<thinking_framework name=\"{pattern.name}\">"]
        parts.append(f"任务类型识别: {pattern.description}")
        parts.append("请按以下步骤进行系统性思考:")
        for i, step in enumerate(pattern.steps, 1):
            parts.append(f"\n### Step {i}: {step.name}")
            parts.append(step.instruction)
            if step.output_format:
                parts.append(f"输出格式: {step.output_format}")
        parts.append("</thinking_framework>")
        return "\n".join(parts)

    def generate_reflection_prompt(self, message: str, result: str) -> str:
        """Generate a self-reflection prompt after task completion.

        This encourages the agent to evaluate its own output.
        """
        pattern = self.match_pattern(message)
        if pattern and pattern.reflection_prompt:
            reflection = pattern.reflection_prompt
        else:
            reflection = (
                "请回顾你的回答:\n"
                "1. 是否完整回答了用户的问题?\n"
                "2. 有没有遗漏重要的边界情况?\n"
                "3. 给出的方案是否是最优解?\n"
                "4. 有没有安全或性能方面的隐患?"
            )
        return f"<self_reflection>\n{reflection}\n</self_reflection>"

    def to_dict(self) -> dict:
        return {"patterns": [p.to_dict() for p in self.patterns.values()]}

    @staticmethod
    def from_dict(d: dict) -> ReasoningEngine:
        engine = ReasoningEngine()
        for pd in d.get("patterns", []):
            pattern = ReasoningPattern.from_dict(pd)
            engine.patterns[pattern.id] = pattern
        return engine


# ---------------------------------------------------------------------------
# Memory Graph — 长期学习记忆
# ---------------------------------------------------------------------------

@dataclass
class MemoryNode:
    """A node in the agent's learning memory graph."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    kind: str = "observation"    # observation | lesson | error_fix | success_pattern | concept
    title: str = ""
    content: str = ""
    tags: list[str] = field(default_factory=list)
    importance: float = 0.5      # 0.0 ~ 1.0, decays over time
    access_count: int = 0        # how often this memory was retrieved
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    related_ids: list[str] = field(default_factory=list)  # links to other nodes

    def to_dict(self) -> dict:
        return {
            "id": self.id, "kind": self.kind,
            "title": self.title, "content": self.content,
            "tags": self.tags, "importance": self.importance,
            "access_count": self.access_count,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "related_ids": self.related_ids,
        }

    @staticmethod
    def from_dict(d: dict) -> MemoryNode:
        return MemoryNode(
            id=d.get("id", uuid.uuid4().hex[:10]),
            kind=d.get("kind", "observation"),
            title=d.get("title", ""),
            content=d.get("content", ""),
            tags=d.get("tags", []),
            importance=d.get("importance", 0.5),
            access_count=d.get("access_count", 0),
            created_at=d.get("created_at", time.time()),
            last_accessed=d.get("last_accessed", time.time()),
            related_ids=d.get("related_ids", []),
        )


class MemoryGraph:
    """Long-term learning memory for an agent.

    Tracks patterns the agent has learned from past interactions:
    - Error→Fix pairs: "When I see X error, the fix is Y"
    - Success patterns: "Approach Z worked well for problem type W"
    - Concept links: "Topic A is related to Topic B"
    - Observations: general learnings

    Memories have importance scores that decay over time but increase
    when the memory is accessed (retrieved as relevant).
    """

    DECAY_RATE = 0.001  # importance decays by this per hour

    def __init__(self):
        self.nodes: dict[str, MemoryNode] = {}

    def add(self, title: str, content: str, kind: str = "observation",
            tags: list[str] | None = None,
            importance: float = 0.5,
            related_ids: list[str] | None = None) -> MemoryNode:
        node = MemoryNode(
            kind=kind, title=title, content=content,
            tags=tags or [], importance=importance,
            related_ids=related_ids or [],
        )
        self.nodes[node.id] = node
        logger.debug("Memory added: [%s] %s (importance=%.2f)", kind, title, importance)
        return node

    def add_error_fix(self, error_pattern: str, fix: str,
                      tags: list[str] | None = None) -> MemoryNode:
        """Convenience: add an error→fix learning."""
        return self.add(
            title=f"Fix: {error_pattern[:80]}",
            content=f"Error pattern: {error_pattern}\nFix: {fix}",
            kind="error_fix", tags=tags or [], importance=0.8,
        )

    def add_success_pattern(self, task_type: str, approach: str,
                            tags: list[str] | None = None) -> MemoryNode:
        """Convenience: add a successful approach pattern."""
        return self.add(
            title=f"Success: {task_type[:80]}",
            content=f"Task type: {task_type}\nApproach: {approach}",
            kind="success_pattern", tags=tags or [], importance=0.7,
        )

    def recall(self, query: str, limit: int = 5) -> list[MemoryNode]:
        """Retrieve relevant memories with importance weighting."""
        tokens = set(query.lower().split())
        scored = []
        now = time.time()
        for node in self.nodes.values():
            # Time-decayed importance
            hours_old = (now - node.created_at) / 3600
            decayed_importance = max(0.1, node.importance - self.DECAY_RATE * hours_old)
            # Frequency bonus
            freq_bonus = min(0.3, node.access_count * 0.05)
            # Relevance score
            text = f"{node.title} {node.content} {' '.join(node.tags)}".lower()
            relevance = 0
            for t in tokens:
                if t in text:
                    relevance += 1
                if t in node.title.lower():
                    relevance += 2
            if relevance == 0:
                continue
            total_score = relevance * (decayed_importance + freq_bonus)
            scored.append((total_score, node))

        scored.sort(key=lambda x: -x[0])
        # Update access counts for recalled memories
        for _, node in scored[:limit]:
            node.access_count += 1
            node.last_accessed = now
        return [n for _, n in scored[:limit]]

    def render_for_prompt(self, query: str, max_chars: int = 2000) -> str:
        """Render relevant memories for prompt injection."""
        memories = self.recall(query, limit=10)
        if not memories:
            return ""

        parts = ["<agent_memory>"]
        parts.append("以下是你从过往经验中学到的相关知识:")
        char_count = 0
        for m in memories:
            line = f"- [{m.kind}] {m.title}: {m.content}"
            if char_count + len(line) > max_chars:
                break
            parts.append(line)
            char_count += len(line)
        parts.append("</agent_memory>")
        return "\n".join(parts)

    def prune(self, min_importance: float = 0.1, max_age_hours: float = 720):
        """Remove old, low-importance memories to prevent unbounded growth."""
        now = time.time()
        to_remove = []
        for nid, node in self.nodes.items():
            hours_old = (now - node.created_at) / 3600
            decayed = max(0, node.importance - self.DECAY_RATE * hours_old)
            if decayed < min_importance and hours_old > max_age_hours:
                to_remove.append(nid)
        for nid in to_remove:
            del self.nodes[nid]
        if to_remove:
            logger.info("Pruned %d old memories", len(to_remove))

    def to_dict(self) -> dict:
        return {"nodes": [n.to_dict() for n in self.nodes.values()]}

    @staticmethod
    def from_dict(d: dict) -> MemoryGraph:
        mg = MemoryGraph()
        for nd in d.get("nodes", []):
            node = MemoryNode.from_dict(nd)
            mg.nodes[node.id] = node
        return mg


# ---------------------------------------------------------------------------
# Domain Tool Chain — 领域工具链
# ---------------------------------------------------------------------------

@dataclass
class ToolChainStep:
    """A step in a domain-specific tool usage pattern."""
    tool_name: str
    description: str
    typical_args: dict = field(default_factory=dict)
    condition: str = ""  # when to use this step

    def to_dict(self) -> dict:
        return {"tool_name": self.tool_name, "description": self.description,
                "typical_args": self.typical_args, "condition": self.condition}

    @staticmethod
    def from_dict(d: dict) -> ToolChainStep:
        return ToolChainStep(
            tool_name=d.get("tool_name", ""),
            description=d.get("description", ""),
            typical_args=d.get("typical_args", {}),
            condition=d.get("condition", ""),
        )


@dataclass
class DomainToolChain:
    """Preferred tool usage sequences for a domain."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    name: str = ""
    description: str = ""
    trigger_keywords: list[str] = field(default_factory=list)
    steps: list[ToolChainStep] = field(default_factory=list)

    def render_for_prompt(self) -> str:
        lines = [f"### 推荐工具链: {self.name}"]
        lines.append(self.description)
        for i, step in enumerate(self.steps, 1):
            cond = f" (当 {step.condition})" if step.condition else ""
            lines.append(f"  {i}. `{step.tool_name}` — {step.description}{cond}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name,
            "description": self.description,
            "trigger_keywords": self.trigger_keywords,
            "steps": [s.to_dict() for s in self.steps],
        }

    @staticmethod
    def from_dict(d: dict) -> DomainToolChain:
        return DomainToolChain(
            id=d.get("id", uuid.uuid4().hex[:10]),
            name=d.get("name", ""),
            description=d.get("description", ""),
            trigger_keywords=d.get("trigger_keywords", []),
            steps=[ToolChainStep.from_dict(s) for s in d.get("steps", [])],
        )


# ---------------------------------------------------------------------------
# AgentEnhancer — 增强模块编排器
# ---------------------------------------------------------------------------

class AgentEnhancer:
    """Orchestrates all enhancement components for an agent.

    This is the main entry point. Each Agent can have one AgentEnhancer
    that combines knowledge base, reasoning engine, memory graph, and
    tool chains to make the agent smarter in its domain.
    """

    def __init__(self, domain: str = "general"):
        self.domain = domain
        self.knowledge = KnowledgeBase()
        self.reasoning = ReasoningEngine()
        self.memory = MemoryGraph()
        self.tool_chains: dict[str, DomainToolChain] = {}
        self.enabled = True
        self.created_at = time.time()
        self._stats = {"enhance_count": 0, "learn_count": 0,
                       "recall_count": 0, "reflection_count": 0}

    # ---- Core enhancement methods ----

    def enhance_system_prompt(self, base_prompt: str, context_hint: str = "") -> str:
        """Enhance the base system prompt with domain knowledge.

        Called once when building the system prompt. Injects relevant
        knowledge entries and tool chain guidance.
        """
        if not self.enabled:
            return base_prompt

        additions = []

        # Domain identity
        additions.append(
            f"\n<domain_specialization domain=\"{self.domain}\">"
            f"\n你是 {self.domain} 领域的专家。以下领域知识已预加载，"
            f"请在回答时充分运用这些专业知识。"
        )

        # Inject high-priority knowledge.
        # IMPORTANT: if a keyword-query-based render returns nothing (e.g. the
        # agent's role text doesn't match any tags in a Chinese knowledge
        # base), fall back to priority-ranked rendering so the knowledge is
        # still injected into the system prompt.
        kb_text = ""
        if context_hint:
            kb_text = self.knowledge.render_for_prompt(context_hint, max_chars=4000)
        if not kb_text:
            kb_text = self.knowledge.render_for_prompt("", max_chars=4000)
        if kb_text:
            additions.append(kb_text)

        # Inject reasoning patterns (high-level framework hints)
        if self.reasoning.patterns:
            additions.append("\n<reasoning_frameworks>")
            for pat in list(self.reasoning.patterns.values())[:6]:
                desc = getattr(pat, "description", "") or ""
                additions.append(f"- {pat.name}: {desc}")
            additions.append("</reasoning_frameworks>")

        # Inject tool chains
        if self.tool_chains:
            additions.append("\n<recommended_tool_chains>")
            for tc in self.tool_chains.values():
                additions.append(tc.render_for_prompt())
            additions.append("</recommended_tool_chains>")

        additions.append("</domain_specialization>")
        self._stats["enhance_count"] += 1
        return base_prompt + "\n".join(additions)

    def pre_think(self, user_message: str) -> str:
        """Generate pre-thinking guidance before processing user message.

        Returns a system message to inject into conversation that guides
        the agent's reasoning process for this specific message.
        """
        if not self.enabled:
            return ""

        parts = []

        # Reasoning framework
        thinking = self.reasoning.generate_pre_think(user_message)
        if thinking:
            parts.append(thinking)

        # Relevant memories
        memory_text = self.memory.render_for_prompt(user_message, max_chars=2000)
        if memory_text:
            parts.append(memory_text)
            self._stats["recall_count"] += 1

        # Relevant knowledge (query-specific, not the base knowledge)
        relevant_kb = self.knowledge.search(user_message, limit=5)
        if relevant_kb:
            parts.append("<relevant_context>")
            for entry in relevant_kb:
                parts.append(f"- {entry.title}: {entry.content[:200]}")
            parts.append("</relevant_context>")

        return "\n".join(parts) if parts else ""

    def reflect_on_result(self, user_message: str, result: str) -> str:
        """Generate a reflection prompt after the agent produces a result.

        Encourages self-evaluation and improvement.
        """
        if not self.enabled:
            return ""
        self._stats["reflection_count"] += 1
        return self.reasoning.generate_reflection_prompt(user_message, result)

    def learn_from_interaction(self, user_message: str, agent_response: str,
                                outcome: str = "success",
                                feedback: str = "") -> MemoryNode | None:
        """Learn from a completed interaction.

        Can be called after: successful task completion, error recovery,
        user feedback (thumbs up/down), or explicit teaching.
        """
        if not self.enabled:
            return None

        self._stats["learn_count"] += 1

        if outcome == "error_fixed":
            return self.memory.add_error_fix(
                error_pattern=user_message[:200],
                fix=agent_response[:300],
                tags=[self.domain],
            )
        elif outcome == "success" and feedback:
            return self.memory.add_success_pattern(
                task_type=user_message[:200],
                approach=f"{agent_response[:200]}\nFeedback: {feedback}",
                tags=[self.domain],
            )
        elif feedback:
            return self.memory.add(
                title=f"Feedback: {feedback[:80]}",
                content=f"Message: {user_message[:200]}\nResponse: {agent_response[:200]}\nFeedback: {feedback}",
                kind="observation",
                tags=[self.domain],
                importance=0.6,
            )
        return None

    # ---- Tool chain management ----

    def add_tool_chain(self, name: str, description: str,
                       steps: list[dict],
                       trigger_keywords: list[str] | None = None) -> DomainToolChain:
        tc = DomainToolChain(
            name=name, description=description,
            trigger_keywords=trigger_keywords or [],
            steps=[ToolChainStep(**s) if isinstance(s, dict) else s for s in steps],
        )
        self.tool_chains[tc.id] = tc
        return tc

    # ---- Statistics ----

    def get_stats(self) -> dict:
        return {
            "domain": self.domain,
            "enabled": self.enabled,
            "knowledge_entries": len(self.knowledge.entries),
            "reasoning_patterns": len(self.reasoning.patterns),
            "memory_nodes": len(self.memory.nodes),
            "tool_chains": len(self.tool_chains),
            **self._stats,
        }

    # ---- Persistence ----

    def to_dict(self) -> dict:
        return {
            "domain": self.domain,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "knowledge": self.knowledge.to_dict(),
            "reasoning": self.reasoning.to_dict(),
            "memory": self.memory.to_dict(),
            "tool_chains": [tc.to_dict() for tc in self.tool_chains.values()],
            "stats": self._stats,
        }

    @staticmethod
    def from_dict(d: dict) -> AgentEnhancer:
        enhancer = AgentEnhancer(domain=d.get("domain", "general"))
        enhancer.enabled = d.get("enabled", True)
        enhancer.created_at = d.get("created_at", time.time())
        enhancer.knowledge = KnowledgeBase.from_dict(d.get("knowledge", {}))
        enhancer.reasoning = ReasoningEngine.from_dict(d.get("reasoning", {}))
        enhancer.memory = MemoryGraph.from_dict(d.get("memory", {}))
        for tcd in d.get("tool_chains", []):
            tc = DomainToolChain.from_dict(tcd)
            enhancer.tool_chains[tc.id] = tc
        enhancer._stats = d.get("stats", enhancer._stats)
        return enhancer


# ---------------------------------------------------------------------------
# Domain Presets — 预设领域增强包
# ---------------------------------------------------------------------------

def _build_security_audit_enhancer() -> AgentEnhancer:
    """安全审计领域增强包"""
    e = AgentEnhancer(domain="security_audit")

    # Knowledge base
    e.knowledge.add("OWASP Top 10", "注入攻击、失效的身份认证、敏感数据暴露、XML外部实体、失效的访问控制、安全配置错误、XSS、不安全的反序列化、使用含有已知漏洞的组件、不足的日志和监控",
                     category="reference", tags=["owasp", "web", "vulnerability"], priority=10)
    e.knowledge.add("SQL注入检测模式", "检查所有用户输入是否经过参数化查询处理。常见模式: 字符串拼接SQL、format/f-string构建SQL、ORM raw query未参数化",
                     category="pattern", tags=["sql", "injection", "detection"], priority=9)
    e.knowledge.add("认证安全检查清单", "1.密码是否加盐哈希存储 2.是否有暴力破解保护 3.Session管理是否安全 4.JWT是否正确验证 5.是否有CSRF保护 6.OAuth实现是否标准",
                     category="best_practice", tags=["auth", "session", "jwt"], priority=8)
    e.knowledge.add("依赖漏洞扫描", "使用 pip audit / npm audit / cargo audit 扫描已知漏洞。关注 CVE 评分 >= 7.0 的高危漏洞。检查依赖版本是否有安全补丁",
                     category="best_practice", tags=["dependency", "cve", "audit"], priority=7)
    e.knowledge.add("敏感数据检测", "扫描代码中的: API密钥、私钥、密码明文、数据库连接字符串、AWS凭证、token硬编码。使用正则: /(password|secret|key|token)\s*[=:]\s*['\"][^'\"]+/i",
                     category="pattern", tags=["secrets", "credentials", "leak"], priority=9)

    # Reasoning patterns
    e.reasoning.add_pattern(
        name="安全审计分析",
        description="对代码进行系统性安全审计",
        trigger_keywords=["安全", "审计", "漏洞", "security", "audit", "vulnerability"],
        steps=[
            {"name": "攻击面识别", "instruction": "识别所有外部输入点: HTTP端点、文件上传、命令行参数、环境变量、数据库查询、第三方API调用"},
            {"name": "数据流追踪", "instruction": "追踪每个输入从接收→处理→存储→输出的完整数据流，标记未经验证/清洗的路径"},
            {"name": "漏洞匹配", "instruction": "对照OWASP Top 10和CWE列表，检查每个数据流是否存在已知漏洞模式"},
            {"name": "权限分析", "instruction": "检查访问控制: 是否有越权访问风险、是否遵循最小权限原则、是否有水平/垂直越权"},
            {"name": "风险评估", "instruction": "对发现的每个问题评估: 严重程度(Critical/High/Medium/Low)、利用难度、影响范围", "output_format": "表格: 问题 | 严重程度 | 利用难度 | 修复建议"},
        ],
        reflection_prompt="回顾审计结果:\n1. 是否覆盖了所有OWASP Top 10类别?\n2. 有没有遗漏的攻击面?\n3. 修复建议是否切实可行?\n4. 是否需要补充自动化检测脚本?",
    )

    # Tool chains
    e.add_tool_chain(
        name="代码安全扫描",
        description="自动化安全扫描流程",
        trigger_keywords=["扫描", "scan", "check"],
        steps=[
            {"tool_name": "glob_files", "description": "查找所有源代码文件"},
            {"tool_name": "search_files", "description": "搜索危险模式: eval/exec/os.system/subprocess未过滤输入"},
            {"tool_name": "search_files", "description": "搜索硬编码凭证: password/secret/key/token"},
            {"tool_name": "bash", "description": "运行依赖漏洞扫描: pip audit / npm audit"},
            {"tool_name": "read_file", "description": "详细分析高危发现点的上下文"},
        ],
    )
    return e


def _build_devops_enhancer() -> AgentEnhancer:
    """DevOps领域增强包"""
    e = AgentEnhancer(domain="devops")

    e.knowledge.add("容器安全基线", "1.使用非root用户运行 2.最小化基础镜像 3.多阶段构建减小体积 4.扫描镜像漏洞 5.限制容器资源 6.只读文件系统 7.不暴露不必要端口",
                     category="best_practice", tags=["docker", "container", "security"], priority=9)
    e.knowledge.add("CI/CD流水线模式", "标准流程: lint→test→build→scan→deploy(staging)→e2e→deploy(prod)。每个阶段失败应阻塞后续。使用蓝绿部署或金丝雀发布降低风险",
                     category="pattern", tags=["ci", "cd", "pipeline"], priority=8)
    e.knowledge.add("K8s健康检查", "必须配置: livenessProbe(重启不健康容器)、readinessProbe(控制流量)、startupProbe(慢启动应用)。探针类型: httpGet/tcpSocket/exec",
                     category="best_practice", tags=["kubernetes", "health", "probe"], priority=8)
    e.knowledge.add("监控黄金信号", "Google SRE 四个黄金信号: 延迟(Latency)、流量(Traffic)、错误率(Errors)、饱和度(Saturation)。P99延迟比平均值更能反映真实用户体验",
                     category="reference", tags=["monitoring", "sre", "metrics"], priority=7)
    e.knowledge.add("故障排查步骤", "1.确认影响范围(哪些服务/用户受影响) 2.查看监控告警(Prometheus/Grafana) 3.检查最近变更(git log/deploy history) 4.查看日志(kubectl logs/journalctl) 5.检查资源(CPU/Memory/Disk/Network)",
                     category="pattern", tags=["troubleshoot", "incident", "debug"], priority=9)

    e.reasoning.add_pattern(
        name="故障排查",
        description="系统性排查生产环境故障",
        trigger_keywords=["故障", "宕机", "报错", "500", "timeout", "crash", "incident", "排查"],
        steps=[
            {"name": "影响评估", "instruction": "确认: 受影响服务、受影响用户量、开始时间、是否在恶化"},
            {"name": "变更审计", "instruction": "检查最近24小时内的变更: 代码部署、配置变更、基础设施变更、依赖更新"},
            {"name": "资源检查", "instruction": "检查系统资源: CPU/Memory/Disk/Network使用率，是否有异常峰值"},
            {"name": "日志分析", "instruction": "查看错误日志，定位第一个异常时间点和错误模式"},
            {"name": "根因定位", "instruction": "结合以上信息推断根因，制定修复方案和回滚计划"},
        ],
        reflection_prompt="1. 是否找到了根本原因(而非表面症状)?\n2. 修复方案是否有回滚计划?\n3. 类似问题如何预防?\n4. 是否需要更新监控告警?",
    )

    e.add_tool_chain(
        name="服务健康检查",
        description="快速检查服务运行状态",
        steps=[
            {"tool_name": "bash", "description": "检查进程状态: ps aux / systemctl status"},
            {"tool_name": "bash", "description": "检查端口监听: netstat -tlnp / ss -tlnp"},
            {"tool_name": "bash", "description": "检查资源使用: free -h / df -h / top -bn1"},
            {"tool_name": "bash", "description": "检查最近日志: journalctl -u service --since '1h ago'"},
            {"tool_name": "bash", "description": "检查网络连通: curl -s health_endpoint / ping"},
        ],
    )
    return e


def _build_frontend_enhancer() -> AgentEnhancer:
    """前端开发领域增强包"""
    e = AgentEnhancer(domain="frontend")

    e.knowledge.add("React性能优化", "1.React.memo防止不必要渲染 2.useMemo/useCallback缓存计算和回调 3.虚拟列表处理大数据 4.代码分割(lazy/Suspense) 5.避免内联对象/函数作为props 6.使用key优化列表渲染",
                     category="best_practice", tags=["react", "performance", "optimization"], priority=9)
    e.knowledge.add("CSS布局选择", "Flexbox: 一维布局(行或列)。Grid: 二维布局(行和列)。选择原则: 导航栏/工具栏→Flex，仪表盘/复杂网格→Grid，响应式卡片→Grid+auto-fill",
                     category="pattern", tags=["css", "layout", "flexbox", "grid"], priority=7)
    e.knowledge.add("Web Vitals标准", "LCP(最大内容绘制)<2.5s, FID(首次输入延迟)<100ms, CLS(累积布局偏移)<0.1, INP(交互到下一次绘制)<200ms, TTFB(首字节时间)<800ms",
                     category="reference", tags=["performance", "vitals", "metrics"], priority=8)
    e.knowledge.add("无障碍检查清单", "1.所有图片有alt文本 2.颜色对比度>=4.5:1 3.键盘完全可导航 4.ARIA标签正确 5.表单有关联label 6.焦点可见 7.屏幕阅读器测试通过",
                     category="best_practice", tags=["a11y", "accessibility", "wcag"], priority=7)

    e.reasoning.add_pattern(
        name="组件设计",
        description="设计React/Vue组件的系统方法",
        trigger_keywords=["组件", "component", "页面", "UI", "界面"],
        steps=[
            {"name": "需求拆解", "instruction": "明确组件的: 功能需求、数据输入(props)、状态管理、事件输出、交互行为"},
            {"name": "组件树设计", "instruction": "将UI拆分为组件树，确定: 容器组件vs展示组件、共享状态提升位置、复用组件识别"},
            {"name": "状态设计", "instruction": "确定状态位置和类型: local state / context / 全局store，识别派生状态(可从已有状态计算的)"},
            {"name": "实现", "instruction": "编写组件代码，注意: TypeScript类型定义、错误边界、loading/empty/error状态处理"},
            {"name": "优化", "instruction": "检查: 不必要的重渲染、bundle大小、懒加载机会、无障碍合规"},
        ],
    )
    return e


def _build_data_engineering_enhancer() -> AgentEnhancer:
    """数据工程领域增强包"""
    e = AgentEnhancer(domain="data_engineering")

    e.knowledge.add("SQL优化原则", "1.避免SELECT * 2.合理使用索引(查询列、WHERE条件列、JOIN列) 3.避免在WHERE中对列使用函数 4.用EXISTS代替IN处理大子查询 5.LIMIT分页优化 6.EXPLAIN分析执行计划",
                     category="best_practice", tags=["sql", "performance", "index"], priority=9)
    e.knowledge.add("ETL设计模式", "ELT优于ETL(先加载再转换,利用数据仓库算力)。幂等性设计(重跑不产生重复数据)。增量加载(CDC/watermark)优于全量。Schema-on-read的灵活性 vs Schema-on-write的数据质量",
                     category="pattern", tags=["etl", "pipeline", "data"], priority=8)
    e.knowledge.add("数据质量检查", "必检项: 空值率、唯一性、引用完整性、数据范围、格式一致性、时效性。Great Expectations / dbt tests / 自定义SQL断言",
                     category="best_practice", tags=["quality", "validation", "testing"], priority=8)

    e.reasoning.add_pattern(
        name="数据管道设计",
        description="设计数据处理管道",
        trigger_keywords=["数据管道", "ETL", "pipeline", "数据处理", "数据仓库"],
        steps=[
            {"name": "数据源分析", "instruction": "识别所有数据源: 类型(API/DB/文件/流)、Schema、更新频率、数据量"},
            {"name": "转换逻辑", "instruction": "设计转换步骤: 清洗→标准化→关联→聚合→派生。每步输入输出明确"},
            {"name": "存储策略", "instruction": "选择存储: 原始层(raw)→清洗层(cleaned)→业务层(mart)。分区策略、压缩格式"},
            {"name": "可靠性设计", "instruction": "幂等性、失败重试、数据回填、监控告警、SLA定义"},
        ],
    )
    return e


def _build_api_design_enhancer() -> AgentEnhancer:
    """API设计领域增强包"""
    e = AgentEnhancer(domain="api_design")

    e.knowledge.add("RESTful设计原则", "资源命名用名词复数(/users)。HTTP方法语义: GET读取、POST创建、PUT全量更新、PATCH部分更新、DELETE删除。无状态设计。HATEOAS链接驱动",
                     category="best_practice", tags=["rest", "http", "design"], priority=9)
    e.knowledge.add("API版本管理", "URL路径版本(/v1/users)最直观。Header版本(Accept: application/vnd.api.v1+json)更RESTful。不要用查询参数版本。向后兼容: 只添加字段不删除",
                     category="pattern", tags=["versioning", "backward", "compatibility"], priority=8)
    e.knowledge.add("错误处理标准", "统一错误格式: {error: {code, message, details[]}}。HTTP状态码: 400参数错误、401未认证、403无权限、404未找到、409冲突、422语义错误、429限频、500内部错误",
                     category="best_practice", tags=["error", "http", "status"], priority=8)
    e.knowledge.add("API安全实践", "1.认证(OAuth2/JWT/API Key) 2.速率限制 3.输入验证(长度/类型/范围) 4.输出编码 5.CORS配置 6.HTTPS强制 7.审计日志 8.字段级权限控制",
                     category="best_practice", tags=["security", "auth", "rate_limit"], priority=9)

    e.reasoning.add_pattern(
        name="API端点设计",
        description="设计RESTful API端点",
        trigger_keywords=["API", "接口", "endpoint", "REST", "接口设计"],
        steps=[
            {"name": "资源识别", "instruction": "识别核心资源(名词)及其关系。确定资源层级和嵌套策略"},
            {"name": "端点设计", "instruction": "为每个资源设计CRUD端点。确定查询参数(过滤/排序/分页)"},
            {"name": "请求响应", "instruction": "定义请求体和响应体的JSON Schema。考虑字段命名一致性(camelCase/snake_case)"},
            {"name": "错误处理", "instruction": "为每个端点定义可能的错误响应。确保错误码和消息有意义"},
            {"name": "安全与限流", "instruction": "确定认证方式、权限模型、速率限制策略"},
        ],
    )
    return e


# ---------------------------------------------------------------------------
# Lightweight preset builders (knowledge + reasoning, no tool chains)
# ---------------------------------------------------------------------------

def _build_generic_enhancer(domain: str, knowledge: list[dict],
                            patterns: list[dict]) -> AgentEnhancer:
    """通用 builder：用 knowledge/patterns 列表快速构建增强包。"""
    e = AgentEnhancer(domain=domain)
    for k in knowledge:
        e.knowledge.add(k["title"], k["content"],
                        category=k.get("cat", "best_practice"),
                        tags=k.get("tags", []), priority=k.get("pri", 7))
    for p in patterns:
        e.reasoning.add_pattern(
            name=p["name"], description=p.get("desc", ""),
            trigger_keywords=p.get("kw", []),
            steps=[{"name": s[0], "instruction": s[1]} for s in p["steps"]],
            reflection_prompt=p.get("reflect", ""),
        )
    return e


def _build_market_analyst_enhancer() -> AgentEnhancer:
    return _build_generic_enhancer("market_analyst", [
        {"title": "竞品分析框架", "content": "SWOT + Porter五力 + 价值链分析。关注: 市场份额、定价策略、产品差异、渠道布局、用户画像", "tags": ["market", "competition"], "pri": 9},
        {"title": "数据来源", "content": "行业报告(艾瑞/IDC)、财报、App Annie、SimilarWeb、社交媒体舆情、专利数据库、招聘数据", "tags": ["data", "source"], "pri": 8},
    ], [{"name": "市场分析", "desc": "系统性市场调研", "kw": ["市场", "竞品", "分析", "趋势", "行业"],
         "steps": [("市场界定", "确定目标市场边界、TAM/SAM/SOM"), ("竞品映射", "识别直接/间接竞品，分析各自定位"),
                   ("趋势研判", "技术趋势、政策趋势、用户需求变化"), ("机会识别", "未被满足的需求、市场空白、切入点")]}])


def _build_product_manager_enhancer() -> AgentEnhancer:
    return _build_generic_enhancer("product_manager", [
        {"title": "需求优先级", "content": "RICE评分: Reach(影响人数)×Impact(影响程度)×Confidence(信心)÷Effort(工作量)。MoSCoW: Must/Should/Could/Won't", "tags": ["priority", "rice"], "pri": 9},
        {"title": "PRD结构", "content": "背景→目标→用户故事→功能需求→非功能需求→数据埋点→排期→验收标准", "tags": ["prd", "doc"], "pri": 8},
    ], [{"name": "需求分析", "desc": "产品需求系统分析", "kw": ["需求", "产品", "功能", "用户", "PRD"],
         "steps": [("用户洞察", "目标用户是谁？痛点是什么？使用场景？"), ("方案设计", "核心功能、交互流程、MVP范围"),
                   ("可行性评估", "技术可行性、资源需求、风险点"), ("指标定义", "成功指标(北极星指标)和数据埋点方案")]}])


def _build_developer_enhancer() -> AgentEnhancer:
    return _build_generic_enhancer("developer", [
        {"title": "代码审查清单", "content": "1.命名清晰 2.函数单一职责 3.错误处理完整 4.无硬编码 5.有单元测试 6.无安全漏洞 7.性能合理 8.日志充分", "tags": ["review", "quality"], "pri": 9},
        {"title": "设计模式", "content": "创建型:工厂/单例/Builder 结构型:适配器/装饰器/代理 行为型:观察者/策略/命令。优先组合>继承", "tags": ["pattern", "design"], "pri": 8},
    ], [{"name": "代码开发", "desc": "系统性编码", "kw": ["开发", "编码", "实现", "代码", "bug"],
         "steps": [("需求理解", "明确输入输出、边界条件、性能要求"), ("方案设计", "选择技术方案、数据结构、接口定义"),
                   ("实现编码", "编写代码，注意错误处理和边界情况"), ("测试验证", "单元测试、集成测试、边界测试")]}])


def _build_qa_engineer_enhancer() -> AgentEnhancer:
    return _build_generic_enhancer("qa_engineer", [
        {"title": "测试策略", "content": "测试金字塔: 单元测试(70%)→集成测试(20%)→E2E测试(10%)。左移测试: 需求阶段介入，代码审查参与", "tags": ["testing", "strategy"], "pri": 9},
        {"title": "缺陷分析", "content": "分类: 功能/性能/安全/兼容性/体验。严重级: Blocker>Critical>Major>Minor>Trivial。根因分析: 5-Why法", "tags": ["bug", "analysis"], "pri": 8},
    ], [{"name": "测试设计", "desc": "系统性测试方案", "kw": ["测试", "QA", "用例", "缺陷", "验收"],
         "steps": [("测试范围", "功能点梳理、风险评估、重点区域"), ("用例设计", "等价类、边界值、场景法、错误推测"),
                   ("执行验证", "执行测试、记录结果、缺陷报告"), ("回归确认", "修复验证、影响范围回归")]}])


def _build_operations_enhancer() -> AgentEnhancer:
    return _build_generic_enhancer("operations", [
        {"title": "运营数据指标", "content": "AARRR: 获取→激活→留存→收入→推荐。北极星指标选择: 反映核心价值、可量化、可行动", "tags": ["metrics", "aarrr"], "pri": 9},
        {"title": "活动策划", "content": "目标→人群→玩法→渠道→预算→时间线→风险预案→效果复盘", "tags": ["campaign", "plan"], "pri": 8},
    ], [{"name": "运营分析", "desc": "运营策略制定", "kw": ["运营", "活动", "转化", "留存", "增长"],
         "steps": [("数据诊断", "核心指标现状、趋势、漏斗分析"), ("策略制定", "目标拆解、增长杠杆、资源分配"),
                   ("执行落地", "具体行动计划、责任人、时间表"), ("效果评估", "数据对比、ROI计算、经验沉淀")]}])


def _build_finance_enhancer() -> AgentEnhancer:
    return _build_generic_enhancer("finance", [
        {"title": "财务分析框架", "content": "杜邦分析: ROE=利润率×周转率×杠杆。三表联动: 利润表→资产负债表→现金流量表。关注: 毛利率、净利率、现金流", "tags": ["finance", "analysis"], "pri": 9},
        {"title": "预算管理", "content": "零基预算 vs 增量预算。滚动预算(季度更新)。预算偏差分析: 实际vs预算，找出偏差原因", "tags": ["budget", "planning"], "pri": 8},
    ], [{"name": "财务分析", "desc": "财务数据分析", "kw": ["财务", "预算", "成本", "利润", "现金流"],
         "steps": [("数据收集", "财务报表、业务数据、行业benchmark"), ("指标分析", "盈利能力、偿债能力、运营效率"),
                   ("问题诊断", "异常项识别、趋势变化、原因分析"), ("建议输出", "改善措施、预算调整、风险提示")]}])


def _build_hr_enhancer() -> AgentEnhancer:
    return _build_generic_enhancer("hr", [
        {"title": "招聘流程", "content": "JD编写→渠道投放→简历筛选→初筛面试→技术面→终面→offer→入职。注意: 结构化面试、STAR法则、反歧视", "tags": ["recruit", "hiring"], "pri": 9},
        {"title": "绩效管理", "content": "OKR(目标与关键结果) vs KPI(关键绩效指标)。360度评估。绩效面谈: 先肯定再改进，GROW模型", "tags": ["performance", "okr"], "pri": 8},
    ], [{"name": "人力资源分析", "desc": "HR管理分析", "kw": ["招聘", "绩效", "培训", "离职", "薪酬"],
         "steps": [("现状评估", "人员结构、流动率、满意度"), ("需求分析", "业务需求→人才需求→能力差距"),
                   ("方案设计", "招聘计划/培训方案/薪酬调整"), ("效果跟踪", "数据跟踪、定期复盘、持续优化")]}])


def _build_designer_enhancer() -> AgentEnhancer:
    return _build_generic_enhancer("designer", [
        {"title": "设计原则", "content": "一致性、可见性、反馈、容错、简洁。Nielsen十大可用性原则。Gestalt法则: 接近、相似、闭合、连续", "tags": ["ux", "principle"], "pri": 9},
        {"title": "设计系统", "content": "原子设计: Atoms→Molecules→Organisms→Templates→Pages。设计令牌: 颜色/字体/间距/阴影标准化", "tags": ["system", "atomic"], "pri": 8},
    ], [{"name": "设计方案", "desc": "UI/UX设计", "kw": ["设计", "UI", "UX", "界面", "交互", "原型"],
         "steps": [("用户研究", "用户画像、使用场景、竞品设计分析"), ("信息架构", "内容组织、导航结构、任务流程"),
                   ("视觉设计", "风格定义、组件库、响应式适配"), ("可用性验证", "启发式评估、用户测试、迭代优化")]}])


def _build_legal_enhancer() -> AgentEnhancer:
    return _build_generic_enhancer("legal", [
        {"title": "合同审查要点", "content": "主体资格→权利义务→违约责任→争议解决→期限→保密条款→知识产权归属→不可抗力", "tags": ["contract", "review"], "pri": 9},
        {"title": "数据合规", "content": "GDPR/个保法: 数据最小化、目的限制、用户同意、数据可携带、被遗忘权、跨境传输限制", "tags": ["compliance", "gdpr"], "pri": 9},
    ], [{"name": "法律分析", "desc": "法务合规分析", "kw": ["合同", "法律", "合规", "知识产权", "隐私"],
         "steps": [("法规检索", "相关法律法规、行业规定、判例"), ("风险识别", "法律风险点、合规差距、潜在纠纷"),
                   ("方案建议", "风险缓解措施、条款修改建议"), ("文档准备", "法律意见书、合同修改稿")]}])


def _build_sales_enhancer() -> AgentEnhancer:
    return _build_generic_enhancer("sales", [
        {"title": "销售方法论", "content": "SPIN: Situation→Problem→Implication→Need-payoff。MEDDIC: Metrics→Economic Buyer→Decision Criteria→Decision Process→Identify Pain→Champion", "tags": ["sales", "method"], "pri": 9},
        {"title": "CRM管理", "content": "漏斗阶段: 线索→MQL→SQL→商机→谈判→成交。关注: 转化率、平均客单价、销售周期、赢单率", "tags": ["crm", "funnel"], "pri": 8},
    ], [{"name": "销售策略", "desc": "销售分析与策略", "kw": ["销售", "客户", "商机", "报价", "成交"],
         "steps": [("客户画像", "行业/规模/痛点/决策链/预算"), ("方案匹配", "需求→产品能力映射，价值主张提炼"),
                   ("竞争策略", "竞品对比优劣势，差异化卖点"), ("成交推进", "报价策略、谈判要点、时间线管理")]}])


def _build_video_producer_enhancer() -> AgentEnhancer:
    return _build_generic_enhancer("video_producer", [
        {"title": "视频制作流程", "content": "策划(选题/脚本)→拍摄(场景/灯光/机位)→剪辑(粗剪→精剪→调色→音频)→后期(特效/字幕)→输出(格式/平台适配)", "tags": ["video", "workflow"], "pri": 9},
        {"title": "平台规范", "content": "抖音: 9:16竖屏,15-60s。B站: 16:9横屏,5-30min。YouTube: 16:9,8-15min最优。小红书: 3:4或1:1,1-3min", "tags": ["platform", "spec"], "pri": 8},
    ], [{"name": "视频策划", "desc": "视频内容策划", "kw": ["视频", "拍摄", "剪辑", "脚本", "短视频"],
         "steps": [("选题策划", "热点分析、目标受众、内容定位"), ("脚本撰写", "分镜头脚本、台词、时间节奏"),
                   ("制作执行", "拍摄清单、后期流程、质量把控"), ("发布优化", "标题封面、标签SEO、发布时间")]}])


def _build_strategy_enhancer() -> AgentEnhancer:
    return _build_generic_enhancer("strategy", [
        {"title": "战略分析工具", "content": "PEST(宏观)→Porter五力(行业)→SWOT(企业)→BCG矩阵(业务组合)→价值链(内部)", "tags": ["strategy", "framework"], "pri": 9},
    ], [{"name": "战略规划", "desc": "企业战略分析", "kw": ["战略", "规划", "布局", "方向", "愿景"],
         "steps": [("环境扫描", "宏观趋势、行业格局、竞争态势"), ("能力评估", "核心能力、资源禀赋、差距分析"),
                   ("战略选择", "增长路径、竞争策略、资源配置"), ("路线图", "里程碑、KPI、风险应对")]}])


def _build_customer_support_enhancer() -> AgentEnhancer:
    return _build_generic_enhancer("customer_support", [
        {"title": "客服SOP", "content": "问候→倾听→确认问题→查找方案→执行→确认解决→满意度调查。升级规则: 超时/复杂/投诉→主管", "tags": ["support", "sop"], "pri": 9},
    ], [{"name": "客户问题处理", "desc": "客户服务", "kw": ["客户", "投诉", "工单", "反馈", "售后"],
         "steps": [("问题分类", "类型判断、紧急程度、影响范围"), ("方案检索", "知识库匹配、历史案例、标准流程"),
                   ("解决执行", "方案实施、进度同步、记录"), ("回访闭环", "确认满意、经验入库、流程优化")]}])


def _build_researcher_enhancer() -> AgentEnhancer:
    return _build_generic_enhancer("researcher", [
        {"title": "研究方法", "content": "定量: 实验/问卷/数据分析。定性: 访谈/焦点小组/案例研究。混合方法设计: 先质后量或先量后质", "tags": ["research", "method"], "pri": 9},
    ], [{"name": "研究设计", "desc": "学术/应用研究", "kw": ["研究", "论文", "调研", "实验", "数据分析"],
         "steps": [("文献综述", "研究现状、理论框架、研究空白"), ("方案设计", "研究问题→假设→方法→样本→工具"),
                   ("数据收集分析", "采集→清洗→统计→可视化"), ("结论输出", "发现总结、局限性、后续方向")]}])


def _build_project_director_enhancer() -> AgentEnhancer:
    return _build_generic_enhancer("project_director", [
        {"title": "项目管理", "content": "PMBOK五大过程组: 启动→规划→执行→监控→收尾。敏捷: Sprint规划→Daily→评审→回顾。关键路径法(CPM)", "tags": ["pm", "agile"], "pri": 9},
    ], [{"name": "项目管理", "desc": "项目全流程管理", "kw": ["项目", "排期", "里程碑", "风险", "进度"],
         "steps": [("项目启动", "目标确认、干系人识别、章程"), ("规划", "WBS拆解、排期、资源、风险登记"),
                   ("执行监控", "进度跟踪、风险应对、变更管理"), ("收尾复盘", "交付确认、经验总结、知识归档")]}])


def _build_pr_marketing_enhancer() -> AgentEnhancer:
    return _build_generic_enhancer("pr_marketing", [
        {"title": "营销策略", "content": "4P: Product/Price/Place/Promotion。内容营销漏斗: 吸引→转化→成交→忠诚。SEO+SEM+社交+KOL+EDM", "tags": ["marketing", "4p"], "pri": 9},
    ], [{"name": "营销方案", "desc": "营销推广策划", "kw": ["营销", "推广", "品牌", "PR", "传播"],
         "steps": [("市场洞察", "目标人群、竞品策略、渠道分析"), ("策略制定", "定位、信息、渠道组合、预算"),
                   ("内容创作", "素材准备、文案、视觉"), ("效果优化", "数据监测、A/B测试、ROI优化")]}])


def _build_supply_chain_enhancer() -> AgentEnhancer:
    return _build_generic_enhancer("supply_chain", [
        {"title": "供应链管理", "content": "SCOR模型: Plan→Source→Make→Deliver→Return。库存: 安全库存=Z×σ×√LT。供应商: QCD(质量/成本/交期)评估", "tags": ["scm", "inventory"], "pri": 9},
    ], [{"name": "供应链分析", "desc": "供应链优化", "kw": ["供应链", "库存", "采购", "物流", "供应商"],
         "steps": [("现状诊断", "库存周转、交付准时率、成本结构"), ("瓶颈识别", "供应风险、产能约束、物流效率"),
                   ("优化方案", "库存策略、供应商优化、流程改进"), ("实施跟踪", "KPI设定、周期评估、持续改善")]}])


def _build_trainer_enhancer() -> AgentEnhancer:
    return _build_generic_enhancer("trainer", [
        {"title": "培训设计", "content": "ADDIE模型: Analysis→Design→Develop→Implement→Evaluate。柯氏四级评估: 反应→学习→行为→结果", "tags": ["training", "addie"], "pri": 9},
    ], [{"name": "培训方案设计", "desc": "企业培训", "kw": ["培训", "课程", "教学", "学习", "赋能"],
         "steps": [("需求分析", "岗位能力模型、差距评估、优先级"), ("课程设计", "学习目标、内容结构、教学方法"),
                   ("实施交付", "讲师准备、互动设计、练习安排"), ("效果评估", "考核方式、行为跟踪、ROI分析")]}])


# ---------------------------------------------------------------------------
# Preset Registry
# ---------------------------------------------------------------------------

ENHANCEMENT_PRESETS: dict[str, callable] = {
    "security_audit": _build_security_audit_enhancer,
    "devops": _build_devops_enhancer,
    "frontend": _build_frontend_enhancer,
    "data_engineering": _build_data_engineering_enhancer,
    "api_design": _build_api_design_enhancer,
    "market_analyst": _build_market_analyst_enhancer,
    "product_manager": _build_product_manager_enhancer,
    "developer": _build_developer_enhancer,
    "qa_engineer": _build_qa_engineer_enhancer,
    "operations": _build_operations_enhancer,
    "finance": _build_finance_enhancer,
    "hr": _build_hr_enhancer,
    "designer": _build_designer_enhancer,
    "legal": _build_legal_enhancer,
    "sales": _build_sales_enhancer,
    "video_producer": _build_video_producer_enhancer,
    "strategy": _build_strategy_enhancer,
    "customer_support": _build_customer_support_enhancer,
    "researcher": _build_researcher_enhancer,
    "project_director": _build_project_director_enhancer,
    "pr_marketing": _build_pr_marketing_enhancer,
    "supply_chain": _build_supply_chain_enhancer,
    "trainer": _build_trainer_enhancer,
}

ENHANCEMENT_PRESET_INFO: dict[str, dict] = {
    "security_audit":   {"name": "安全审计",   "icon": "🛡️", "description": "OWASP Top 10、漏洞检测、安全扫描、权限分析"},
    "devops":           {"name": "DevOps运维", "icon": "🚀", "description": "容器安全、CI/CD流水线、故障排查、监控告警"},
    "frontend":         {"name": "前端开发",   "icon": "🎨", "description": "React性能优化、组件设计、Web Vitals、无障碍"},
    "data_engineering": {"name": "数据工程",   "icon": "📊", "description": "SQL优化、ETL设计、数据质量、管道架构"},
    "api_design":       {"name": "API设计",    "icon": "🔌", "description": "RESTful设计、版本管理、错误处理、安全实践"},
    "market_analyst":   {"name": "市场分析",   "icon": "📈", "description": "竞品分析、行业趋势、用户调研、市场策略"},
    "product_manager":  {"name": "产品经理",   "icon": "📋", "description": "需求分析、PRD撰写、优先级排序、用户洞察"},
    "developer":        {"name": "软件开发",   "icon": "💻", "description": "代码审查、设计模式、架构设计、最佳实践"},
    "qa_engineer":      {"name": "测试工程",   "icon": "🧪", "description": "测试策略、用例设计、缺陷分析、自动化测试"},
    "operations":       {"name": "运营增长",   "icon": "📱", "description": "AARRR模型、转化优化、活动策划、数据驱动"},
    "finance":          {"name": "财务分析",   "icon": "💰", "description": "财报分析、预算管理、成本控制、现金流"},
    "hr":               {"name": "人力资源",   "icon": "👥", "description": "招聘流程、绩效管理、培训发展、薪酬体系"},
    "designer":         {"name": "UI/UX设计",  "icon": "🎯", "description": "设计系统、用户研究、交互设计、可用性"},
    "legal":            {"name": "法务合规",   "icon": "⚖️", "description": "合同审查、数据合规、知识产权、风险管控"},
    "sales":            {"name": "销售管理",   "icon": "🤝", "description": "SPIN销售、CRM管理、客户画像、成交策略"},
    "video_producer":   {"name": "视频制作",   "icon": "🎬", "description": "脚本策划、拍摄剪辑、平台运营、内容优化"},
    "strategy":         {"name": "战略规划",   "icon": "🧭", "description": "战略分析、商业模式、竞争策略、路线图"},
    "customer_support": {"name": "客户服务",   "icon": "🎧", "description": "工单管理、SOP流程、客户满意度、知识库"},
    "researcher":       {"name": "研究分析",   "icon": "🔬", "description": "研究方法、数据分析、文献综述、报告撰写"},
    "project_director": {"name": "项目管理",   "icon": "📅", "description": "敏捷/瀑布、风险管理、排期跟踪、干系人管理"},
    "pr_marketing":     {"name": "营销推广",   "icon": "📣", "description": "品牌传播、内容营销、渠道策略、效果优化"},
    "supply_chain":     {"name": "供应链",     "icon": "🏭", "description": "库存管理、采购优化、物流效率、供应商评估"},
    "trainer":          {"name": "企业培训",   "icon": "🎓", "description": "课程设计、能力模型、培训评估、知识管理"},
}


def list_enhancement_presets() -> list[dict]:
    """List available enhancement presets (built-in + community)."""
    results = [
        {"id": k, **v}
        for k, v in ENHANCEMENT_PRESET_INFO.items()
    ]
    # Append community skills from the bundled catalog
    try:
        catalog = _load_community_catalog()
        for s in catalog.get("skills", []):
            results.append({
                "id": s["id"],
                "name": s.get("name", s["id"]),
                "icon": s.get("icon", "📦"),
                "description": s.get("description", ""),
                "category": s.get("category", "community"),
                "source": s.get("source", "community"),
            })
    except Exception:
        pass
    return results


def build_enhancer(domain: str) -> AgentEnhancer:
    """Build an enhancer from a preset, community skill, or empty one."""
    builder = ENHANCEMENT_PRESETS.get(domain)
    if builder:
        return builder()
    # Try community catalog
    try:
        community_skill = _find_community_skill(domain)
        if community_skill:
            return _build_from_community_skill(community_skill)
    except Exception:
        pass
    return AgentEnhancer(domain=domain)


# ---------------------------------------------------------------------------
# Community skills catalog (imported from agency-agents-zh-main)
# ---------------------------------------------------------------------------

_COMMUNITY_CATALOG: dict | None = None


def _load_community_catalog() -> dict:
    """Lazy-load the bundled community skills catalog (JSON)."""
    global _COMMUNITY_CATALOG
    if _COMMUNITY_CATALOG is not None:
        return _COMMUNITY_CATALOG
    import json, os
    here = os.path.dirname(__file__)
    path = os.path.join(here, "data", "community_skills.json")
    if not os.path.exists(path):
        _COMMUNITY_CATALOG = {"skills": []}
        return _COMMUNITY_CATALOG
    try:
        with open(path, "r", encoding="utf-8") as f:
            _COMMUNITY_CATALOG = json.load(f)
    except Exception:
        _COMMUNITY_CATALOG = {"skills": []}
    return _COMMUNITY_CATALOG


def _find_community_skill(skill_id: str) -> dict | None:
    cat = _load_community_catalog()
    for s in cat.get("skills", []):
        if s.get("id") == skill_id:
            return s
    return None


def _build_from_community_skill(skill: dict) -> AgentEnhancer:
    """Materialise a community skill JSON entry into an AgentEnhancer."""
    enhancer = AgentEnhancer(domain=skill.get("id", "community_skill"))
    # Inject knowledge entries
    for e in skill.get("entries", []):
        entry = KnowledgeEntry(
            id=e.get("id", ""),
            title=e.get("title", ""),
            content=e.get("content", ""),
            category=e.get("category", "reference"),
            tags=list(e.get("tags", []) or []),
            priority=int(e.get("priority", 5)),
        )
        enhancer.knowledge.entries[entry.id] = entry
    return enhancer


def build_multi_enhancer(domains: list[str]) -> AgentEnhancer:
    """Build a composite enhancer merging up to 8 preset domains.

    Knowledge entries, reasoning patterns, memory nodes and tool chains from
    each preset are copied into a single AgentEnhancer whose domain is the
    "+" joined composite name. If only one domain is provided, this is
    equivalent to build_enhancer(domain).
    """
    doms = [d for d in (domains or []) if d]
    # Cap at 8 to keep context small
    doms = doms[:8]
    if not doms:
        return AgentEnhancer(domain="custom")
    if len(doms) == 1:
        return build_enhancer(doms[0])

    composite_name = "+".join(doms)
    merged = AgentEnhancer(domain=composite_name)
    for d in doms:
        src = build_enhancer(d)
        # Merge knowledge
        for eid, entry in src.knowledge.entries.items():
            if eid not in merged.knowledge.entries:
                merged.knowledge.entries[eid] = entry
        # Merge reasoning
        for pid, pat in src.reasoning.patterns.items():
            if pid not in merged.reasoning.patterns:
                merged.reasoning.patterns[pid] = pat
        # Merge memory
        for nid, node in src.memory.nodes.items():
            if nid not in merged.memory.nodes:
                merged.memory.nodes[nid] = node
        # Merge tool chains
        for tid, tc in src.tool_chains.items():
            if tid not in merged.tool_chains:
                merged.tool_chains[tid] = tc
    return merged
