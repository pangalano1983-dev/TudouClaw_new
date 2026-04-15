"""
Intent Resolver: Pre-LLM classification and slot extraction middleware for TudouClaw agents.

This module provides a lightweight intent understanding layer that runs BEFORE the main LLM call.
It performs:
  1. Fast rule-based classification (regex + keywords in Chinese and English)
  2. Parameter slot extraction from the message
  3. Missing required slot detection
  4. Confidence scoring with clarification question generation
  5. Workflow template matching

The resolver uses a two-tier approach:
  - Rule-based fast path: returns high-confidence results immediately
  - LLM-based slow path: for ambiguous cases using the agent's learning_model
"""

from __future__ import annotations
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from app import llm

logger = logging.getLogger("tudou.intent_resolver")


# ──────────────────────────────────────────────────────────────────────────────
# DATA STRUCTURES
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class IntentSlot:
    """Represents a parameter slot extracted from the message."""
    name: str
    value: Any = None
    required: bool = False
    extracted: bool = False  # Was it found in the message?
    confidence: float = 1.0  # Extraction confidence (0.0-1.0)


@dataclass
class ResolvedIntent:
    """The result of intent resolution."""
    category: str              # Intent category (e.g., "code_task", "query")
    confidence: float          # Overall confidence (0.0-1.0)
    slots: dict[str, IntentSlot]  # Extracted parameters
    missing_required: list[str]   # Names of missing required slots
    suggested_workflow: Optional[str] = None  # Matching workflow template ID
    clarification: Optional[str] = None       # Generated clarification question
    raw_message: str = ""       # Original user message
    resolution_method: str = "rule"  # "rule" or "llm"

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "category": self.category,
            "confidence": self.confidence,
            "slots": {
                name: {
                    "name": slot.name,
                    "value": slot.value,
                    "required": slot.required,
                    "extracted": slot.extracted,
                    "confidence": slot.confidence,
                }
                for name, slot in self.slots.items()
            },
            "missing_required": self.missing_required,
            "suggested_workflow": self.suggested_workflow,
            "clarification": self.clarification,
            "raw_message": self.raw_message,
            "resolution_method": self.resolution_method,
        }


# ──────────────────────────────────────────────────────────────────────────────
# RULE PATTERNS AND SCHEMAS
# ──────────────────────────────────────────────────────────────────────────────

