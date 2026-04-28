"""V2 LLMRouter — pick (provider, model) for a call from agent's slots.

Resolution order:

  1. Caller passed ``explicit_function`` (e.g. "coding") → use that slot.
  2. Heuristic ``classify(signals)`` infers a function from the call's
     shape (multimodal? coding body? long context? reasoning chain?).
  3. Phase hint (Plan → reasoning, Verify → analysis).
  4. Fallback: ``default`` slot.

Empty slot at any step keeps falling back. If even ``default`` is empty,
returns ``("", "")`` and the caller decides (typically: V2 ``llm_tier``
resolver, then V1 config.yaml default — see ``llm_tier_routing``).

This module ONLY decides which (provider, model) to use. Provider-level
quirks (sanitize, fold, parallel tool calls flag, YAML overlay) live in
``app.llm_providers`` and apply automatically once chat_no_stream is
called with the resolved ids.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from ..agent.llm_slots import (
    AgentLLMSlots,
    SLOT_NAMES,
    SlotBinding,
)

logger = logging.getLogger("tudouclaw.v2.llm_router")


# Keyword sets for heuristic classification. Kept conservative — false
# positives just mean the wrong slot, not a hard error (router falls
# back to default anyway when the picked slot is empty).
_REASONING_KEYWORDS = re.compile(
    r"为什么|怎么会|推导|证明|解释一下|step.?by.?step|chain.?of.?thought|"
    r"derive|prove|explain why",
    re.IGNORECASE,
)
_ANALYSIS_KEYWORDS = re.compile(
    r"总结|概括|对比|比较|归纳|分析(?!师|部)|review|summari[sz]e|compare|"
    r"contrast",
    re.IGNORECASE,
)


# Phase → preferred function slot mapping (only when no explicit / classify
# match). Not strict — if the slot is empty it falls back to default.
_PHASE_TO_SLOT: dict[str, str] = {
    "plan":     "reasoning",
    "verify":   "analysis",
    "deliver":  "analysis",
    # intake / execute / done don't have a strong preference — go to
    # default unless caller passes explicit_function.
}


class RouterDecision:
    """Inspectable outcome of one ``LLMRouter.pick`` call.

    Attributes:
        slot:     the slot name finally chosen ("default"/"coding"/...)
        binding:  the resolved (provider, model)
        reason:   short human-readable trace, e.g.
                  ``"explicit_function=coding"`` or
                  ``"classify=reasoning,fallback=default"``
    """
    __slots__ = ("slot", "binding", "reason")

    def __init__(self, slot: str, binding: SlotBinding, reason: str):
        self.slot = slot
        self.binding = binding
        self.reason = reason

    def __repr__(self) -> str:
        return (f"RouterDecision(slot={self.slot!r}, "
                f"binding={self.binding.to_str()!r}, "
                f"reason={self.reason!r})")


class LLMRouter:
    """Stateless router. One instance per process is fine."""

    def pick(
        self,
        slots: AgentLLMSlots,
        *,
        explicit_function: str = "",
        phase: str = "",
        signals: Optional[dict[str, Any]] = None,
    ) -> RouterDecision:
        """Pick the slot binding for one LLM call.

        Args:
            slots: the agent's resolved AgentLLMSlots.
            explicit_function: caller hint, takes priority. Empty if none.
            phase: current 6-phase name (lowercase: intake/plan/...).
            signals: optional dict of call-shape signals:
                - has_image_or_audio: bool — multimodal content present
                - is_writing_code_body: bool — write_file/edit_file with
                                                 large content arg
                - prompt_chars: int — total prompt size
                - last_user_text: str — last user message content for
                                          keyword classification

        Returns:
            RouterDecision with slot, binding, and reason trace.
        """
        signals = signals or {}

        # 1. Explicit function trumps everything
        if explicit_function and explicit_function in SLOT_NAMES:
            b = slots.get(explicit_function)
            if b.is_set():
                return RouterDecision(
                    explicit_function, b,
                    f"explicit={explicit_function}",
                )
            return RouterDecision(
                "default", slots.default,
                f"explicit={explicit_function}(empty),fallback=default",
            )

        # 2. Signal-based classify (highest-priority signal wins)
        slot = self._classify(signals)
        if slot:
            b = slots.get(slot)
            if b.is_set():
                return RouterDecision(
                    slot, b, f"classify={slot}",
                )
            # classified slot empty → continue to phase/default fallback
            classify_trace = f"classify={slot}(empty)"
        else:
            classify_trace = ""

        # 3. Phase hint
        if phase:
            slot = _PHASE_TO_SLOT.get(phase.lower(), "")
            if slot:
                b = slots.get(slot)
                if b.is_set():
                    reason = (f"{classify_trace},phase={phase}→{slot}"
                              if classify_trace else f"phase={phase}→{slot}")
                    return RouterDecision(slot, b, reason)

        # 4. Default fallback
        reason_parts = []
        if classify_trace:
            reason_parts.append(classify_trace)
        if phase:
            reason_parts.append(f"phase={phase}")
        reason_parts.append("→default")
        return RouterDecision(
            "default", slots.default, ",".join(reason_parts) or "default",
        )

    def _classify(self, signals: dict[str, Any]) -> str:
        """Return a slot name based on signals, or '' if no match."""
        # Multimodal beats everything (the model MUST handle the input)
        if signals.get("has_image_or_audio"):
            return "multimodal"

        # Coding body generation
        if signals.get("is_writing_code_body"):
            return "coding"

        # Long context → analysis
        try:
            chars = int(signals.get("prompt_chars", 0) or 0)
        except (TypeError, ValueError):
            chars = 0
        if chars > 12000:   # ~3K tokens; "long" but not absurd
            return "analysis"

        # Keyword sniff on last user text
        text = signals.get("last_user_text", "") or ""
        if isinstance(text, str) and text:
            if _REASONING_KEYWORDS.search(text):
                return "reasoning"
            if _ANALYSIS_KEYWORDS.search(text):
                return "analysis"

        return ""


# Module-level singleton
_router = LLMRouter()


def get_router() -> LLMRouter:
    """Return the process-wide router instance."""
    return _router
