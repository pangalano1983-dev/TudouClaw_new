"""Legacy module path — real code moved to app/mcp/builtins/chromadb.py.

This shim keeps ``python -m app.tudou_chromadb_mcp`` working for MCP
registry entries that were written before the reorganisation. New
registrations use ``python -m app.mcp.builtins.chromadb``.
"""
from app.mcp.builtins.chromadb import *  # noqa: F401,F403
from app.mcp.builtins.chromadb import main  # noqa: F401


if __name__ == "__main__":
    main()