# Intent category keywords (Chinese + English)
INTENT_PATTERNS = {
    "code_task": {
        "keywords": [
            # English
            "write code", "code", "implement", "fix", "debug", "refactor",
            "optimize", "edit code", "review code", "test", "coding", "write",
            # Chinese
            "写代码", "编写", "修复", "调试", "重构", "优化", "编码",
            "代码审查", "测试", "实现", "改进", "编个",
        ],
        "patterns": [
            r"(?:write|implement|fix|refactor|optimize|code|debug).{0,30}(?:code|function|class|method|script)",
            r"(?:写|编|修|重|优).{0,10}(?:代码|函数|类|脚本|程序)",
            r"编写.{0,30}(?:函数|代码|程序|脚本)",
        ],
    },
    "query": {
        "keywords": [
            # English
            "what is", "how to", "explain", "what does", "why", "when",
            "which", "where", "how", "search", "find", "information",
            "ask", "question", "help", "tell me", "show me", "list",
            # Chinese
            "什么是", "怎么", "如何", "为什么", "解释", "说明", "告诉我",
            "查询", "搜索", "找", "信息", "问题", "帮助", "显示", "列表",
            "怎样", "请问",
        ],
        "patterns": [
            r"(?:what|how|why|explain|tell|show).{0,50}(?:\?|是什么|怎样|如何)",
            r"(?:怎么|如何|什么是|为什么|怎样|请问).{0,30}",
            r"(?:请问|怎样).{0,40}(?:\？|\?)",
        ],
    },
    "deployment": {
        "keywords": [
            # English
            "deploy", "release", "launch", "ship", "publish", "upload",
            "rollback", "promote", "ci/cd", "pipeline", "build", "push",
            # Chinese
            "部署", "发布", "上线", "发送", "推送", "回滚", "构建",
            "流水线", "上传", "打包",
        ],
        "patterns": [
            r"(?:deploy|release|rollback|promote|publish).{0,30}",
            r"(?:部署|发布|上线|回滚).{0,30}",
        ],
    },
    "communication": {
        "keywords": [
            # English
            "send email", "email", "message", "notify", "alert", "tell",
            "inform", "contact", "reach out", "send message", "slack",
            # Chinese
            "发邮件", "邮件", "消息", "通知", "告知", "联系", "发消息",
            "提醒", "信息",
        ],
        "patterns": [
            r"(?:send|email|message|notify|contact).{0,40}",
            r"(?:发|邮|消息|通知).{0,30}",
        ],
    },
    "file_operation": {
        "keywords": [
            # English
            "create file", "read", "write", "delete", "edit", "open",
            "save", "file", "document", "folder", "directory", "copy",
            # Chinese
            "创建文件", "读取", "写入", "删除", "编辑", "打开", "保存",
            "文件", "文档", "目录", "复制",
        ],
        "patterns": [
            r"(?:create|read|write|delete|edit|open|save).{0,30}file",
            r"(?:创建|读|写|删|编|打开|保存).{0,20}(?:文件|文档|目录)",
        ],
    },
    "workflow": {
        "keywords": [
            # English
            "workflow", "start", "run", "execute", "pipeline", "process",
            "trigger", "automate", "task", "job",
            # Chinese
            "工作流", "流程", "开始", "运行", "执行", "自动化", "任务",
            "触发", "管道",
        ],
        "patterns": [
            r"(?:start|run|trigger|execute).{0,30}(?:workflow|pipeline|process)",
            r"(?:开始|运行|执行|触发).{0,20}(?:工作流|流程|任务)",
        ],
    },
    "task_management": {
        "keywords": [
            # English
            "create task", "task", "todo", "add task", "list tasks",
            "update", "mark", "complete", "done", "status",
            # Chinese
            "创建任务", "任务", "待办", "添加", "列表", "标记", "完成",
            "状态", "更新",
        ],
        "patterns": [
            r"(?:create|add|list|update|mark).{0,30}(?:task|todo)",
            r"(?:创建|添加|列表|更新|标记).{0,20}(?:任务|待办)",
        ],
    },
    "learning": {
        "keywords": [
            # English
            "learn", "study", "research", "understand", "teach", "explain",
            "knowledge", "training", "course", "tutorial",
            # Chinese
            "学习", "研究", "理解", "教", "知识", "培训", "课程",
            "教程", "学", "讲解",
        ],
        "patterns": [
            r"(?:learn|study|research|understand).{0,40}",
            r"(?:学习|研究|理解|教).{0,30}",
        ],
    },
    "configuration": {
        "keywords": [
            # English
            "configure", "config", "setting", "setup", "change", "enable",
            "disable", "option", "preference", "debug mode", "logging",
            # Chinese
            "配置", "设置", "选项", "启用", "禁用", "改变", "调整",
            "参数", "配置项", "调试",
        ],
        "patterns": [
            r"(?:configure|setup|change|enable|disable).{0,30}(?:setting|option|config|mode|logging)",
            r"(?:enable|disable).{0,20}(?:debug|logging|mode)",
            r"(?:配置|设置|改变|启用|禁用).{0,20}",
            r"(?:启用|禁用).{0,20}(?:调试|日志)",
        ],
    },
}

# Slot schemas per category
SLOT_SCHEMAS = {
    "code_task": [
        IntentSlot("target_file", required=False),
        IntentSlot("language", required=False),
        IntentSlot("action", required=True),  # write/fix/refactor
        IntentSlot("description", required=True),
    ],
    "query": [
        IntentSlot("question", required=True),
        IntentSlot("context", required=False),
        IntentSlot("scope", required=False),
    ],
    "deployment": [
        IntentSlot("target_env", required=True),  # dev/staging/prod
        IntentSlot("service", required=False),
        IntentSlot("version", required=False),
    ],
    "communication": [
        IntentSlot("to", required=True),
        IntentSlot("subject", required=False),
        IntentSlot("body", required=True),
        IntentSlot("channel", required=False),  # email/slack/etc
    ],
    "file_operation": [
        IntentSlot("file_path", required=True),
        IntentSlot("action", required=True),  # create/read/edit/delete
        IntentSlot("content", required=False),
    ],
    "workflow": [
        IntentSlot("workflow_id", required=True),
        IntentSlot("parameters", required=False),
    ],
    "task_management": [
        IntentSlot("action", required=True),  # create/update/list
        IntentSlot("task_title", required=False),
        IntentSlot("priority", required=False),
    ],
    "learning": [
        IntentSlot("topic", required=True),
        IntentSlot("level", required=False),  # beginner/intermediate/advanced
    ],
    "configuration": [
        IntentSlot("setting_name", required=True),
        IntentSlot("setting_value", required=False),
    ],
}

