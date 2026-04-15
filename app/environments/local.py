"""
Local execution environment using the existing sandbox module.
"""
import os
import subprocess
from pathlib import Path
from typing import Optional

from . import base
from .. import sandbox as _sandbox


class LocalEnvironment(base.BaseEnvironment):
    """Execute commands locally using the sandbox's existing infrastructure."""

    def __init__(
        self,
        cwd: str = "",
        timeout: int = 30,
        env: Optional[dict] = None,
        sandbox_mode: str = "restricted",
    ):
        """
        Initialize a local environment with sandbox protection.

        Args:
            cwd: Working directory
            timeout: Default command timeout in seconds
            env: Optional environment variables (for interface compatibility)
            sandbox_mode: Sandbox mode ("off", "command_only", "restricted", "strict")
        """
        super().__init__(cwd or os.getcwd(), timeout, env)
        self.sandbox_mode = sandbox_mode
        # Create and store a sandbox policy for this environment
        self.policy = _sandbox.SandboxPolicy(
            root=self.cwd,
            mode=sandbox_mode,
        )

    def execute(
        self,
        command: str,
        cwd: str = "",
        *,
        timeout: Optional[int] = None,
        stdin_data: Optional[str] = None,
    ) -> dict:
        """Execute a command locally with sandbox protection."""
        # Check command safety
        ok, err = self.policy.check_command(command)
        if not ok:
            return {"output": f"Error: {err}", "returncode": 1, "error": err}

        # Use provided timeout or fall back to instance default
        effective_timeout = timeout if timeout is not None else self.timeout
        try:
            effective_timeout = max(1, min(int(effective_timeout), 600))
        except (TypeError, ValueError):
            effective_timeout = self.timeout

        # Use provided cwd or fall back to policy root
        effective_cwd = cwd or str(self.policy.root)

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                cwd=effective_cwd,
                env=self.policy.scrub_env(),
                input=stdin_data,
            )

            # Combine stdout and stderr
            output_parts = []
            if result.stdout:
                output_parts.append(result.stdout)
            if result.stderr:
                output_parts.append(f"[stderr]\n{result.stderr}")
            output_parts.append(f"[exit code: {result.returncode}]")

            return {
                "output": "\n".join(output_parts),
                "returncode": result.returncode,
            }

        except subprocess.TimeoutExpired:
            return {
                "output": f"Error: Command timed out after {effective_timeout}s",
                "returncode": 124,
                "error": f"Timeout after {effective_timeout}s",
            }
        except Exception as e:
            return {
                "output": f"Error: {e}",
                "returncode": 1,
                "error": str(e),
            }

    def cleanup(self) -> None:
        """Local environment has no resources to clean up."""
        pass

    def is_available(self) -> bool:
        """Local execution is always available."""
        return True
