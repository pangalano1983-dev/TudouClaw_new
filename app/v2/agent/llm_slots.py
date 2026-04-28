"""V2 LLM slot routing — five-function model selection.

A V2 Agent declares which model handles each task family ("slot"):

    default     — fallback + tool dispatch
    analysis    — long-context, summarization, comparison
    reasoning   — multi-step reasoning, derivation, planning
    coding      — generating code bodies (write_file content, edit_file)
    multimodal  — image / audio / video inputs

Operators populate slots in agent config (UI or JSON). At call time
``LLMRouter.pick(agent, signals)`` returns the (provider_id, model_name)
tuple for the most relevant slot, falling back through:

    explicit_function (caller hint)
    → signal-based classify
    → default

This module provides the data shape and migration helpers ONLY.
The router lives in ``app.v2.bridges.llm_router``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("tudouclaw.v2.llm_slots")


# Closed set of slot names. Adding a slot = explicit code change here.
SLOT_NAMES: tuple[str, ...] = (
    "default",
    "analysis",
    "reasoning",
    "coding",
    "multimodal",
)

# Subset of slots that are "function-keyed" (everything except default).
FUNCTION_SLOTS: tuple[str, ...] = tuple(s for s in SLOT_NAMES if s != "default")


@dataclass(frozen=True)
class SlotBinding:
    """One slot's resolved (provider, model) binding."""
    provider: str = ""    # ProviderEntry.id
    model: str = ""       # exact model name as the provider reports it

    def is_set(self) -> bool:
        return bool(self.provider and self.model)

    def to_str(self) -> str:
        if not self.is_set():
            return ""
        return f"{self.provider}/{self.model}"

    @staticmethod
    def from_str(s: str) -> "SlotBinding":
        """Parse 'provider/model' or '' → SlotBinding."""
        if not s or "/" not in s:
            return SlotBinding()
        prov, _, mdl = s.partition("/")
        return SlotBinding(provider=prov.strip(), model=mdl.strip())


@dataclass
class AgentLLMSlots:
    """Five-slot LLM binding for one agent.

    Stored on Capabilities as a dict[str, str] field (provider/model
    strings) for JSON serialization simplicity. Use ``from_dict`` /
    ``to_dict`` to bridge.
    """
    default: SlotBinding = field(default_factory=SlotBinding)
    analysis: SlotBinding = field(default_factory=SlotBinding)
    reasoning: SlotBinding = field(default_factory=SlotBinding)
    coding: SlotBinding = field(default_factory=SlotBinding)
    multimodal: SlotBinding = field(default_factory=SlotBinding)

    def get(self, slot: str) -> SlotBinding:
        """Return the binding for ``slot`` or an empty binding if name unknown."""
        if slot not in SLOT_NAMES:
            return SlotBinding()
        return getattr(self, slot)

    def resolve(self, slot: str) -> SlotBinding:
        """Return the binding for ``slot`` falling back to default if empty.

        ``slot=""`` or unknown → default. Function slot empty → default.
        Default empty → empty binding (caller decides if that's an error).
        """
        if slot and slot in SLOT_NAMES:
            b = getattr(self, slot)
            if b.is_set():
                return b
        return self.default

    def to_dict(self) -> dict[str, str]:
        """Serialize to {slot_name: 'provider/model'} dict for JSON storage."""
        out: dict[str, str] = {}
        for s in SLOT_NAMES:
            b = getattr(self, s)
            if b.is_set():
                out[s] = b.to_str()
        return out

    @classmethod
    def from_dict(cls, d: Optional[dict[str, Any]]) -> "AgentLLMSlots":
        """Build from {slot_name: 'provider/model'} dict (lenient)."""
        slots = cls()
        if not isinstance(d, dict):
            return slots
        for s in SLOT_NAMES:
            v = d.get(s)
            if isinstance(v, str) and v:
                setattr(slots, s, SlotBinding.from_str(v))
            elif isinstance(v, dict):
                # accept {"provider": "...", "model": "..."} too
                setattr(slots, s, SlotBinding(
                    provider=str(v.get("provider", "") or "").strip(),
                    model=str(v.get("model", "") or "").strip(),
                ))
        return slots


