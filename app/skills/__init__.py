"""app.skills — unified skill system package.

Layout:
    engine.py           # SkillRegistry / SkillRunner / validator / manifest schema
    store.py            # SkillStore — Hub-level catalog + install + grant facade
    builtin/            # shipped skills (jimeng_video, send_email, ...)

Public API re-exported for convenience:
    from app.skills import SkillRegistry, SkillStore, SkillRunner
"""
from .engine import *  # noqa: F401,F403
from .engine import (  # noqa: F401  explicit for IDEs/static checkers
    MCPDependency,
    LLMDependency,
    SkillInput,
    SkillManifest,
    SkillStatus,
    SkillInstall,
    ManifestError,
    parse_manifest,
    parse_manifest_file,
    CodeValidationError,
    validate_python_skill,
    SkillContext,
    MCPProxy,
    LLMProxy,
    HttpProxy,
    SkillRunner,
    SkillRegistry,
    init_registry,
    get_registry,
)
from .store import (  # noqa: F401
    SkillCatalogEntry,
    SkillAnnotation,
    SkillStore,
    init_store,
    get_store,
)
from .sourcer import (  # noqa: F401
    SkillSourcer,
    SkillDraft,
    Experience,
    DiscoveredSkill,
    SkillEvaluation,
    SkillRecommendation,
    SkillSource,
)
from .prompt_enhancer import (  # noqa: F401
    PromptPack,
    PromptPackStore,
    PromptPackRegistry,
    BM25Ranker,
    parse_skill_md,
    get_prompt_pack_registry,
    init_prompt_pack_registry,
    set_prompt_pack_registry,
)
