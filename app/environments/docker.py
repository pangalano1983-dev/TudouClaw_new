"""
Docker-based execution environment with security isolation.
"""
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Optional

from . import base


class DockerEnvironment(base.BaseEnvironment):
    """
    Execute commands in isolated Docker containers with restrictive security settings.

    Features:
    - Capability dropping (only essential caps enabled)
    - Memory and CPU limits
    - tmpfs for /tmp to prevent disk abuse
    - No privilege escalation
    - PID limit to prevent fork bombs
    """

    # Conservative security settings for isolated code execution
    SECURITY_ARGS = [
        "--cap-drop",
        "ALL",
        "--cap-add",
        "DAC_OVERRIDE",
        "--cap-add",
        "CHOWN",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        "256",
        "--tmpfs",
        "/tmp:rw,nosuid,size=512m",
    ]

    def __init__(
        self,
        cwd: str = "",
        timeout: int = 30,
        env: Optional[dict] = None,
        image: str = "python:3.11-slim",
        memory_limit: str = "512m",
        cpu_limit: str = "1.0",
    ):
        """
        Initialize a Docker execution environment.

        Args:
            cwd: Working directory to bind mount in container
            timeout: Default command timeout in seconds
            env: Optional environment variables to forward to container
            image: Docker image to use for execution
            memory_limit: Memory limit for container (e.g., "512m", "2g")
            cpu_limit: CPU limit for container (e.g., "0.5", "2.0")
        """
        super().__init__(cwd or os.getcwd(), timeout, env)
        self.image = image
        self.memory_limit = memory_limit
        self.cpu_limit = cpu_limit
        self.session_id = str(uuid.uuid4())[:8]
        self._docker_path = self._find_docker()

    def _find_docker(self) -> Optional[str]:
        """Find docker binary in common locations."""
        # Try standard locations
        candidates = [
            shutil.which("docker"),
            "/usr/local/bin/docker",
            "/opt/homebrew/bin/docker",
            "/usr/bin/docker",
        ]
        for candidate in candidates:
            if candidate and Path(candidate).exists() and os.access(candidate, os.X_OK):
                return candidate
        return None

    def is_available(self) -> bool:
        """Check if Docker is available and daemon is running."""
        if not self._docker_path:
            return False

        try:
            result = subprocess.run(
                [self._docker_path, "ps"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

    def execute(
        self,
        command: str,
        cwd: str = "",
        *,
        timeout: Optional[int] = None,
        stdin_data: Optional[str] = None,
    ) -> dict:
        """
        Execute a command in a Docker container.

        Args:
            command: Shell command to execute
            cwd: Optional override for working directory (relative to /workspace)
            timeout: Optional override for timeout (seconds)
            stdin_data: Optional stdin input

        Returns:
            dict with "output" and "returncode" keys
        """
        if not self._docker_path:
            return {
                "output": "Error: Docker is not available",
                "returncode": 1,
                "error": "Docker not found",
            }

        if not self.is_available():
            return {
                "output": "Error: Docker daemon is not running",
                "returncode": 1,
                "error": "Docker daemon unavailable",
            }

        # Use provided timeout or fall back to instance default
        effective_timeout = timeout if timeout is not None else self.timeout
        try:
            effective_timeout = max(1, min(int(effective_timeout), 600))
        except (TypeError, ValueError):
            effective_timeout = self.timeout

        # Effective working directory in the container
        effective_cwd = cwd or "/workspace"
        if not effective_cwd.startswith("/"):
            effective_cwd = f"/workspace/{effective_cwd}"

        # Build docker run command
        container_name = f"tudou-{self.session_id}-{uuid.uuid4().hex[:8]}"

        docker_cmd = [
            self._docker_path,
            "run",
            "--rm",
            "--name",
            container_name,
            # Volume mounts
            "-v",
            f"{self.cwd}:/workspace",
            "-w",
            effective_cwd,
            # Resource limits
            "-m",
            self.memory_limit,
            "--cpus",
            self.cpu_limit,
            # Security settings
            *self.SECURITY_ARGS,
            # Environment variables (only safe ones)
            "-e",
            f"PATH={os.environ.get('PATH', '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin')}",
            "-e",
            f"HOME=/workspace",
            "-e",
            f"USER=root",
        ]

        # Add any forwarded environment variables
        if self.env:
            # Only forward explicitly set env vars, avoid credentials
            safe_prefixes = ("LANG", "LC_", "PYTHONPATH", "NODE_")
            for key, value in self.env.items():
                if any(key.startswith(p) for p in safe_prefixes):
                    docker_cmd.extend(["-e", f"{key}={value}"])

        # Add the image and shell command
        docker_cmd.extend(
            [
                self.image,
                "sh",
                "-c",
                command,
            ]
        )

        try:
            result = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
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
            # Try to kill the container on timeout
            try:
                subprocess.run(
                    [self._docker_path, "kill", container_name],
                    capture_output=True,
                    timeout=5,
                )
            except Exception:
                pass

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
        """Kill any running containers for this session."""
        if not self._docker_path:
            return

        try:
            # Kill all containers with this session ID
            result = subprocess.run(
                [self._docker_path, "ps", "-a", "-q", "-f", f"name=tudou-{self.session_id}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                container_ids = result.stdout.strip().split("\n")
                for cid in container_ids:
                    if cid:
                        try:
                            subprocess.run(
                                [self._docker_path, "kill", cid],
                                capture_output=True,
                                timeout=5,
                            )
                        except Exception:
                            pass
        except Exception:
            pass
