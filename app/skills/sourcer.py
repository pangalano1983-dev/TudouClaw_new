"""
SkillSourcer — Unified skill acquisition facade.

Merges the capabilities of SkillForge (experience-based skill generation)
and SkillScout (online skill discovery) into a single entry-point.

Usage:
    from app.skills.sourcer import SkillSourcer

    sourcer = SkillSourcer(
        experience_data_dir="data/experience",
        output_dir="pending_skills",
        llm_call_fn=llm.chat_no_stream,
    )

    # Generate skills from experience patterns
    drafts = sourcer.scan_experience(role="coder")

    # Discover skills from online sources
    results = sourcer.search_online("web scraping", agent_role="coder")

    # Approve an experience-derived draft
    sourcer.approve_draft(draft_id)
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from ._skill_forge import (
    SkillForge,
    SkillDraft,
    Experience,
    MIN_EXPERIENCES_FOR_SKILL,
    MIN_SUCCESS_RATE,
)
from ._skill_scout import (
    SkillScout,
    SkillSource,
    DiscoveredSkill,
    SkillEvaluation,
    SkillRecommendation,
)

logger = logging.getLogger("tudou.skill_sourcer")

__all__ = [
    "SkillSourcer",
    # Re-export data models for convenience
    "SkillDraft",
    "Experience",
    "SkillSource",
    "DiscoveredSkill",
    "SkillEvaluation",
    "SkillRecommendation",
]


class SkillSourcer:
    """Unified skill acquisition: from experience library or online sources.

    Composes SkillForge (experience -> skill drafts) and SkillScout
    (online search -> evaluated recommendations) behind a single API.
    """

    def __init__(
        self,
        # SkillForge params
        experience_data_dir: str = "",
        output_dir: str = "pending_skills",
        # SkillScout params
        sources: Optional[list[SkillSource]] = None,
        cache_dir: str = "",
        # Shared
        llm_call_fn: Optional[Callable] = None,
        model: str = "",
        provider: str = "claude",
        language: str = "en",
    ):
        """Initialise the unified sourcer.

        Args:
            experience_data_dir: Experience library data directory (for SkillForge).
                                 If empty, forge features are disabled.
            output_dir:          Output dir for pending skill packages.
            sources:             Online SkillSource list (for SkillScout).
            cache_dir:           Cache directory for online metadata.
            llm_call_fn:         LLM callable shared by both sub-engines.
            model:               LLM model name (SkillForge).
            provider:            LLM provider name (SkillForge).
            language:            Output language for SkillScout reports.
        """
        self._forge: Optional[SkillForge] = None
        self._scout: Optional[SkillScout] = None

        # Initialise SkillForge only when experience dir is provided
        if experience_data_dir:
            self._forge = SkillForge(
                experience_data_dir=experience_data_dir,
                output_dir=output_dir,
                llm_call_fn=llm_call_fn,
                model=model,
                provider=provider,
            )

        # SkillScout is always available (works without local data)
        self._scout = SkillScout(
            sources=sources,
            cache_dir=cache_dir,
            llm_call_fn=llm_call_fn,
            language=language,
        )

        logger.info(
            "SkillSourcer initialised (forge=%s, scout=%s)",
            "enabled" if self._forge else "disabled",
            "enabled",
        )

    # ------------------------------------------------------------------
    # Forge-delegated methods (experience -> skill drafts)
    # ------------------------------------------------------------------

    def scan_experience(self, role: str = "") -> list[SkillDraft]:
        """Scan the experience library and propose skill candidates.

        Args:
            role: Limit scan to a specific role (empty = all roles).

        Returns:
            List of newly generated SkillDraft objects.
        """
        if self._forge is None:
            logger.warning("scan_experience called but SkillForge is not initialised")
            return []
        return self._forge.scan_for_candidates(role=role)

    def draft_skill(self, experiences: list[Experience]) -> SkillDraft:
        """Create a skill draft from a set of related experiences.

        Raises:
            RuntimeError: If SkillForge is not initialised.
            ValueError:   If fewer than MIN_EXPERIENCES_FOR_SKILL are provided.
        """
        if self._forge is None:
            raise RuntimeError("SkillForge is not initialised (no experience_data_dir)")
        return self._forge.draft_skill(experiences)

    def approve_draft(self, draft_id: str) -> dict:
        """Approve a pending skill draft."""
        if self._forge is None:
            return {"error": "SkillForge is not initialised"}
        return self._forge.approve_draft(draft_id)

    def reject_draft(self, draft_id: str) -> dict:
        """Reject a pending skill draft."""
        if self._forge is None:
            return {"error": "SkillForge is not initialised"}
        return self._forge.reject_draft(draft_id)

    def list_drafts(self) -> list[SkillDraft]:
        """List all pending/approved/rejected skill drafts."""
        if self._forge is None:
            return []
        return self._forge.list_drafts()

    def export_package(self, draft: SkillDraft) -> str:
        """Export an approved skill draft as a directory package.

        Returns:
            Path to the exported skill directory.

        Raises:
            RuntimeError: If SkillForge is not initialised.
        """
        if self._forge is None:
            raise RuntimeError("SkillForge is not initialised (no experience_data_dir)")
        return self._forge.export_package(draft)

    # ------------------------------------------------------------------
    # Scout-delegated methods (online discovery)
    # ------------------------------------------------------------------

    def search_online(
        self,
        query: str,
        agent_role: str = "",
        max_results: int = 20,
    ) -> list[DiscoveredSkill]:
        """Search online sources for skills matching *query*.

        Args:
            query:       Search keywords (e.g. "web_scraper", "email").
            agent_role:  Optional agent role for relevance context.
            max_results: Maximum results to return.

        Returns:
            List of DiscoveredSkill sorted by relevance.
        """
        if self._scout is None:
            return []
        return self._scout.search(query, agent_role=agent_role, max_results=max_results)

    def evaluate_online(
        self,
        skill: DiscoveredSkill,
        agent_role: str = "",
        available_mcps: Optional[list[str]] = None,
    ) -> SkillEvaluation:
        """Evaluate a discovered skill on quality, security, and compatibility."""
        if self._scout is None:
            raise RuntimeError("SkillScout is not initialised")
        return self._scout.evaluate(skill, agent_role=agent_role, available_mcps=available_mcps)

    def generate_report(
        self,
        query: str,
        agent_role: str = "",
        max_results: int = 10,
        available_mcps: Optional[list[str]] = None,
    ) -> SkillRecommendation:
        """Full pipeline: search -> evaluate -> rank -> generate markdown report."""
        if self._scout is None:
            raise RuntimeError("SkillScout is not initialised")
        return self._scout.generate_report(
            query, agent_role=agent_role,
            max_results=max_results, available_mcps=available_mcps,
        )

    def prepare_install(self, skill: DiscoveredSkill, output_dir: str) -> dict:
        """Generate install instructions for a discovered skill (no auto-install)."""
        if self._scout is None:
            raise RuntimeError("SkillScout is not initialised")
        return self._scout.prepare_install(skill, output_dir)

    # ------------------------------------------------------------------
    # Convenience properties
    # ------------------------------------------------------------------

    @property
    def forge(self) -> Optional[SkillForge]:
        """Direct access to the underlying SkillForge (may be None)."""
        return self._forge

    @property
    def scout(self) -> Optional[SkillScout]:
        """Direct access to the underlying SkillScout."""
        return self._scout
