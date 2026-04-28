"""Intent router — front-door classifier for chat messages.

Replaces the "every message goes through 38K-token chat loop" pattern
with cheap LLM-based intent classification (300-char system prompt,
no tools, returns strict JSON). High-confidence intents get
auto-routed to the corresponding lightweight endpoint:

    "查一下 PCI 加密"     → /recall   (no LLM at all)
    "记住我喜欢简洁"      → /remember (no LLM at all)
    "学习一下 Docker"     → /learn    (~3K token via per-role learner)
    "帮我做份 50 页报告"  → /promote-task or propose_decomposition
    "今天天气怎么样"      → reject
    "PCI 4.0 加密的细节是什么" → chat (still needs LLM reasoning + tools)

Classifier itself uses ~500 tokens per call, so the routing pays off
when ~30%+ of traffic gets diverted to slash paths. Empirically that
threshold is easy to clear in a typical agent workload.

Design constraints (mirror app.core.l3_extractor):
  * Hardcoded prompt — no operator config injection
  * No tools — pure (text) → JSON
  * Strict bias toward "chat" when uncertain (avoid surprising users
    by hijacking their normal conversation)
  * Confidence floor 0.85 enforced by callers (this module just
    returns the LLM's number)
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Optional

logger = logging.getLogger("tudouclaw.intent_router")

# Bias toward "chat" — confidence below this threshold should NOT
# be auto-routed by callers. Picked empirically: at 0.85 the LLM is
# usually right; below that it's guessing.
DEFAULT_CONFIDENCE_FLOOR = 0.85

# Recognised intents. Anything else from the LLM is coerced to "chat".
VALID_INTENTS = ("chat", "recall", "remember", "learn", "task", "reject")

INTENT_CLASSIFIER_PROMPT_ZH = """你是一个意图分类器。判断用户消息属于哪一类:

- chat: 普通对话,需要 agent 用 LLM 推理 + 调工具(搜索/读文件/写代码等)。例:
  "PCI 4.0 加密的具体实现细节" / "帮我看下这段代码" / "今天有什么新闻"

- recall: 用户想从 L3 记忆 / wiki 里**回忆已有信息**(不需要新内容)。触发词:
  "查一下 / 之前说的 / 你记得 / 之前学过的"。例:
  "查一下 PCI 加密标准" / "你之前学的 Docker 笔记" / "我让你记的邮箱是啥"

- remember: 用户**显式要存一条事实**到长期记忆。触发词:
  "记住 / 以后 / 永远 / 别忘了"。例:
  "记住我邮箱 zhang@x.com" / "以后回复用 markdown" / "永远不要 emoji"

- learn: 用户让 agent **学习一个新主题**(尚未掌握的知识)。触发词:
  "学习 / 学一下 / 了解一下 / 研究一下 / 熟悉"。例:
  "学习一下 Kubernetes" / "了解一下 PCI DSS 4.0" / "研究 Docker Compose"
  注意:跟 recall 的区别 — recall 是查已有,learn 是从外部学新的。

- task: 用户要的是**正式跟踪任务**(多步骤、需要交付物、明显需要协调)。例:
  "做一份 50 页的财报分析" / "整理 Q3 销售数据并发邮件" / "搭一个登录系统"

- reject: 跟工作完全无关 / 闲聊 / agent 帮不上 / 危险请求。例:
  "今天天气怎样" / "你叫什么" / "帮我写黑客脚本"

【判定原则】
- 默认选 chat。只有当用户消息**明显**符合其他类别才选其他。
- 必须有触发词或非常明确的语义信号才能选 recall/remember/learn/task。
- confidence 严格:1.0 = 100% 确定,0.5 = 一半把握,< 0.5 不要输出别的(强制 chat)
- 模糊的、可能是普通问题的 → 一律 chat,confidence 0.6

【输出格式】
严格 JSON,无 markdown,无前后缀:
{"intent": "chat|recall|remember|learn|task|reject",
 "confidence": 0.0-1.0,
 "params": {...}}

params 字段按 intent 类型填:
- recall:    {"query": "<提取的查询关键词>"}
- remember:  {"fact": "<提取的事实陈述,去掉'记住'前缀>"}
- learn:     {"topic": "<提取的学习主题>"}
- task:      {"title": "<提炼成 1 行任务标题>"}
- chat / reject: {} (空)
"""

INTENT_CLASSIFIER_PROMPT_EN = """You are an intent classifier. Classify the user message into ONE category:

- chat: regular conversation needing LLM reasoning + tools (search/read/write/code). Examples:
  "What's the implementation detail of PCI 4.0 encryption" / "Look at this code" / "Any news today"