# Workflow template mappings
WORKFLOW_CATALOG = {
    "code_task": ["catalog_product_dev", "catalog_code_review"],
    "deployment": ["catalog_cicd_release"],
    "query": ["catalog_data_analysis"],
    "communication": ["catalog_notification"],
}


# ──────────────────────────────────────────────────────────────────────────────
# INTENT RESOLVER
# ──────────────────────────────────────────────────────────────────────────────


class IntentResolver:
    """Pre-LLM intent classification and slot extraction layer.

    Two-tier approach:
      1. Rule-based fast path: regex + keyword matching (Chinese + English)
      2. LLM-based slow path: for ambiguous cases using the agent's learning_model

    Usage:
        resolver = IntentResolver()
        intent = resolver.resolve(
            message="Fix the bug in main.py",
            agent_role="developer",
            history=[...],  # optional conversation history
        )
        if intent.missing_required:
            print(f"Missing: {intent.missing_required}")
            print(f"Ask user: {intent.clarification}")
    """

    # Configuration
    CONFIDENCE_THRESHOLD = 0.7  # Below this, generate clarification
    RULE_CONFIDENCE_HIGH = 0.85
    RULE_CONFIDENCE_MEDIUM = 0.65
    RULE_CONFIDENCE_LOW = 0.45

    def __init__(self, llm_call_fn: Optional[Callable] = None) -> None:
        """Initialize the IntentResolver.

        Args:
            llm_call_fn: Optional callable(messages, provider, model) -> dict
                        for LLM-based classification. If None, uses app.llm.chat_no_stream.
        """
        self.llm_call_fn = llm_call_fn or llm.chat_no_stream
        logger.info("IntentResolver initialized")

    def resolve(
        self,
        message: str,
        agent_role: str = "",
        history: Optional[list[dict]] = None,
        available_tools: Optional[list[str]] = None,
        learning_provider: str = "",
        learning_model: str = "",
    ) -> ResolvedIntent:
        """Resolve user intent from message.

        Args:
            message: User message text
            agent_role: Agent's role for context (e.g., "developer", "pm")
            history: Conversation history (list of {"role": "user"/"assistant", "content": "..."})
            available_tools: List of available tool names for context
            learning_provider: LLM provider for classification (cheap/fast)
            learning_model: LLM model for classification

        Returns:
            ResolvedIntent: Classified intent with slots, confidence, and clarifications
        """
        if not message or not message.strip():
            return ResolvedIntent(
                category="general",
                confidence=0.0,
                slots={},
                missing_required=[],
                raw_message="",
                resolution_method="rule",
            )

        message = message.strip()
        logger.debug(f"Resolving intent for: {message[:100]}")

        # Step 1: Rule-based classification (fast path)
        category, rule_confidence = self._rule_based_classify(message)
        resolution_method = "rule"

        # Step 2: If confidence is low, try LLM-based classification
        if rule_confidence < self.CONFIDENCE_THRESHOLD and (
            learning_provider or learning_model
        ):
            logger.debug(
                f"Rule confidence {rule_confidence:.2f} below threshold, "
                f"trying LLM classification"
            )
            try:
                llm_category, llm_conf, llm_slots = self._llm_classify(
                    message, agent_role, history or [], learning_provider, learning_model
                )
                if llm_conf > rule_confidence:
                    category = llm_category
                    rule_confidence = llm_conf
                    resolution_method = "llm"
                    logger.debug(f"LLM classification: {category} (conf={llm_conf:.2f})")
            except Exception as e:
                logger.warning(f"LLM classification failed: {e}, falling back to rule")

        # Step 3: Extract slots for the category
        slots = self._extract_slots(message, category)

        # Step 4: Find missing required slots
        schema = SLOT_SCHEMAS.get(category, [])
        missing_required = [
            slot.name
            for slot in schema
            if slot.required and not slots.get(slot.name, IntentSlot(slot.name)).extracted
        ]

        # Step 5: Generate clarification question if confidence is low or slots are missing
        clarification = None
        if rule_confidence < self.CONFIDENCE_THRESHOLD or missing_required:
            clarification = self._generate_clarification(
                category, message, missing_required
            )

        # Step 6: Match workflow template
        suggested_workflow = self._match_workflow(category, message)

        intent = ResolvedIntent(
            category=category,
            confidence=rule_confidence,
            slots=slots,
            missing_required=missing_required,
            suggested_workflow=suggested_workflow,
            clarification=clarification,
            raw_message=message,
            resolution_method=resolution_method,
        )

        logger.debug(
            f"Resolved: category={category}, conf={rule_confidence:.2f}, "
            f"missing={missing_required}, method={resolution_method}"
        )
        return intent

    def _rule_based_classify(self, message: str) -> tuple[str, float]:
        """Fast regex/keyword classification.

        Returns:
            (category, confidence) tuple
        """
        message_lower = message.lower()

        # Strong indicators that override others (query question marks, etc.)
        query_indicators = ["怎么", "怎样", "如何", "为什么", "什么是", "请问"]
        if any(indicator in message for indicator in query_indicators):
            if "？" in message or "?" in message:
                return "query", 0.95

        scores = {}
        for category, patterns in INTENT_PATTERNS.items():
            score = 0.0

            # Keyword matching
            keyword_matches = sum(
                1 for kw in patterns["keywords"] if kw.lower() in message_lower
            )
            if keyword_matches > 0:
                score = min(1.0, keyword_matches * 0.3)

            # Regex pattern matching
            for pattern in patterns.get("patterns", []):
                try:
                    if re.search(pattern, message_lower, re.IGNORECASE):
                        score = max(score, 0.8)
                except re.error:
                    logger.warning(f"Invalid regex pattern: {pattern}")

            scores[category] = score

        # Find best match
        if not scores or max(scores.values()) == 0:
            return "general", 0.5

        best_category = max(scores, key=scores.get)
        confidence = scores[best_category]

        return best_category, confidence

    def _llm_classify(
        self,
        message: str,
        agent_role: str,
        history: list[dict],
        learning_provider: str,
        learning_model: str,
    ) -> tuple[str, float, dict]:
        """LLM-based classification for ambiguous cases.

        Returns:
            (category, confidence, extra_slots) tuple
        """
        categories = ", ".join(INTENT_PATTERNS.keys())
        prompt = f"""Classify the user's intent into one of these categories:
{categories}

User role: {agent_role or 'general'}
User message: {message}

Respond in JSON format:
{{
  "category": "<category_name>",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}}

Use ONLY the category names listed above. Confidence should reflect how certain you are.
"""

        messages = [
            {"role": "system", "content": "You are an intent classifier for an AI agent platform."},
            {"role": "user", "content": prompt},
        ]

        try:
            resp = self.llm_call_fn(
                messages, tools=None, provider=learning_provider, model=learning_model
            )
            content = resp.get("message", {}).get("content", "")

            # Parse JSON response
            import json

            # Try to extract JSON from response
            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                category = result.get("category", "general").strip().lower()
                confidence = float(result.get("confidence", 0.5))

                # Validate category
                if category not in INTENT_PATTERNS:
                    category = "general"

                return category, confidence, {}
            else:
                logger.warning(f"Could not parse LLM response: {content}")
                return "general", 0.5, {}
        except Exception as e:
            logger.error(f"LLM classification error: {e}")
            raise

    def _extract_slots(self, message: str, category: str) -> dict[str, IntentSlot]:
        """Extract known parameter slots from message text.

        This is a simple rule-based extraction. For more sophisticated extraction,
        this could be enhanced with NER or use a dedicated slot filling model.

        Args:
            message: User message
            category: Intent category

        Returns:
            Dictionary of {slot_name: IntentSlot}
        """
        slots: dict[str, IntentSlot] = {}
        schema = SLOT_SCHEMAS.get(category, [])

        for slot_template in schema:
            slot = IntentSlot(
                name=slot_template.name,
                required=slot_template.required,
                extracted=False,
            )

            # Simple extraction heuristics per slot type
            if slot.name == "target_file":
                # Look for file paths (.*\.py, file.txt, etc.)
                match = re.search(
                    r"(?:file|in|from|to|update)\s+([/\w\-._]+\.(?:py|js|txt|yaml|json))",
                    message,
                    re.IGNORECASE,
                )
                if match:
                    slot.value = match.group(1)
                    slot.extracted = True

            elif slot.name == "action":
                # Look for actions like fix, write, refactor, deploy, send, etc.
                actions = {
                    "code_task": ["fix", "write", "implement", "refactor", "optimize"],
                    "file_operation": ["create", "read", "edit", "delete"],
                    "deployment": ["deploy", "release", "rollback"],
                    "communication": ["send", "notify"],
                    "workflow": ["start", "run", "trigger"],
                    "task_management": ["create", "update", "list"],
                }
                category_actions = actions.get(category, [])
                for action in category_actions:
                    if action.lower() in message.lower():
                        slot.value = action
                        slot.extracted = True
                        break

            elif slot.name == "description":
                # Use remaining message after removing common patterns
                desc = re.sub(r"^\s*(?:fix|write|create|deploy|send)\.?\s+", "", message, flags=re.IGNORECASE)
                if desc and len(desc) > 3:
                    slot.value = desc[:200]  # Limit to 200 chars
                    slot.extracted = True

            elif slot.name == "question":
                slot.value = message[:300]
                slot.extracted = True

            elif slot.name == "to":
                # Look for email or name patterns
                email_match = re.search(r"[\w\.-]+@[\w\.-]+", message)
                if email_match:
                    slot.value = email_match.group()
                    slot.extracted = True
                else:
                    # Look for "to <name>" pattern
                    to_match = re.search(r"(?:to|send\s+to)\s+([A-Z][a-zA-Z\s]+)", message)
                    if to_match:
                        slot.value = to_match.group(1).strip()
                        slot.extracted = True

            elif slot.name == "target_env":
                # Look for environment keywords
                envs = ["dev", "development", "staging", "prod", "production", "test"]
                for env in envs:
                    if env.lower() in message.lower():
                        slot.value = env
                        slot.extracted = True
                        break

            elif slot.name == "topic":
                slot.value = message[:300]
                slot.extracted = True

            slots[slot.name] = slot

        return slots

    def _generate_clarification(
        self, category: str, message: str, missing_required: list[str]
    ) -> Optional[str]:
        """Generate a natural clarification question.

        Args:
            category: Intent category
            message: Original message
            missing_required: List of missing required slot names

        Returns:
            Clarification question or None
        """
        if not missing_required:
            # Low confidence but slots are complete
            return f"Just to confirm, you want to {category.replace('_', ' ')}. Is that right?"

        # Build clarification for missing slots
        clarification_map = {
            "action": "What specific action would you like to perform?",
            "description": "Could you provide more details about what you need?",
            "target_file": "Which file should I work on?",
            "target_env": "Which environment should I deploy to (dev/staging/prod)?",
            "to": "Who should I send this to?",
            "question": "What would you like to know more about?",
            "topic": "What topic would you like to learn about?",
            "file_path": "What file path are you referring to?",
            "body": "What's the content/body of your message?",
        }

        missing_clauses = [
            clarification_map.get(slot, f"Could you provide {slot}?")
            for slot in missing_required[:2]  # Ask about first 2 missing
        ]

        if len(missing_clauses) == 1:
            return f"I need a bit more info: {missing_clauses[0]}"
        else:
            return f"A few clarifications: {' Also, '.join(missing_clauses)}"

    def _match_workflow(self, category: str, message: str) -> Optional[str]:
        """Find matching workflow template from catalog.

        Args:
            category: Intent category
            message: Original message

        Returns:
            Workflow template ID or None
        """
        templates = WORKFLOW_CATALOG.get(category)
        if not templates:
            return None

        # Simple heuristic: return first matching template
        # Could be enhanced with more sophisticated matching
        return templates[0]


# ──────────────────────────────────────────────────────────────────────────────
# CONVENIENCE FUNCTIONS
# ──────────────────────────────────────────────────────────────────────────────


def create_resolver(llm_call_fn: Optional[Callable] = None) -> IntentResolver:
    """Factory function to create an IntentResolver.

    Args:
        llm_call_fn: Optional custom LLM calling function

    Returns:
        IntentResolver instance
    """
    return IntentResolver(llm_call_fn=llm_call_fn)


__all__ = [
    "IntentResolver",
    "IntentSlot",
    "ResolvedIntent",
    "create_resolver",
    "INTENT_PATTERNS",
    "SLOT_SCHEMAS",
    "WORKFLOW_CATALOG",
]
