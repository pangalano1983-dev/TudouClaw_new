"""
Environment manager for pluggable execution backends.

Provides a registry and factory pattern for selecting and
managing execution environments (local, docker, etc.).
"""
from typing import Dict, List, Optional, Type

from . import base
from . import docker
from . import local


class EnvironmentManager:
    """
    Registry and factory for execution environments.

    Maintains available backends and provides methods to select
    and instantiate them based on availability and configuration.
    """

    def __init__(self):
        """Initialize the environment manager with built-in backends."""
        self._environments: Dict[str, Type[base.BaseEnvironment]] = {}
        self._instances: Dict[str, base.BaseEnvironment] = {}
        self._default = "local"

        # Register built-in environments
        self.register("local", local.LocalEnvironment)
        self.register("docker", docker.DockerEnvironment)

    def register(self, name: str, env_class: Type[base.BaseEnvironment]) -> None:
        """
        Register a new environment backend.

        Args:
            name: Identifier for this environment (e.g., "local", "docker")
            env_class: Environment class (must inherit from BaseEnvironment)
        """
        if not issubclass(env_class, base.BaseEnvironment):
            raise TypeError(
                f"{env_class} must inherit from BaseEnvironment"
            )
        self._environments[name] = env_class

    def get(
        self,
        name: Optional[str] = None,
        cwd: str = "",
        timeout: int = 30,
        **kwargs,
    ) -> base.BaseEnvironment:
        """
        Get or create an environment instance.

        Args:
            name: Environment name (defaults to default environment)
            cwd: Working directory for the environment
            timeout: Default timeout for commands
            **kwargs: Additional arguments passed to the environment constructor

        Returns:
            An instance of the requested environment

        Raises:
            ValueError: If environment not found or not available
        """
        env_name = name or self._default

        if env_name not in self._environments:
            available = self.list_available()
            raise ValueError(
                f"Environment '{env_name}' not registered. "
                f"Available: {available or 'none'}"
            )

        env_class = self._environments[env_name]

        # Create a new instance (could be cached, but fresh per request
        # ensures isolation and clean state)
        try:
            instance = env_class(cwd=cwd, timeout=timeout, **kwargs)
            if not instance.is_available():
                raise ValueError(
                    f"Environment '{env_name}' is not available on this system"
                )
            return instance
        except Exception as e:
            raise ValueError(
                f"Failed to initialize environment '{env_name}': {e}"
            ) from e

    def set_default(self, name: str) -> None:
        """
        Set the default environment for get() calls.

        Args:
            name: Environment name to use as default

        Raises:
            ValueError: If environment not registered
        """
        if name not in self._environments:
            raise ValueError(
                f"Environment '{name}' not registered. "
                f"Available: {list(self._environments.keys())}"
            )
        self._default = name

    def list_available(self) -> List[str]:
        """
        List all registered environments that are available on this system.

        Returns:
            List of environment names that have their backends available
        """
        available = []
        for name, env_class in self._environments.items():
            try:
                # Test availability with a temporary instance
                instance = env_class(cwd=".")
                if instance.is_available():
                    available.append(name)
                instance.cleanup()
            except Exception:
                # If instantiation fails, it's not available
                pass
        return available

    def list_all(self) -> List[str]:
        """
        List all registered environments.

        Returns:
            List of all registered environment names
        """
        return list(self._environments.keys())

    def get_default(self) -> str:
        """Get the name of the current default environment."""
        return self._default


# Singleton instance for global use
env_manager = EnvironmentManager()
