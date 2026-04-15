"""REMOVED shim — do not import.

Use ``from app.mcp.manager import ...`` directly. This file is kept
only because the workspace filesystem does not permit deleting it;
importing it raises so any forgotten caller fails loudly.
"""
raise ImportError(
    "app.infra.mcp_manager has been removed; import from app.mcp.manager instead."
)
