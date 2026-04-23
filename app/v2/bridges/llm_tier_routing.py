"""
V2 tier resolution — thin adapter over the repo's LLMTierRouter.

Historical context: V2 originally shipped its own
``ProviderEntry.tier_models`` mechanism. TudouClaw_new already ships a
richer router (``app.llm_tier_routing.LLMTierRouter``) that supports:

    * fallback_tier chains
    * per-tier cost_hint / enabled / note
    * dedicated persistence (``llm_tiers.json``)

Rather than maintain two routing tables, V2 delegates to it. Anyone
configuring tier → provider/model mappings for V2 agents does so
through the same UI / REST / JSON file the rest of the platform uses.

Public API (unchanged by design):

    resolve_tier(tier)  → (provider_id, model)
    known_tiers()       → list[str]
"""
from __future__ import annotations

import logging
import os
from typing import Tuple


logger = logging.getLogger("tudouclaw.v2.tier_routing")


KNOWN_TIERS: list[str] = [
    "default",
    "reasoning_strong",
    "coding_strong",
    "writing_strong",
    "translation",
    "creative",
    "fast_cheap",
    "multimodal",
    "vision",
    "domain_specific",
]


def resolve_tier(tier: str) -> Tuple[str, str]:
    """Return ``(provider_id, model)`` for a tier, or ``("", "")``
    to fall through to V1's configured default.

    Delegation order:
        1. Env escape hatch: ``TUDOU_LLM_TIER_<TIER>="provider:model"``
        2. The repo-wide ``LLMTierRouter`` (reads ``llm_tiers.json``).
        3. Back-compat: ``ProviderEntry.tier_models`` on a registered provider.
        4. Fall-through ``("", "")``.

    Never raises.
    """
    prov, mdl, _ = resolve_tier_with_params(tier)
    return (prov, mdl)


def resolve_tier_with_params(tier: str) -> Tuple[str, str, float]:
    """Like ``resolve_tier`` but also returns the tier's temperature.

    Temperature is -1.0 when the tier has no configured value AND no
    recommended default — signals "use provider default". V2 call sites
    that make LLM requests should prefer this over ``resolve_tier`` so
    the sampling temperature matches the task type (code-gen low, creative
    high, etc.).
    """
    key = (tier or "").strip()
    if not key:
        return ("", "", -1.0)

    # 1. Main router (LLMTierRouter from app.llm_tier_routing).
    try:
        from app import llm_tier_routing as _router_mod
        router = _router_mod.get_router()
        provider, model, temp = router.resolve_with_params(key)
        if provider and model:
            return (provider, model, temp)
        # Even if provider didn't resolve, preserve the temperature
        # signal so callers using V1 default can still pick up the
        # task-type sampling recommendation.
        if temp >= 0:
            # Return ("","") for provider/model (fall-through) but keep temp.
            pass
    except Exception as e:  # noqa: BLE001
        logger.debug("LLMTierRouter resolve failed for %r: %s", key, e)

    # 2. Legacy provider-level ``tier_models`` (pre-router configs).
    try:
        from app import llm as _llm
        picker = getattr(_llm.get_registry(), "pick_for_tier", None)
        if callable(picker):
            picked = picker(key)
            if picked is not None:
                entry, model = picked
                # Legacy picker has no temperature; fall back to the
                # recommended default for this tier.
                try:
                    from app.llm_tier_routing import default_temperature_for
                    fallback_temp = default_temperature_for(key)
                except Exception:
                    fallback_temp = -1.0
                return (entry.id, model, fallback_temp)
    except Exception:
        pass

    # 3. Env escape hatch (headless CI / tests). Lowest priority so a
    #    real UI-configured binding always wins over a stray env var.
    env_val = os.environ.get(
        "TUDOU_LLM_TIER_" + key.upper(), ""
    ).strip()
    if env_val and ":" in env_val:
        p, _, m = env_val.partition(":")
        try:
            from app.llm_tier_routing import default_temperature_for
            fallback_temp = default_temperature_for(key)
        except Exception:
            fallback_temp = -1.0
        return (p.strip(), m.strip(), fallback_temp)

    return ("", "", -1.0)


def known_tiers() -> list[str]:
    """Return tier names we know about, plus any custom ones declared
    via the main router or provider-level tier_models dicts."""
    out = set(KNOWN_TIERS)
    try:
        from app import llm_tier_routing as _router_mod
        router = _router_mod.get_router()
        mapping = getattr(router, "_map", None) or {}
        for t in mapping.keys():
            if t:
                out.add(t)
    except Exception:
        pass
    try:
        from app import llm as _llm
        for p in _llm.get_registry().list(include_disabled=False):
            for t in (getattr(p, "tier_models", {}) or {}).keys():
                if t:
                    out.add(t)
    except Exception:
        pass
    return sorted(out)


__all__ = ["resolve_tier", "resolve_tier_with_params", "known_tiers", "KNOWN_TIERS"]
