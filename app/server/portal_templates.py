"""
Portal frontend templates — Login page and main SPA dashboard.

HTML has been extracted to standalone files under ``app/templates/``
for easier editing.  This module lazy-loads them and exposes the same
two public names that the rest of the codebase already imports:

    from app.server.portal_templates import _LOGIN_HTML, _PORTAL_HTML
"""
from __future__ import annotations

import os
from functools import lru_cache

_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")


@lru_cache(maxsize=1)
def _read(name: str) -> str:
    path = os.path.join(_TEMPLATE_DIR, name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# Public API — kept as module-level properties via __getattr__
# so existing ``from …portal_templates import _LOGIN_HTML`` still works.

def __getattr__(name: str) -> str:
    if name == "_LOGIN_HTML":
        return _read("login.html")
    if name == "_PORTAL_HTML":
        return _read("portal.html")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
