"""Single source of truth for the runtime data directory.

Use this module instead of hardcoding ``~/.tudou_claw`` or reading the
env var inline. Only one place encodes the resolution rules so that
multi-node / NAS deployments (see ``docs/data-dir-config.md``) can
swap the root with one env var.

Resolution order (first non-empty wins)::

    1. TUDOU_CLAW_DATA_DIR  — canonical name
    2. TUDOU_CLAW_HOME      — legacy alias (auth.py / experience_library.py
                              historically read this; keep working until
                              callers migrate over)
    3. ~/.tudou_claw         — default

The path is resolved fresh on each call (NOT cached as a module-level
constant). Tests can ``monkeypatch.setenv("TUDOU_CLAW_DATA_DIR", ...)``
and the next ``data_dir()`` call sees the new value. If you bind the
result to a module-level constant in your own module, your tests need
to either (a) reload your module after monkeypatching, or (b) call
``data_dir()`` at use time instead of import time.
"""

from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    """Return the runtime data root as a Path.

    Does NOT create the directory. Most callers chain a subpath
    (e.g. ``data_dir() / "agents.json"``) and write through the usual
    file ops which create parents on demand. If you need the dir to
    exist up front, do ``data_dir().mkdir(parents=True, exist_ok=True)``
    yourself — paths.py stays read-only on disk.
    """
    raw = (
        os.environ.get("TUDOU_CLAW_DATA_DIR", "").strip()
        or os.environ.get("TUDOU_CLAW_HOME", "").strip()
    )
    if raw:
        return Path(raw).expanduser().resolve()
    return Path.home() / ".tudou_claw"


__all__ = ["data_dir"]
