"""
Security utilities for TudouClaw.

1. MCP credential safety: filter env vars, strip secrets from error messages
2. Context injection scanning: detect invisible unicode and injection patterns
3. Model-specific prompt engineering helpers
"""

import re
import logging

logger = logging.getLogger("tudou.security")

# ── MCP Credential Safety ──

# Environment variables safe to pass to MCP subprocess
SAFE_ENV_KEYS = frozenset({
    "PATH", "HOME", "USER", "LANG", "LC_ALL", "LC_CTYPE",
    "TERM", "SHELL", "TMPDIR", "TMP", "TEMP",
    "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME",
    "XDG_RUNTIME_DIR", "XDG_STATE_HOME",
    "PYTHONPATH", "NODE_PATH", "GOPATH",
})

# Patterns that indicate secrets in strings
_SECRET_PATTERNS = [
    re.compile(r'sk-[a-zA-Z0-9]{20,}'),           # OpenAI-style
    re.compile(r'sk-ant-api[a-zA-Z0-9-]{20,}'),    # Anthropic
    re.compile(r'ghp_[a-zA-Z0-9]{36}'),             # GitHub PAT
    re.compile(r'gho_[a-zA-Z0-9]{36}'),             # GitHub OAuth
    re.compile(r'glpat-[a-zA-Z0-9-]{20,}'),         # GitLab
    re.compile(r'Bearer\s+[a-zA-Z0-9._-]{20,}'),    # Bearer tokens
    re.compile(r'[a-f0-9]{64}'),                     # 64-char hex (API keys)
    re.compile(r'-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY'),  # Private keys
    re.compile(r'password["\s:=]+\S{6,}', re.IGNORECASE),
]

def filter_env_for_mcp(env: dict) -> dict:
    """Filter environment variables, keeping only safe ones + explicitly configured ones."""
    safe = {}
    for k, v in env.items():
        if k in SAFE_ENV_KEYS or k.startswith("MCP_"):
            safe[k] = v
    return safe

def strip_secrets(text: str) -> str:
    """Remove API keys, tokens, and passwords from text before showing to LLM."""
    result = text
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub("[REDACTED]", result)
    return result


# ── Context Injection Scanning ──

# Invisible unicode characters that can hide instructions
_INVISIBLE_CHARS = set([
    '\u200b',  # zero-width space
    '\u200c',  # zero-width non-joiner
    '\u200d',  # zero-width joiner
    '\u2060',  # word joiner
    '\u2061',  # function application
    '\u2062',  # invisible times
    '\u2063',  # invisible separator
    '\u2064',  # invisible plus
    '\ufeff',  # BOM / zero-width no-break space
    '\u00ad',  # soft hyphen
    '\u200e',  # LTR mark
    '\u200f',  # RTL mark
    '\u202a',  # LTR embedding
    '\u202b',  # RTL embedding
    '\u202c',  # pop directional
    '\u202d',  # LTR override
    '\u202e',  # RTL override
    '\u2066',  # LTR isolate
    '\u2067',  # RTL isolate
    '\u2068',  # first strong isolate
    '\u2069',  # pop directional isolate
])

_INJECTION_PATTERNS = [
    re.compile(r'ignore\s+(all\s+)?previous\s+instructions', re.IGNORECASE),
    re.compile(r'system\s+prompt\s+override', re.IGNORECASE),
    re.compile(r'you\s+are\s+now\s+', re.IGNORECASE),
    re.compile(r'forget\s+(all\s+)?(your\s+)?instructions', re.IGNORECASE),
    re.compile(r'new\s+instructions?\s*:', re.IGNORECASE),
    re.compile(r'disregard\s+(all\s+)?previous', re.IGNORECASE),
    re.compile(r'override\s+safety', re.IGNORECASE),
    re.compile(r'jailbreak', re.IGNORECASE),
]

def scan_content(text: str, source: str = "") -> tuple[bool, str]:
    """Scan text for injection attacks and invisible characters.

    Returns (is_safe, reason). If is_safe is False, reason describes the threat.
    """
    if not text:
        return True, ""

    # Check for invisible unicode
    found_invisible = [c for c in text if c in _INVISIBLE_CHARS]
    if len(found_invisible) > 3:
        chars = set(f"U+{ord(c):04X}" for c in found_invisible[:5])
        return False, f"Invisible unicode characters detected: {chars} (source: {source})"

    # Check for injection patterns
    for pattern in _INJECTION_PATTERNS:
        match = pattern.search(text)
        if match:
            return False, f"Injection pattern detected: '{match.group()[:50]}' (source: {source})"

    return True, ""

def sanitize_content(text: str) -> str:
    """Remove invisible unicode characters from text."""
    return ''.join(c for c in text if c not in _INVISIBLE_CHARS)


# ── Model-Specific Tool Use Enforcement ──

def get_model_tool_guidance(model: str) -> str:
    """Return model-specific guidance for tool use enforcement.

    Some models tend to describe actions rather than actually calling tools.
    This injects specific steering prompts to fix that.
    """
    model_lower = (model or "").lower()

    if any(k in model_lower for k in ("gpt-4", "gpt-3.5", "gpt-4o")):
        return (
            "\n\nIMPORTANT: When you need to perform an action (read files, "
            "search, execute commands), you MUST use the provided tools by "
            "making function calls. Do NOT describe what you would do — "
            "actually call the tool."
        )

    if any(k in model_lower for k in ("gemini", "gemma")):
        return (
            "\n\nCRITICAL: You have access to tools. When a task requires "
            "reading files, searching, or executing commands, you MUST invoke "
            "the appropriate tool function. Never respond with a description "
            "of what tool you'd use — invoke it directly."
        )

    if any(k in model_lower for k in ("qwen", "deepseek", "minimax")):
        return (
            "\n\n注意: 当你需要读取文件、搜索、执行命令时，必须直接调用对应的工具函数。"
            "不要只描述你会做什么——请直接调用工具执行操作。"
        )

    return ""  # Claude and well-behaved models don't need steering