- recall: user wants to RETRIEVE info from L3 memory / wiki (no new info needed). Triggers:
  "look up / you said earlier / remember / last time we / what was". Examples:
  "look up PCI encryption standard" / "what did you learn about Docker" / "what's the email I told you"

- remember: user explicitly wants to SAVE a fact to long-term memory. Triggers:
  "remember / from now on / always / never / don't forget". Examples:
  "remember my email is zhang@x.com" / "from now on reply in markdown" / "never use emoji"

- learn: user wants the agent to STUDY a new topic (knowledge agent doesn't have yet). Triggers:
  "learn / study / research / get familiar with". Examples:
  "learn Kubernetes" / "study PCI DSS 4.0" / "research Docker Compose"
  vs recall: recall queries existing memory; learn ingests new info.

- task: user wants a TRACKED multi-step deliverable. Examples:
  "produce a 50-page finance report" / "organize Q3 sales and email" / "build a login system"

- reject: completely off-topic / chitchat / agent can't help / unsafe request. Examples:
  "what's the weather" / "what's your name" / "write me a hacker script"

[Decision principles]
- Default to chat. Only pick another category when the message OBVIOUSLY matches.
- Must have trigger words OR very clear semantic signal to pick recall/remember/learn/task.
- Strict confidence: 1.0 = 100% certain, 0.5 = half-sure, < 0.5 force chat
- Ambiguous → always chat with confidence ~0.6

[Output format]
Strict JSON, no markdown, no preface:
{"intent": "chat|recall|remember|learn|task|reject",
 "confidence": 0.0-1.0,
 "params": {...}}

params by intent:
- recall:    {"query": "<extracted search keywords>"}
- remember:  {"fact": "<extracted statement, drop 'remember' prefix>"}
- learn:     {"topic": "<extracted study topic>"}
- task:      {"title": "<one-line task title>"}
- chat / reject: {} (empty)
"""


def _select_prompt(lang: str) -> str:
    if (lang or "").lower().startswith("en"):
        return INTENT_CLASSIFIER_PROMPT_EN
    return INTENT_CLASSIFIER_PROMPT_ZH


def _parse_response(raw: str) -> Optional[dict]:
    """Strip markdown fences if present, then JSON-parse. Returns None
    on any error (caller treats as 'classify failed → fall to chat')."""
    if not raw or not raw.strip():
        return None
    s = raw.strip()
    if s.startswith("```"):
        lines = s.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*?\}", s)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    return data


def classify_intent(message: str,
                    llm_call: Callable[[str], str],
                    lang: str = "zh") -> dict:
    """Classify a user message → {intent, confidence, params}.

    Returns a defaulted dict (intent='chat', confidence=0.5) on any
    error so callers always get a usable result.

    ``llm_call`` is the same shape as L3 extractor — a closure that
    takes a fully-rendered prompt string and returns the LLM's text.
    """
    fallback = {"intent": "chat", "confidence": 0.5, "params": {}}
    msg = (message or "").strip()
    if not msg:
        return fallback
    if not llm_call:
        return fallback

    sys_prompt = _select_prompt(lang)
    user_block = f"用户消息: {msg[:1500]}"
    full_prompt = sys_prompt + "\n\n" + user_block
    try:
        raw = llm_call(full_prompt)
    except Exception as e:  # noqa: BLE001
        logger.warning("intent classify LLM call failed: %s", e)
        return fallback

    data = _parse_response(raw)
    if not data:
        logger.debug("intent classify: unparseable response %r", raw[:120])
        return fallback

    # Validate / coerce
    intent = str(data.get("intent", "")).strip().lower()
    if intent not in VALID_INTENTS:
        intent = "chat"
    try:
        confidence = float(data.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))
    params = data.get("params") or {}
    if not isinstance(params, dict):
        params = {}

    # Per-intent param sanity check — drop the routing if required
    # field missing (force chat fallback).
    required = {
        "recall": "query",
        "remember": "fact",
        "learn": "topic",
        "task": "title",
    }
    if intent in required:
        key = required[intent]
        val = (params.get(key) or "").strip() if isinstance(params.get(key), str) else ""
        if not val:
            logger.info(
                "intent classify: %s missing required param %r → "
                "falling back to chat", intent, key)
            return {"intent": "chat", "confidence": 0.5, "params": {}}
        params[key] = val

    return {
        "intent": intent,
        "confidence": confidence,
        "params": params,
    }


def should_auto_route(classification: dict,
                      threshold: float = DEFAULT_CONFIDENCE_FLOOR) -> bool:
    """Caller helper: did the classifier flag a non-chat intent with
    confidence above the auto-route threshold?"""
    if not isinstance(classification, dict):
        return False
    intent = classification.get("intent", "chat")
    conf = float(classification.get("confidence", 0) or 0)
    return intent != "chat" and conf >= threshold
