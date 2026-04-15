"""
Smoke tests — verify all refactored modules can be imported without errors.

These tests don't exercise business logic; they catch import-time failures
such as missing dependencies, circular imports, and syntax regressions.
"""
import importlib

import pytest


# Modules created or heavily modified during the refactoring.
MODULES_TO_CHECK = [
    # defaults
    "app.defaults",
    # hub package
    "app.hub",
    "app.hub.types",
    "app.hub.manager_base",
    "app.hub.persistence",
    "app.hub.agent_manager",
    "app.hub.node_manager",
    "app.hub.project_manager",
    "app.hub.message_bus",
    # skills package
    "app.skills",
    "app.skills.engine",
    "app.skills.store",
    "app.skills.sourcer",
    "app.skills.prompt_enhancer",
    # backward-compat shims
    "app.skill_store",
    # server handlers
    "app.server.handlers",
    "app.server.handlers.auth",
    "app.server.handlers.config",
    "app.server.handlers.hub_sync",
    "app.server.handlers.channels",
    "app.server.handlers.scheduler",
    "app.server.handlers.providers",
    "app.server.handlers.agents",
    "app.server.handlers.projects",
]


@pytest.mark.parametrize("module_name", MODULES_TO_CHECK)
def test_import(module_name: str):
    """Each module listed should import without raising."""
    mod = importlib.import_module(module_name)
    assert mod is not None
