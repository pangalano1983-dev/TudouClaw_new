"""
SkillForge — backward-compatibility shim.

The implementation has moved to ``app.skills._skill_forge``.
The unified facade is ``app.skills.sourcer.SkillSourcer``.
"""
from app.skills._skill_forge import (  # noqa: F401
    SkillForge,
    SkillDraft,
    Experience,
    MIN_EXPERIENCES_FOR_SKILL,
    MIN_SUCCESS_RATE,
    SCENE_SIMILARITY_THRESHOLD,
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_PROVIDER,
)
from app.skills.sourcer import SkillSourcer  # noqa: F401

__all__ = [
    "SkillForge",
    "SkillDraft",
    "Experience",
    "SkillSourcer",
    "MIN_EXPERIENCES_FOR_SKILL",
    "MIN_SUCCESS_RATE",
    "SCENE_SIMILARITY_THRESHOLD",
    "DEFAULT_LLM_MODEL",
    "DEFAULT_LLM_PROVIDER",
]
