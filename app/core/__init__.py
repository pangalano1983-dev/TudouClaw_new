"""
Core module containing the fundamental building blocks of the claw-code system.

This package provides essential components for agent orchestration and workflow management:
- agent: Agent definitions and management
- hub: Central hub for coordinating system components
- project: Project and workspace management
- workflow: Workflow definitions and execution
- channel: Communication channels and message routing
- persona: Agent personas and behavioral profiles
"""
import platform as _platform

if _platform.system() == "Darwin":
    import os as _os
    DEFAULT_DATA_DIR = _os.path.expanduser("~/.tudou_claw")
else:
    DEFAULT_DATA_DIR = "/home/tudou_claw/.tudou_claw"
