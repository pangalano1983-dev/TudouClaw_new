"""
Portal — Compatibility shim.

The portal has been split into smaller modules under app/server/:
  - portal_templates.py   — Login + SPA frontend HTML/CSS/JS (~9500 lines)
  - portal_auth.py        — Authentication / authorization helpers
  - portal_routes_get.py  — GET route handlers
  - portal_routes_post.py — POST + DELETE route handlers
  - portal_server.py      — HTTP handler class + run_portal() server startup
  - portal_init.py        — Re-export for backward compat

This file exists solely for backward compatibility:
    from app.portal import run_portal
    from app.portal import _PortalHandler
"""

from .server.portal_server import (      # noqa: F401
    run_portal,
    _PortalHandler,
    get_portal_mode,
    is_hub_mode,
    _portal_mode,
)
