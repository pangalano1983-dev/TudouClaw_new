# Execution Environments

A pluggable execution environment system for TudouClaw, inspired by Hermes Agent's modular architecture. Supports multiple execution backends (local, Docker, etc.) with a unified interface.

## Architecture

```
BaseEnvironment (abstract)
├── LocalEnvironment (uses existing sandbox)
└── DockerEnvironment (Docker container isolation)
```

### BaseEnvironment (base.py)

Abstract base class defining the interface for all execution backends:

```python
class BaseEnvironment(ABC):
    def __init__(self, cwd: str, timeout: int = 30, env: dict = None)
    
    @abstractmethod
    def execute(command: str, cwd: str = "", *, timeout: int = None, 
                stdin_data: str = None) -> dict
        """Execute command, return {"output": str, "returncode": int}"""
    
    @abstractmethod
    def cleanup(self)
        """Release resources (e.g., kill containers)"""
    
    @abstractmethod
    def is_available(self) -> bool
        """Check if backend is available on this system"""
```

## Implementations

### LocalEnvironment (local.py)

Wraps the existing sandbox module with full command filtering and filesystem jailing:

**Features:**
- Uses existing `SandboxPolicy` for security
- Command blacklist enforcement (prevents `rm`, `mkfs`, etc.)
- Filesystem jail with symlink traversal protection
- Environment variable scrubbing (removes credentials)
- Process timeout protection

**Usage:**
```python
from app.environments import env_manager

# Create local environment with restricted sandbox
env = env_manager.get("local", cwd="/workspace", timeout=30, 
                      sandbox_mode="restricted")

# Execute command
result = env.execute("ls -la")
print(result["output"])      # stdout + stderr
print(result["returncode"])  # exit code

env.cleanup()
```

### DockerEnvironment (docker.py)

Executes commands in isolated Docker containers with restrictive security:

**Features:**
- Automatic Docker availability detection
- Container lifecycle management (auto-cleanup)
- Security settings:
  - Capability dropping (only DAC_OVERRIDE, CHOWN enabled)
  - Memory limit (default: 512MB)
  - CPU limit (default: 1.0 core)
  - PID limit (256 to prevent fork bombs)
  - tmpfs /tmp with nosuid flag (512MB)
  - No privilege escalation (`--security-opt no-new-privileges`)
- Volume mount for working directory
- Safe environment variable forwarding

**Usage:**
```python
from app.environments import env_manager

# Create Docker environment
env = env_manager.get("docker", cwd="/workspace", timeout=30,
                      image="python:3.11-slim",
                      memory_limit="512m",
                      cpu_limit="1.0")

# Execute command in container
result = env.execute("python -c 'print(42)'")
if result["returncode"] == 0:
    print(result["output"])  # "42"
else:
    print(result.get("error"))

env.cleanup()
```

## EnvironmentManager (manager.py)

Global registry for managing available backends:

```python
from app.environments import env_manager

# List all registered environments
all_envs = env_manager.list_all()        # ["local", "docker"]

# List only available ones
available = env_manager.list_available() # ["local"]

# Set default environment
env_manager.set_default("docker")

# Create instance
env = env_manager.get("docker", cwd="/tmp", timeout=60)

# Or use default
env = env_manager.get(cwd="/tmp", timeout=60)
```

## Integration with tools.py

The environments system can replace `_tool_bash()` with pluggable backends:

**Before (monolithic):**
```python
def _tool_bash(command: str, timeout: int = 30, **_) -> str:
    pol = _sandbox.get_current_policy()
    # ... manual sandbox checks and subprocess.run
    result = subprocess.run(command, shell=True, cwd=str(pol.root), ...)
```

**After (pluggable):**
```python
from app.environments import env_manager

def _tool_bash(command: str, timeout: int = 30, 
               environment: str = None, **_) -> str:
    env = env_manager.get(environment, cwd=os.getcwd(), timeout=timeout)
    result = env.execute(command, timeout=timeout)
    return result["output"]
```

## Security Model

### LocalEnvironment
- **Blacklist approach**: Command patterns are blocked at execution time
- **Filesystem jailing**: All paths must resolve inside sandbox root
- **Process isolation**: Via sandbox environment scrubbing
- **Best for**: Development, testing, trusted code

### DockerEnvironment
- **Container isolation**: Complete OS-level isolation
- **Resource limits**: Memory, CPU, PID limits
- **Capability dropping**: Minimal required capabilities only
- **Volume binding**: Read-only or specific directories
- **Best for**: Untrusted code, production, maximum isolation

## Configuration

### Environment Variables

Control sandbox behavior:
```bash
# Set sandbox mode (default: "restricted")
export TUDOU_SANDBOX=restricted  # off, command_only, restricted, strict

# Docker image selection
TUDOU_DOCKER_IMAGE=python:3.11-slim
TUDOU_DOCKER_MEMORY=512m
TUDOU_DOCKER_CPU=1.0
```

### Per-Request Options

```python
# LocalEnvironment options
env = env_manager.get("local", 
                      cwd="/workspace",
                      timeout=60,
                      sandbox_mode="strict")

# DockerEnvironment options
env = env_manager.get("docker",
                      cwd="/workspace",
                      timeout=60,
                      image="python:3.11-slim",
                      memory_limit="2g",
                      cpu_limit="2.0")
```

## Error Handling

All `execute()` calls return consistent format:

```python
result = env.execute("failing_command")

# Always has these keys:
result["output"]      # stdout + stderr as string
result["returncode"]  # exit code

# May have these keys on error:
result["error"]       # error description
```

**Common return codes:**
- `0`: Success
- `1`: General error
- `124`: Timeout
- Other: Command's native exit code

## Testing

Run the test suite:

```bash
cd /path/to/TudouClaw
python3 -c '
import sys
sys.path.insert(0, ".")
from app.environments import env_manager

# Test local environment
env = env_manager.get("local", cwd="/tmp")
result = env.execute("echo test")
assert result["returncode"] == 0
assert "test" in result["output"]

# Test blocked command
result = env.execute("rm -rf /tmp")
assert result["returncode"] == 1

print("All tests passed!")
'
```

## Extending with Custom Environments

Create a new environment backend:

```python
from app.environments import base

class CustomEnvironment(base.BaseEnvironment):
    def __init__(self, cwd, timeout=30, env=None, **opts):
        super().__init__(cwd, timeout, env)
        self.custom_opt = opts.get("custom_opt")
    
    def execute(self, command, cwd="", *, timeout=None, stdin_data=None):
        # Implement execution
        return {"output": "...", "returncode": 0}
    
    def cleanup(self):
        # Release resources
        pass
    
    def is_available(self):
        # Check if backend is available
        return True
```

Register it:

```python
from app.environments import env_manager
env_manager.register("custom", CustomEnvironment)

# Use it
env = env_manager.get("custom", cwd="/tmp")
```

## Performance Considerations

### LocalEnvironment
- **Startup**: ~1-5ms (subprocess spawn)
- **Overhead**: Minimal
- **Use case**: Many short-lived commands

### DockerEnvironment
- **Startup**: ~500ms-2s (container creation)
- **Overhead**: Higher resource usage
- **Use case**: Long-running or untrusted code

Choose based on:
- **Security requirements**: Docker for untrusted code
- **Performance needs**: Local for many quick commands
- **Resource availability**: Local for low-resource environments
