"""
Prompt Enhancer — backward-compatibility shim.

The implementation has moved to ``app.skills.prompt_enhancer``.
"""
from app.skills.prompt_enhancer import (  # noqa: F401
    PromptPack,
    PromptPackStore,
    PromptPackRegistry,
    BM25Ranker,
    parse_skill_md,
    get_prompt_pack_registry,
    init_prompt_pack_registry,
    set_prompt_pack_registry,
)

__all__ = [
    "PromptPack",
    "PromptPackStore",
    "PromptPackRegistry",
    "BM25Ranker",
    "parse_skill_md",
    "get_prompt_pack_registry",
    "init_prompt_pack_registry",
    "set_prompt_pack_registry",
]
