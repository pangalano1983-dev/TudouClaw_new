"""
Pluggable execution environments for TudouClaw.

Inspired by Hermes Agent's modular architecture, supports multiple
execution backends (local, Docker, etc.) with a unified interface.
"""
from .base import BaseEnvironment
from .local import LocalEnvironment
from .docker import DockerEnvironment
from .manager import EnvironmentManager, env_manager

__all__ = [
    "BaseEnvironment", "LocalEnvironment", "DockerEnvironment",
    "EnvironmentManager", "env_manager",
]
