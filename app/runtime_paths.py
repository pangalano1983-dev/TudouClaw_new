"""Process-level paths and subprocess env — single source of truth.

Why this module exists
──────────────────────
Every place that launches a child Python process (MCP server, agent worker,
tool sandbox …) needs two things:

  1. A cwd / PYTHONPATH that allows ``python -m app.xxx`` to resolve the
     top-level ``app`` package regardless of where the parent was launched.
  2. A way to inject caller-supplied env variables (API keys, endpoints,
     feature flags) without hardcoding them inside individual modules.

Historically each launcher recomputed the project root locally with
``os.path.dirname(os.path.dirname(__file__))``. That's brittle: the
correct number of ``dirname()`` hops depends on how deep the caller
module sits under ``app/``, and moving a file silently breaks subprocess
startup with ``ModuleNotFoundError: No module named 'app'``. One source
of truth here fixes the whole class of bugs.

Public API
──────────

    get_project_root()                     -> str
    build_subprocess_env(extra=None, base=None) -> dict[str, str]
    subprocess_launch_kwargs(extra=None)   -> dict  # splat into Popen

Usage:

    from app.runtime_paths import subprocess_launch_kwargs
    kw = subprocess_launch_kwargs(extra_env=mcp_config.env)
    proc = subprocess.Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE,
                            text=True, bufsize=1, **kw)
"""
from __future__ import annotations

import os
from typing import Mapping

# ─────────────────────── project root resolution ───────────────────────
#
# We resolve PROJECT_ROOT from the ``app`` package's own ``__file__``,
# NOT from this helper's ``__file__``. That way the depth of
# ``runtime_paths.py`` inside the tree is irrelevant — as long as the
# file sits somewhere under ``app/``, PROJECT_ROOT always points at the
# parent of the ``app`` package.
#
# This is the fix for the class of bugs where a deeper caller used too
# few ``dirname()`` hops and ended up pointing PYTHONPATH at
# ``<root>/app`` instead of ``<root>``.

import app as _app_pkg  # noqa: E402  (intentional late import)

_APP_PKG_DIR = os.path.dirname(os.path.abspath(_app_pkg.__file__))
PROJECT_ROOT: str = os.path.abspath(os.path.join(_APP_PKG_DIR, os.pardir))


def get_project_root() -> str:
    """Return the absolute path of the TudouClaw project root.

    This is the directory that CONTAINS the ``app`` package, i.e. the
    directory you need on ``sys.path`` / ``PYTHONPATH`` for
    ``import app`` and ``python -m app.xxx`` to succeed.
    """
    return PROJECT_ROOT


# ───────────────────────── env var injection ─────────────────────────
#
# Variables we always make available to child processes. These are
# non-secret, runtime-structural variables — think "where is the
# project root" — not credentials. Credentials travel through the
# per-MCP ``config.env`` dict that callers pass in as ``extra_env``.

_INTRINSIC_ENV: dict[str, str] = {
    # Lets child code resolve project-relative paths without recomputing
    # dirname hops. Any skill / MCP server that needs to read files
    # under the repo should use this instead of ``__file__`` math.
    "TUDOU_PROJECT_ROOT": PROJECT_ROOT,
}


def build_subprocess_env(
    extra_env: Mapping[str, str] | None = None,
    base_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build an env dict for launching a ``python -m app.xxx`` subprocess.

    Layering (lowest → highest precedence):
        1. ``base_env`` (default: current ``os.environ``)
        2. Intrinsic variables (``TUDOU_PROJECT_ROOT``, PYTHONPATH)
        3. ``extra_env`` — caller-supplied overrides (per-MCP env,
           per-agent credentials, etc.)

    PYTHONPATH is always prepended with PROJECT_ROOT (de-duplicated),
    so an incoming PYTHONPATH from the user's shell is preserved.
    """
    env: dict[str, str] = dict(base_env if base_env is not None else os.environ)

    # Intrinsic vars go in before user overrides so users CAN override
    # them if they have a real reason to. (They almost never should.)
    env.update(_INTRINSIC_ENV)

    # PYTHONPATH: prepend PROJECT_ROOT, dedupe, preserve the rest.
    existing = env.get("PYTHONPATH", "")
    parts: list[str] = [PROJECT_ROOT]
    if existing:
        for p in existing.split(os.pathsep):
            if p and p != PROJECT_ROOT and p not in parts:
                parts.append(p)
    env["PYTHONPATH"] = os.pathsep.join(parts)

    if extra_env:
        # Caller-supplied env wins. This is how per-MCP credentials
        # (VOLC_ACCESSKEY, MCP_EMAIL_SERVER_*, etc.) get injected
        # without being hardcoded anywhere.
        for k, v in extra_env.items():
            if v is None:
                env.pop(k, None)
            else:
                env[k] = str(v)

    return env


def subprocess_launch_kwargs(
    extra_env: Mapping[str, str] | None = None,
    cwd: str | None = None,
) -> dict:
    """Return Popen kwargs (``env=``, ``cwd=``) for an MCP / worker subprocess.

    By default ``cwd`` is pinned to the project root so relative imports
    in shim modules like ``app/tudou_jimeng_video_mcp.py`` resolve
    correctly. Pass an explicit ``cwd`` to override (e.g. an agent work
    directory) — PYTHONPATH will still point back at PROJECT_ROOT so
    ``import app`` keeps working.
    """
    return {
        "env": build_subprocess_env(extra_env),
        "cwd": cwd if cwd is not None else PROJECT_ROOT,
    }


__all__ = [
    "PROJECT_ROOT",
    "get_project_root",
    "build_subprocess_env",
    "subprocess_launch_kwargs",
]
