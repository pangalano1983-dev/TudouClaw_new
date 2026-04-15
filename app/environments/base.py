"""
Abstract base class for execution environments.
"""
from abc import ABC, abstractmethod
from typing import Optional


class BaseEnvironment(ABC):
    """Abstract base for execution environment backends."""

    def __init__(self, cwd: str, timeout: int = 30, env: Optional[dict] = None):
        """
        Initialize an execution environment.

        Args:
            cwd: Working directory for command execution
            timeout: Default timeout in seconds for commands
            env: Optional environment variables dict
        """
        self.cwd = cwd
        self.timeout = timeout
        self.env = env or {}

    @abstractmethod
    def execute(
        self,
        command: str,
        cwd: str = "",
        *,
        timeout: Optional[int] = None,
        stdin_data: Optional[str] = None,
    ) -> dict:
        """
        Execute a command in this environment.

        Args:
            command: Shell command to execute
            cwd: Optional override for working directory
            timeout: Optional override for timeout (seconds)
            stdin_data: Optional stdin input

        Returns:
            dict with keys:
                - "output": combined stdout and stderr as string
                - "returncode": integer exit code
                - "error": optional error message if execution failed
        """

    @abstractmethod
    def cleanup(self) -> None:
        """Release resources held by this environment."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this environment backend is available on the system."""