# ─────────────────────────────────────────────────────────────────────
# V1 → V2 migration helpers
# ─────────────────────────────────────────────────────────────────────
#
# V1 scattered LLM selection across 5 mechanisms:
#   1. agent.provider / agent.model           → default
#   2. agent.coding_provider / coding_model   → coding (was named "tool" in
#                                                early V2 design; coding is
#                                                its true semantic since
#                                                tool dispatch goes to
#                                                default)
#   3. agent.extra_llms[label].purpose        → mapped per purpose
#   4. agent.profile.llm_tier_overrides       → tier name → slot mapping
#   5. agent.auto_route                       → (deleted, replaced by router)
#
# This function reads what's available on a V1 agent dict and produces
# AgentLLMSlots. Missing fields stay empty bindings (router falls back
# to default at call time).

# `extra_llms[*].purpose` value → slot name. V1 had open-ended purposes;
# we map the historical ones to the closed slot set. Unknown purposes
# are dropped (with a debug log) rather than blowing up.
_PURPOSE_TO_SLOT: dict[str, str] = {
    "code_review":   "coding",
    "code":          "coding",
    "coding":        "coding",
    "tool-heavy":    "default",   # tool dispatch lives on default
    "tool":          "default",
    "reasoning":     "reasoning",
    "analysis":      "analysis",
    "summarize":     "analysis",
    "summarization": "analysis",
    "multimodal":    "multimodal",
    "vision":        "multimodal",
    "image":         "multimodal",
    "default":       "default",
}


def slots_from_v1_agent(v1_agent: Any) -> AgentLLMSlots:
    """Best-effort extraction of slot bindings from a V1 ``Agent`` instance.

    Looks at, in order: ``provider/model`` (default slot),
    ``coding_provider/coding_model`` (coding slot), ``extra_llms``
    list (mapped via purpose), and ``profile.llm_tier_overrides``
    (tier name treated as slot name when it matches).

    Never raises — returns empty slots if the agent doesn't expose
    expected fields.
    """
    slots = AgentLLMSlots()
    if v1_agent is None:
        return slots

    # 1. default ← provider/model
    try:
        prov = str(getattr(v1_agent, "provider", "") or "").strip()
        mdl = str(getattr(v1_agent, "model", "") or "").strip()
        if prov and mdl:
            slots.default = SlotBinding(provider=prov, model=mdl)
    except Exception:
        pass

    # 2. coding ← coding_provider/coding_model
    try:
        prov = str(getattr(v1_agent, "coding_provider", "") or "").strip()
        mdl = str(getattr(v1_agent, "coding_model", "") or "").strip()
        if prov and mdl:
            slots.coding = SlotBinding(provider=prov, model=mdl)
    except Exception:
        pass

    # 2b. multimodal ← multimodal_provider/multimodal_model
    try:
        prov = str(getattr(v1_agent, "multimodal_provider", "") or "").strip()
        mdl = str(getattr(v1_agent, "multimodal_model", "") or "").strip()
        if prov and mdl:
            slots.multimodal = SlotBinding(provider=prov, model=mdl)
    except Exception:
        pass

    # 3. extra_llms[*] mapped by purpose
    try:
        for entry in getattr(v1_agent, "extra_llms", []) or []:
            if not isinstance(entry, dict):
                continue
            purpose = str(entry.get("purpose", "") or "").strip().lower()
            slot = _PURPOSE_TO_SLOT.get(purpose)
            if not slot:
                continue
            prov = str(entry.get("provider", "") or "").strip()
            mdl = str(entry.get("model", "") or "").strip()
            if not (prov and mdl):
                continue
            # Only fill if not already set (don't overwrite the explicit
            # field-based binding from step 1/2).
            existing = getattr(slots, slot)
            if not existing.is_set():
                setattr(slots, slot, SlotBinding(provider=prov, model=mdl))
    except Exception:
        pass

    # 4. profile.llm_tier_overrides — tier name treated as slot when it
    #    matches an exact slot name (e.g. "coding": "deepseek/v4-coder").
    try:
        prof = getattr(v1_agent, "profile", None)
        overrides = getattr(prof, "llm_tier_overrides", {}) or {}
        for tier_name, ref in overrides.items():
            slot = str(tier_name).strip().lower()
            if slot not in SLOT_NAMES:
                continue
            existing = getattr(slots, slot)
            if existing.is_set():
                continue
            if isinstance(ref, str) and "/" in ref:
                setattr(slots, slot, SlotBinding.from_str(ref))
    except Exception:
        pass

    return slots
