"""
Portal package — re-exports for backward compatibility.

Usage:
    from app.server.portal_init import run_portal, _PortalHandler
"""
from .portal_server import run_portal, _PortalHandler, get_portal_mode, is_hub_mode

__all__ = ["run_portal", "_PortalHandler", "get_portal_mode", "is_hub_mode"]
