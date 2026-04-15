"""
Backward-compatibility shim — canonical location is ``app.skills.store``.

All public names are re-exported so existing code like
``from app.skill_store import SkillStore`` and
``from app import skill_store`` continues to work.
"""
from .skills.store import *  # noqa: F401,F403
from .skills.store import (  # noqa: F401  — explicit for IDEs
    SOURCE_TIERS,
    DEFAULT_SOURCE,
    SkillCatalogEntry,
    SkillAnnotation,
    SkillStore,
    init_store,
    get_store,
    import_agent_skill,
    import_anthropic_skills_bulk,
    scan_remote_url,
    import_from_scan_result,
    cleanup_scan_temp,
    _parse_frontmatter,
)
