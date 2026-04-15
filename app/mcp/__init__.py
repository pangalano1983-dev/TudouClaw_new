"""app.mcp — MCP (Model Context Protocol) management & builtin MCP servers.

Subpackage layout:
    app/mcp/
        manager.py       # MCPManager, MCP_CATALOG, MCPServerConfig, ...
        builtins/        # first-party MCP servers (stdio, python -m)
            chromadb.py
            jimeng_video.py

For backward compatibility, the legacy import path ``app.mcp_manager``
still works via a shim at ``app/mcp_manager.py`` that re-exports
everything from ``app.mcp.manager``. New code should prefer::

    from app.mcp.manager import get_mcp_manager, MCP_CATALOG, ...
"""

from app.mcp.manager import *  # noqa: F401,F403
