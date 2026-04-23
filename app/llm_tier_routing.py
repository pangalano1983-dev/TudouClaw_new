"""LLM Tier Routing — 把"能力档位"解析为具体的 provider/model。

动机：不同企业接入的 LLM 厂商千差万别（OpenAI / Anthropic / DeepSeek / 豆包 / 通义 / 本地 Ollama）。
角色配置不应硬编码具体模型名，而是声明"需要什么能力档位"：
  - reasoning_strong  — 深度推理（架构/产品设计）
  - coding_strong     — 代码生成/工具调用
  - writing_strong    — 自然语言写作（PM/Writer）
  - fast_cheap        — 快速便宜（日常/转写/摘要）
  - multimodal        — 图文音视频
  - domain_specific   — 领域微调

管理员在系统设置里维护「档位 → provider/model」映射。角色 YAML 只引用档位。

智能预填：启动时检测已配置的 provider，按行业经验推荐默认映射（用户可随意覆盖）。

存储：~/.tudou_claw/llm_tiers.json
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, asdict, field
from pathlib import Path
from threading import Lock

logger = logging.getLogger("tudou.llm_tier_routing")

# ═══════════════════════════════════════════════════════════════════════════
# 标准档位定义（可扩展）
# ═══════════════════════════════════════════════════════════════════════════

STANDARD_TIERS = (
    "reasoning_strong",   # 数据分析 / 深度推理
    "coding_strong",      # 代码生成
    "writing_strong",     # 对话 / 文档写作
    "translation",        # 翻译
    "creative",           # 创意 / 营销文案
    "fast_cheap",
    "multimodal",
    "domain_specific",
)

TIER_LABELS_ZH = {
    "reasoning_strong": "数据分析 / 深度推理",
    "coding_strong": "代码生成",
    "writing_strong": "对话 / 写作",
    "translation": "翻译",
    "creative": "创意 / 营销",
    "fast_cheap": "快速便宜",
    "multimodal": "多模态",
    "domain_specific": "领域专精",
}

TIER_DESCRIPTIONS_ZH = {
    "reasoning_strong": "数据分析、复杂判断、架构设计（需要低温度保证稳定推理，如 Claude Opus / GPT-4o / DeepSeek-R1）",
    "coding_strong": "代码生成、工具调用、编程辅助（低温度降低幻觉，如 Claude Sonnet / DeepSeek-Coder / Qwen-Coder）",
    "writing_strong": "对话、PRD、纪要、用户沟通（中等温度兼顾自然和稳定，如 GPT-4o / Claude Sonnet / 文心一言）",
    "translation": "多语言翻译、术语对齐（低温度保证术语一致，如 GPT-4o / Qwen-Max / DeepSeek-v3）",
    "creative": "创意文案、营销、故事、脑暴（高温度鼓励发散，如 GPT-4o / Claude Opus / 文心一言）",
    "fast_cheap": "日常答疑、摘要、转写（如 GPT-4o-mini / Qwen-Turbo / 本地 Ollama）",
    "multimodal": "图像理解、语音转写、视频分析（如 GPT-4o / Gemini / Qwen-VL）",
    "domain_specific": "领域微调模型（如法务/医疗/金融专用，用户自部署）",
}

# 每个档位的建议 temperature — 这是"任务类型"与"采样随机度"的经验映射:
#   - 代码生成 / 数据分析 / 翻译 → 低温度（0.1–0.3）：要稳定、可复现、术语一致
#   - 对话 / 日常 / 多模态       → 中温度（0.5–0.7）：自然但不散漫
#   - 创意 / 脑暴                → 高温度（0.8–1.0）：鼓励多样化
# autofill_defaults 首次写入 tier 时会用这个表预填 temperature 字段，
# 用户在 UI 中可以随时覆盖。Sentinel -1.0 = 未设置，调用方使用 provider 默认。
TIER_DEFAULT_TEMPERATURES: dict[str, float] = {
    "reasoning_strong": 0.2,   # 数据分析 - 要确定性
    "coding_strong":    0.0,   # 代码生成 - 完全确定性，零幻觉
    "writing_strong":   0.6,   # 对话     - 自然但稳定
    "translation":      0.2,   # 翻译     - 术语一致
    "creative":         0.9,   # 创意     - 多样化
    "fast_cheap":       0.5,
    "multimodal":       0.4,
    "domain_specific":  0.2,
}


def default_temperature_for(tier: str) -> float:
    """Return the recommended temperature for ``tier``, or -1.0 (unset).

    Exposed as a helper so callers outside this module (UI catalog, tests,
    sanity checks) use one source of truth instead of re-copying the dict.
    """
    return TIER_DEFAULT_TEMPERATURES.get(tier, -1.0)


# ═══════════════════════════════════════════════════════════════════════════
# 数据结构
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class LLMTierEntry:
    tier: str
    provider: str = ""          # provider id, e.g. "openai", "anthropic"
    model: str = ""             # model name, e.g. "gpt-4o"
    fallback_tier: str = ""     # 如果本档位不可用，回退到另一档位
    enabled: bool = True
    cost_hint: str = "medium"   # low | medium | high
    note: str = ""              # 备注
    # Sampling temperature for this tier. Sentinel -1.0 means "unset" —
    # resolve_with_params returns -1.0 and the chat layer omits the
    # ``temperature`` field from the API payload (i.e. provider default
    # applies). 0.0 is a valid value (fully deterministic), so we can't
    # use 0.0 as the sentinel. Valid user range is [0.0, 2.0] depending
    # on the provider; we don't clamp here because some providers accept
    # >1 for richer exploration.
    temperature: float = -1.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "LLMTierEntry":
        # temperature back-compat: older saves lack the field → -1.0 so
        # the chat layer falls back to the provider default.
        try:
            temp = float(d.get("temperature", -1.0))
        except (TypeError, ValueError):
            temp = -1.0
        return cls(
            tier=d.get("tier", ""),
            provider=d.get("provider", ""),
            model=d.get("model", ""),
            fallback_tier=d.get("fallback_tier", ""),
            enabled=bool(d.get("enabled", True)),
            cost_hint=d.get("cost_hint", "medium"),
            note=d.get("note", ""),
            temperature=temp,
        )


# ═══════════════════════════════════════════════════════════════════════════
# 智能预填规则
# ═══════════════════════════════════════════════════════════════════════════

# provider_id → 档位的默认模型建议（启动时根据已装 provider 选择）
# 格式: provider_id → { tier: [model候选, ...] }
# 按优先级排序，取第一个可用模型
PROVIDER_TIER_HINTS: dict[str, dict[str, list[str]]] = {
    "anthropic": {
        "reasoning_strong": ["claude-opus-4", "claude-3-opus", "claude-3-5-sonnet-20241022"],
        "coding_strong": ["claude-3-5-sonnet-20241022", "claude-3-5-sonnet"],
        "writing_strong": ["claude-3-5-sonnet-20241022", "claude-3-5-sonnet"],
        "translation": ["claude-3-5-sonnet-20241022", "claude-3-5-sonnet"],
        "creative": ["claude-opus-4", "claude-3-opus", "claude-3-5-sonnet-20241022"],
        "multimodal": ["claude-3-5-sonnet-20241022"],
    },
    "openai": {
        "reasoning_strong": ["o1", "o1-preview", "gpt-4o"],
        "coding_strong": ["gpt-4o", "gpt-4-turbo"],
        "writing_strong": ["gpt-4o"],
        "translation": ["gpt-4o", "gpt-4-turbo"],
        "creative": ["gpt-4o"],
        "multimodal": ["gpt-4o"],
        "fast_cheap": ["gpt-4o-mini", "gpt-3.5-turbo"],
    },
    "deepseek": {
        "coding_strong": ["deepseek-coder", "deepseek-v3", "deepseek-chat"],
        "reasoning_strong": ["deepseek-r1", "deepseek-reasoner"],
        "translation": ["deepseek-v3", "deepseek-chat"],
        "creative": ["deepseek-v3", "deepseek-chat"],
        "fast_cheap": ["deepseek-chat"],
    },
    "doubao": {  # 豆包
        "fast_cheap": ["doubao-lite-4k", "doubao-pro-4k"],
        "writing_strong": ["doubao-pro-32k"],
        "translation": ["doubao-pro-32k"],
        "creative": ["doubao-pro-32k"],
        "multimodal": ["doubao-vision-pro"],
    },
    "qwen": {    # 通义千问
        "reasoning_strong": ["qwen-max", "qwen2.5-72b"],
        "coding_strong": ["qwen2.5-coder-32b", "qwen-coder"],
        "writing_strong": ["qwen-max"],
        "translation": ["qwen-max", "qwen-plus"],
        "creative": ["qwen-max", "qwen-plus"],
        "fast_cheap": ["qwen-turbo"],
        "multimodal": ["qwen-vl-max", "qwen-vl-plus"],
    },
    "ollama": {  # 本地开源
        "fast_cheap": ["llama3.2", "qwen2.5:7b"],
        "coding_strong": ["qwen2.5-coder:7b", "deepseek-coder:6.7b"],
        "translation": ["qwen2.5:7b", "llama3.2"],
        "creative": ["qwen2.5:7b", "llama3.2"],
    },
}


def _suggest_mapping(provider_id: str, available_models: list[str]) -> dict[str, str]:
    """根据 provider 的可用模型，为每个档位推荐一个模型名。

    返回 {tier: model}；没有候选的档位不返回。
    """
    hints = PROVIDER_TIER_HINTS.get(provider_id.lower(), {})
    available_lower = {m.lower(): m for m in available_models}
    suggestions: dict[str, str] = {}
    for tier, candidates in hints.items():
        for c in candidates:
            # 精确匹配
            if c in available_models:
                suggestions[tier] = c
                break
            # 大小写不敏感前缀匹配
            for am_lower, am_orig in available_lower.items():
                if am_lower.startswith(c.lower()) or c.lower().startswith(am_lower):
                    suggestions[tier] = am_orig
                    break
            if tier in suggestions:
                break
    return suggestions


# ═══════════════════════════════════════════════════════════════════════════
# Router
# ═══════════════════════════════════════════════════════════════════════════

def _pick_temp(requested_tier: str, explicit: float) -> float:
    """Choose a temperature value when resolution has partial info.

    Precedence (first that's ≥ 0 wins):
      1. ``explicit`` — temperature already captured from the ORIGINAL
         requested tier's entry (so explicit user config beats defaults).
      2. ``TIER_DEFAULT_TEMPERATURES[requested_tier]`` — recommended
         default for the task type the caller asked for.
      3. -1.0 — sentinel meaning "chat layer should omit temperature".
    """
    if explicit is not None and explicit >= 0:
        return explicit
    return TIER_DEFAULT_TEMPERATURES.get(requested_tier, -1.0)


class LLMTierRouter:
    """Singleton：档位 → provider/model 映射管理器。"""

    def __init__(self, persist_path: str = ""):
        self._map: dict[str, LLMTierEntry] = {}
        self._lock = Lock()
        self._persist_path = persist_path or os.path.join(
            os.path.expanduser("~"), ".tudou_claw", "llm_tiers.json"
        )

    # ── 基础 CRUD ──────────────────────────────────────────────────────
    def set(self, tier: str, entry: LLMTierEntry) -> None:
        with self._lock:
            self._map[tier] = entry

    def get(self, tier: str) -> LLMTierEntry | None:
        return self._map.get(tier)

    def all(self) -> dict[str, LLMTierEntry]:
        return dict(self._map)

    def remove(self, tier: str) -> bool:
        with self._lock:
            if tier in self._map:
                del self._map[tier]
                return True
            return False

    # ── 解析 ───────────────────────────────────────────────────────────
    def resolve(self, tier: str, max_hops: int = 3) -> tuple[str, str]:
        """档位 → (provider, model)。

        - 档位未配置或 disabled → 沿 fallback_tier 链查找，最多 max_hops 跳
        - 全部无效 → 返回 ('', '')，调用方走默认路径

        Back-compat wrapper: callers that also want temperature should
        use ``resolve_with_params`` instead.
        """
        prov, mdl, _ = self.resolve_with_params(tier, max_hops=max_hops)
        return (prov, mdl)

    def resolve_with_params(self, tier: str,
                            max_hops: int = 3) -> tuple[str, str, float]:
        """档位 → (provider, model, temperature)。

        Temperature is -1.0 when the tier has no explicit value AND there's
        no recommended default in ``TIER_DEFAULT_TEMPERATURES`` — signals
        "use provider default". Chat layer treats -1.0 (or any < 0) as
        "omit from payload".

        Fallback resolution walks the fallback_tier chain for (provider,
        model). Temperature, however, is taken from the ORIGINALLY
        requested tier if it has one set — falling back the model does
        not drag along the fallback's temperature preference (otherwise
        asking for 'creative' with 'writing_strong' fallback would lose
        the creative temperature). If the originally-requested tier is
        unset we do fall back to the resolved tier's temperature.
        """
        # First, capture the explicitly-configured temperature for the
        # ORIGINAL tier (before any fallback hops). We return this value
        # if it's set; otherwise the resolved tier's temperature wins.
        original_entry = self._map.get(tier) if tier else None
        original_temp = -1.0
        if original_entry is not None and original_entry.temperature >= 0:
            original_temp = original_entry.temperature

        seen: set[str] = set()
        cur = tier
        for _ in range(max_hops):
            if not cur or cur in seen:
                # Nothing usable → still return (original_tier's temp OR
                # the recommended default) so the caller can apply a
                # sensible temperature even when the router has no
                # provider binding configured.
                return ("", "", _pick_temp(tier, original_temp))
            seen.add(cur)
            entry = self._map.get(cur)
            if entry is None:
                return ("", "", _pick_temp(tier, original_temp))
            if entry.enabled and entry.provider and entry.model:
                temp = original_temp
                if temp < 0 and entry.temperature >= 0:
                    temp = entry.temperature
                if temp < 0:
                    temp = _pick_temp(tier, -1.0)
                return (entry.provider, entry.model, temp)
            if entry.fallback_tier:
                cur = entry.fallback_tier
                continue
            return ("", "", _pick_temp(tier, original_temp))
        return ("", "", _pick_temp(tier, original_temp))

    # ── 持久化 ─────────────────────────────────────────────────────────
    def load(self) -> int:
        """从磁盘加载映射。返回加载条目数。"""
        p = Path(self._persist_path)
        if not p.is_file():
            return 0
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.warning("LLMTierRouter load failed: %s", e)
            return 0
        if not isinstance(data, dict):
            return 0
        items = data.get("tiers") or {}
        with self._lock:
            self._map.clear()
            for tier, d in items.items():
                try:
                    self._map[tier] = LLMTierEntry.from_dict(d)
                except Exception:
                    continue
        logger.info("LLMTierRouter loaded %d tier mappings", len(self._map))
        return len(self._map)

    def save(self) -> None:
        p = Path(self._persist_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        data = {"tiers": {t: e.to_dict() for t, e in self._map.items()}}
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ── 智能预填（首次启动时调用） ─────────────────────────────────────
    def autofill_defaults(self, force: bool = False) -> int:
        """检测已配置的 provider，为每个档位预填默认模型映射。

        Args:
            force: True 则覆盖已有映射；False 只填充未配置的档位
        Returns: 新增/覆盖的条目数
        """
        try:
            from .llm import list_providers, list_available_models
            providers = list_providers()
            all_models = list_available_models()
        except Exception as e:
            logger.debug("LLM registry not ready for autofill: %s", e)
            return 0

        if not providers:
            return 0

        added = 0
        for tier in STANDARD_TIERS:
            if not force and tier in self._map and self._map[tier].enabled:
                continue
            # 遍历 provider 找第一个能满足此档位的
            for pid in providers:
                models = all_models.get(pid, [])
                suggestions = _suggest_mapping(pid, models)
                if tier in suggestions:
                    entry = LLMTierEntry(
                        tier=tier,
                        provider=pid,
                        model=suggestions[tier],
                        enabled=True,
                        cost_hint="medium",
                        note=f"auto-filled from {pid}",
                        # Seed temperature from the per-task recommendation
                        # table. Admins can override in the UI; -1.0 means
                        # "use provider default".
                        temperature=TIER_DEFAULT_TEMPERATURES.get(tier, -1.0),
                    )
                    with self._lock:
                        self._map[tier] = entry
                    added += 1
                    logger.info("Autofilled tier %s → %s/%s", tier, pid, suggestions[tier])
                    break
        if added > 0:
            try:
                self.save()
            except Exception as e:
                logger.warning("LLMTierRouter save failed: %s", e)
        return added


# ═══════════════════════════════════════════════════════════════════════════
# Singleton
# ═══════════════════════════════════════════════════════════════════════════

_router: LLMTierRouter | None = None


def get_router() -> LLMTierRouter:
    global _router
    if _router is None:
        _router = LLMTierRouter()
    return _router


def init_router(data_dir: str = "", autofill: bool = True) -> LLMTierRouter:
    """启动时初始化 router，加载已有映射并（可选）自动预填缺失档位。"""
    global _router
    path = os.path.join(data_dir, "llm_tiers.json") if data_dir else ""
    _router = LLMTierRouter(persist_path=path) if path else LLMTierRouter()
    _router.load()
    if autofill:
        try:
            _router.autofill_defaults(force=False)
        except Exception as e:
            logger.warning("autofill skipped: %s", e)
    return _router
