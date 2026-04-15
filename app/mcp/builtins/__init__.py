"""app.mcp.builtins — first-party MCP servers bundled with TudouClaw.

Each module here is a standalone stdio MCP server runnable via
``python -m app.mcp.builtins.<name>``. They wrap external APIs whose
credentials must stay in the main process (out of sandboxed skill code).

Current servers:
    chromadb       # vector store
    jimeng_video   # Volcano Engine 即梦 text-to-video
"""
