"""
SkillScout — backward-compatibility shim.

The implementation has moved to ``app.skills._skill_scout``.
The unified facade is ``app.skills.sourcer.SkillSourcer``.
"""
from app.skills._skill_scout import (  # noqa: F401
    SkillScout,
    SkillSource,
    DiscoveredSkill,
    SkillEvaluation,
    SkillRecommendation,
    GITHUB_API_RATE_LIMIT,
    CACHE_TTL_SECONDS,
    MIN_QUALITY_SCORE_FOR_RECOMMENDATION,
)
from app.skills.sourcer import SkillSourcer  # noqa: F401

__all__ = [
    "SkillScout",
    "SkillSource",
    "DiscoveredSkill",
    "SkillEvaluation",
    "SkillRecommendation",
    "SkillSourcer",
    "GITHUB_API_RATE_LIMIT",
    "CACHE_TTL_SECONDS",
    "MIN_QUALITY_SCORE_FOR_RECOMMENDATION",
]
