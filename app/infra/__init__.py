"""
Infrastructure module providing low-level system and integration services.

This package contains infrastructure components for system operations and external integrations:
- llm: Language model integration and management
- tools: Utilities and helper functions for the system
- sandbox: Isolated execution environments for safe code running
- scheduler: Task scheduling and asynchronous job management
- mcp_manager: Management of Model Context Protocol integrations
- src_bridge: Bridge for accessing external source code and repositories
"""
import platform as _platform

if _platform.system() == "Darwin":
    import os as _os
    DEFAULT_DATA_DIR = _os.path.expanduser("~/.tudou_claw")
else:
    DEFAULT_DATA_DIR = "/home/tudou_claw/.tudou_claw"
