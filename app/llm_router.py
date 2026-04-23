"""LLM router — score-based multi-LLM selection.

Replaces the string-label-based auto_route with capability-driven routing:

  1. Detect the current turn/iteration's category (tool-heavy / multimodal /
     reasoning / analysis / complex / default) from message signals.
  2. Rank the agent's extra_llms slots by their score for that category.
     Per-slot user-declared `scores` wins; otherwise fall back to the public
     benchmark scores bundled in ``app/data/model_scores.json``; otherwise
     neutral 5.0.
  3. Return (provider, model) of the winner; fall back to primary if no
     extra_llms slot is eligible.

Nothing here runs an LLM — pure config-driven routing. Safe to import from
both ``agent.py`` and ``agent_execution.py`` (no circular deps).
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any, Iterable, Optional

logger = logging.getLogger("tudou.llm_router")


# Canonical category set — keep in sync with model_scores.json "categories".
CATEGORIES = ("tool-heavy", "multimodal", "reasoning", "analysis",
              "complex", "default")
# Default score for any (model, category) pair we can't resolve.
NEUTRAL_SCORE = 5.0

# ---------------------------------------------------------------------------
# JSON loader — cached, read once per process.
# ---------------------------------------------------------------------------

_scores_cache: Optional[dict] = None
_cache_lock = threading.Lock()


def _scores_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "model_scores.json"


def load_scores() -> dict:
    """Return the parsed model_scores.json, or an empty shell on failure."""
    global _scores_cache
    if _scores_cache is not None:
        return _scores_cache
    with _cache_lock:
        if _scores_cache is not None:
            return _scores_cache
        path = _scores_path()
        try:
            with path.open("r", encoding="utf-8") as f:
                _scores_cache = json.load(f)
        except (FileNotFoundError, OSError, json.JSONDecodeError) as e:
            logger.warning("llm_router: failed to load %s: %s", path, e)
            _scores_cache = {"models": {}, "aliases": {}, "categories": list(CATEGORIES)}
        return _scores_cache


def clear_cache() -> None:
    """Invalidate the cached scores. For tests / hot-reload."""
    global _scores_cache
    with _cache_lock:
        _scores_cache = None


# ---------------------------------------------------------------------------
# Model name resolution — aliases + fuzzy fallback.
# ---------------------------------------------------------------------------

_NORMALIZE_STRIP = re.compile(r"^(mlx-community/|unsloth/|bartowski/|TheBloke/)",
                              re.IGNORECASE)
_QUANT_SUFFIX = re.compile(r"[-_]?(4bit|8bit|q4|q5|q6|q8|awq|gguf|int4|int8)(-\w+)?$",
                           re.IGNORECASE)


def _normalize_name(name: str) -> str:
    if not name:
        return ""
    s = name.strip()
    # Strip common hub prefixes: "mlx-community/foo" -> "foo"
    s = _NORMALIZE_STRIP.sub("", s)
    # Strip quantization tail: "Qwen2.5-32B-Instruct-4bit" -> "Qwen2.5-32B-Instruct"
    s = _QUANT_SUFFIX.sub("", s)
    return s.strip().lower()


def resolve_to_canonical(name: str, data: Optional[dict] = None) -> Optional[str]:
    """Return the canonical key in scores['models'] for a given model name.

    Tries, in order:
      1. Exact match (case-insensitive) against keys in scores['models']
      2. Alias lookup (case-insensitive) against scores['aliases']
      3. Normalized-stripped version of the name (strip MLX prefix / quant suffix)
      4. Partial match — if exactly one canonical key contains the normalized
         name as a substring, accept it
    Returns None when no match is found.
    """
    if not name:
        return None
    d = data or load_scores()
    models = d.get("models", {}) or {}
    aliases = d.get("aliases", {}) or {}

    # 1. exact (case-insensitive)
    for k in models:
        if k.lower() == name.lower():
            return k

    # 2. alias
    aid = aliases.get(name.lower()) or aliases.get(name)
    if aid and aid in models:
        return aid

    # 3. normalized lookup
    norm = _normalize_name(name)
    if norm != name.lower():
        aid2 = aliases.get(norm)
        if aid2 and aid2 in models:
            return aid2
        for k in models:
            if _normalize_name(k) == norm:
                return k

    # 4. substring — only if unambiguous
    hits = [k for k in models if norm and norm in k.lower()]
    if len(hits) == 1:
        return hits[0]
    return None


def score_for_model(model_name: str, category: str,
                    data: Optional[dict] = None) -> float:
    """Return the public benchmark score (0-10) for (model, category).

    Missing model / missing category / null value → NEUTRAL_SCORE (5.0).
    """
    d = data or load_scores()
    canonical = resolve_to_canonical(model_name, d) or "_unknown"
    entry = (d.get("models") or {}).get(canonical) or {}
    v = entry.get(category)
    if v is None:
        return NEUTRAL_SCORE
    try:
        return float(v)
    except (TypeError, ValueError):
        return NEUTRAL_SCORE


# ---------------------------------------------------------------------------
# Category detection — signals + keywords.
# ---------------------------------------------------------------------------

# Chinese + English triggers. Order inside a category doesn't matter.
_REASONING_KEYWORDS = (
    # CN
    "分析", "推理", "为什么", "解释", "对比", "比较", "评估", "思考",
    "权衡", "原因", "论证", "推导", "洞察", "深度",
    # EN
    "analyze", "reasoning", "explain why", "compare", "evaluate", "think through",
    "rationale", "deeper", "insight", "synthesize",
)
_ANALYSIS_KEYWORDS = (
    # CN — emphasizes written analysis / reporting vs. pure reasoning
    "总结", "盘点", "总结一下", "报告", "洞察报告", "综述", "综合分析",
    "解读", "调研", "梳理",
    # EN
    "summarize", "roundup", "overview", "report on", "recap",
)
_TOOL_HEAVY_KEYWORDS = (
    # CN — imperative verbs with side effects
    "生成", "创建", "发送", "发邮件", "发消息", "运行", "执行",
    "下载", "上传", "写一个", "做一个", "帮我发", "帮我存", "帮我下载",
    "帮我创建", "帮我生成", "导出", "导入", "部署", "推送",
    "调用", "测试一下",
    # EN
    "generate", "create", "send", "run", "execute", "download",
    "upload", "deploy", "push", "commit", "export", "build",
)


def _message_text(user_message: Any) -> str:
    """Extract searchable text from whatever the chat loop passes in."""
    if not user_message:
        return ""
    if isinstance(user_message, str):
        return user_message
    if isinstance(user_message, dict):
        return str(user_message.get("content", "") or "")
    if isinstance(user_message, list):
        parts = []
        for p in user_message:
            if isinstance(p, dict):
                t = p.get("text") or p.get("content") or ""
                if isinstance(t, str):
                    parts.append(t)
        return "\n".join(parts)
    return str(user_message or "")


def _message_is_multimodal(user_message: Any) -> bool:
    if not isinstance(user_message, list):
        return False
    for p in user_message:
        if isinstance(p, dict):
            t = p.get("type") or ""
            if t in ("image_url", "image", "audio", "audio_url", "input_audio"):
                return True
    return False


def _any_keyword(text: str, kws: Iterable[str]) -> bool:
    tl = text.lower()
    for kw in kws:
        if kw.lower() in tl:
            return True
    return False


def detect_category(user_message: Any = None,
                    has_tools: bool = False,
                    recent_tool_call_density: float = 0.0,
                    complex_threshold_chars: int = 2000) -> str:
    """Classify the current LLM turn into one of ``CATEGORIES``.

    Priority (first match wins):
      1. multimodal  — message has image/audio parts
      2. reasoning   — reasoning-keyword hit AND not dominated by tool-verbs
      3. analysis    — analysis/reporting keywords
      4. tool-heavy  — imperative verbs OR tools are already being used densely
      5. complex     — long prompt above the threshold
      6. default
    """
    if _message_is_multimodal(user_message):
        return "multimodal"

    text = _message_text(user_message)

    reasoning_hit = _any_keyword(text, _REASONING_KEYWORDS)
    tool_hit = _any_keyword(text, _TOOL_HEAVY_KEYWORDS)
    analysis_hit = _any_keyword(text, _ANALYSIS_KEYWORDS)

    # Reasoning wins over tool-heavy when BOTH are present and the user is
    # asking "why / compare / explain" — those require thinking regardless
    # of whether tools are involved.
    if reasoning_hit and not (tool_hit and not reasoning_hit):
        return "reasoning"
    if analysis_hit:
        return "analysis"
    if tool_hit or has_tools and recent_tool_call_density >= 0.5:
        return "tool-heavy"
    if complex_threshold_chars > 0 and len(text) >= complex_threshold_chars:
        return "complex"
    return "default"


# ---------------------------------------------------------------------------
# Slot picker — "best slot for category".
# ---------------------------------------------------------------------------

def _slot_score(slot: dict, category: str, data: Optional[dict] = None) -> float:
    """Score a single slot for a category.

    Precedence: user-declared `scores` on the slot → public benchmark score
    for the slot's model → NEUTRAL_SCORE.
    """
    if not isinstance(slot, dict):
        return NEUTRAL_SCORE
    user_scores = slot.get("scores")
    if isinstance(user_scores, dict):
        v = user_scores.get(category)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    mdl = str(slot.get("model", "")).strip()
    if not mdl:
        return NEUTRAL_SCORE
    return score_for_model(mdl, category, data)


def best_slot_for_category(
    extra_llms: Iterable[dict],
    category: str,
    primary_provider: str = "",
    primary_model: str = "",
    data: Optional[dict] = None,
) -> tuple[str, str, dict | None]:
    """Pick the (provider, model, winning_slot) for the category.

    Priority rules (first match wins):
      1. **Purpose match** — a slot whose ``purpose`` (or ``label``) equals
         the current category is the user's explicit "this slot is my X"
         declaration. That intent beats raw score. Only requires the slot
         to have a provider or model actually configured.
      2. **Highest score** — among remaining candidates (primary + slots
         not already elected above), pick the one with the largest
         score for the requested category; default-score used as
         tie-breaker. Primary wins on equal score (stable sort).

    Returns (provider, model, slot_dict_or_None). slot_dict is None when
    primary wins (either by score or when no extra_llms configured).
    """
    d = data or load_scores()

    # --- Rule 1: explicit purpose match ---
    cat_lc = (category or "").lower()
    for slot in (extra_llms or []):
        if not isinstance(slot, dict):
            continue
        tag = str(slot.get("purpose") or slot.get("label") or "").strip().lower()
        if tag and tag == cat_lc:
            prov = str(slot.get("provider", "")).strip() or primary_provider
            mdl = str(slot.get("model", "")).strip() or primary_model
            if prov or mdl:
                return prov, mdl, slot

    # --- Rule 2: score-based picking ---
    candidates: list[dict] = []
    if primary_provider or primary_model:
        candidates.append({
            "_is_primary": True,
            "label": "primary",
            "provider": primary_provider,
            "model": primary_model,
        })
    for slot in (extra_llms or []):
        if isinstance(slot, dict):
            candidates.append(slot)

    if not candidates:
        return primary_provider, primary_model, None

    def _key(s: dict) -> tuple[float, float]:
        return (_slot_score(s, category, d),
                _slot_score(s, "default", d))

    winner = max(candidates, key=_key)
    prov = str(winner.get("provider", "")).strip() or primary_provider
    mdl = str(winner.get("model", "")).strip() or primary_model
    if winner.get("_is_primary"):
        return prov, mdl, None
    return prov, mdl, winner


# ---------------------------------------------------------------------------
# System-prompt scores hint — injects a compact table of candidate LLMs and
# their per-category scores so the primary LLM can make informed routing
# decisions when calling plan_update(create_plan, ...). Returns "" when the
# agent has no extra_llms configured (nothing to route between).
# ---------------------------------------------------------------------------

def build_scores_hint_for_agent(primary_provider: str,
                                primary_model: str,
                                extra_llms: list[dict],
                                data: Optional[dict] = None) -> str:
    """Return a markdown block describing each candidate LLM's scores."""
    if not extra_llms:
        return ""
    d = data or load_scores()
    rows = []
    # Primary row
    if primary_model:
        scores = {cat: score_for_model(primary_model, cat, d)
                  for cat in ("tool-heavy", "multimodal", "reasoning",
                              "analysis", "default")}
        rows.append(("primary", primary_provider or "?", primary_model, scores))
    # Extra slots
    for slot in extra_llms:
        if not isinstance(slot, dict):
            continue
        label = (slot.get("label") or slot.get("purpose")
                 or slot.get("model") or "?")
        mdl = str(slot.get("model") or "").strip()
        prov = str(slot.get("provider") or "").strip()
        scores = {}
        for cat in ("tool-heavy", "multimodal", "reasoning",
                    "analysis", "default"):
            scores[cat] = _slot_score(slot, cat, d)
        rows.append((label, prov, mdl, scores))
    if len(rows) < 2:
        return ""
    header = ("## 可用 LLM 及各类别评分（0-10，越高越合适）\n\n"
              "| Label | Provider/Model | tool-heavy | multimodal "
              "| reasoning | analysis | default |\n"
              "|-------|---------------|-----------|-----------"
              "|-----------|----------|---------|\n")
    for label, prov, mdl, sc in rows:
        header += (f"| {label} | {prov}/{mdl or '-'} "
                   f"| {sc['tool-heavy']:.1f} | {sc['multimodal']:.1f} "
                   f"| {sc['reasoning']:.1f} | {sc['analysis']:.1f} "
                   f"| {sc['default']:.1f} |\n")
    header += (
        "\n**调 plan_update(action='create_plan') 时，每个 step 请带 `llm_purpose` 字段**，"
        "从 `tool-heavy / multimodal / reasoning / analysis / default` 里选一个，"
        "系统会按上表评分自动把该步派给最合适的 LLM。可选填 `llm_rationale` 说明理由。\n"
    )
    return header

