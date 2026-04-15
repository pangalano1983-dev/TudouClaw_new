"""
Structured Logging — centralised logging configuration for Tudou Claw.

Features:
    - JSON structured logging for production (machine-parseable)
    - Human-readable colored console logging for development
    - Context propagation (agent_id, node_id, request_id)
    - Log rotation with configurable file output
    - Single-point configuration replacing per-module handler setup

Usage:
    # At application startup (portal / web / repl entry-point):
    from app.infra.logging import setup_logging, get_logger

    setup_logging(level="INFO", fmt="json", log_file="/var/log/tudou.log")

    # In any module:
    from app.infra.logging import get_logger
    logger = get_logger("tudou.agent")
    logger.info("Agent started", extra={"agent_id": "a1", "model": "qwen3"})

Environment variables:
    TUDOU_LOG_LEVEL   — DEBUG / INFO / WARNING / ERROR (default: INFO)
    TUDOU_LOG_FORMAT  — json / text (default: text)
    TUDOU_LOG_FILE    — optional file path, enables rotation
    TUDOU_LOG_MAX_MB  — max megabytes per log file (default: 50)
    TUDOU_LOG_BACKUPS — number of rotated files to keep (default: 5)
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
import threading
import time
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Context variables — propagated across async/thread boundaries
# ---------------------------------------------------------------------------
ctx_agent_id: ContextVar[str] = ContextVar("ctx_agent_id", default="")
ctx_node_id: ContextVar[str] = ContextVar("ctx_node_id", default="")
ctx_request_id: ContextVar[str] = ContextVar("ctx_request_id", default="")
ctx_user_id: ContextVar[str] = ContextVar("ctx_user_id", default="")

_setup_done = False
_setup_lock = threading.Lock()

# ---------------------------------------------------------------------------
# JSON Formatter
# ---------------------------------------------------------------------------

class JSONFormatter(logging.Formatter):
    """Outputs each log record as a single JSON line (JSONL / ndjson).

    Standard fields: ts, level, logger, msg, pid, thread.
    Extra context from ContextVars or record.extra is merged in.
    Exception info is serialised as ``exc`` string.
    """

    def format(self, record: logging.LogRecord) -> str:
        doc: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc)
                         .isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "pid": record.process,
            "thread": record.threadName,
        }

        # Inject context-var values (non-empty only)
        for key, cvar in _CONTEXT_VARS.items():
            val = cvar.get("")
            if val:
                doc[key] = val

        # Merge user-supplied extra fields (skip stdlib internals)
        _STDLIB = {
            "name", "msg", "args", "levelname", "levelno", "pathname",
            "filename", "module", "exc_info", "exc_text", "stack_info",
            "lineno", "funcName", "created", "msecs", "relativeCreated",
            "thread", "threadName", "process", "processName", "message",
            "taskName",
        }
        for k, v in record.__dict__.items():
            if k not in _STDLIB and not k.startswith("_"):
                doc[k] = v

        if record.exc_info and record.exc_info[1]:
            doc["exc"] = self.formatException(record.exc_info)

        return json.dumps(doc, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# Human-readable Formatter (dev mode, with optional colour)
# ---------------------------------------------------------------------------

_LEVEL_COLOURS = {
    "DEBUG":    "\033[36m",    # cyan
    "INFO":     "\033[32m",    # green
    "WARNING":  "\033[33m",    # yellow
    "ERROR":    "\033[31m",    # red
    "CRITICAL": "\033[1;31m",  # bold red
}
_RESET = "\033[0m"


class TextFormatter(logging.Formatter):
    """Human-friendly formatter compatible with the existing Tudou format.

    Format: ``[HH:MM:SS] LEVEL logger | message  {context}``
    Colour is applied only when the stream is a TTY.
    """

    def __init__(self, use_colour: bool = True):
        super().__init__()
        self.use_colour = use_colour

    def format(self, record: logging.LogRecord) -> str:
        ts = time.strftime("%H:%M:%S", time.localtime(record.created))
        level = record.levelname.ljust(5)

        # Collect context tags
        ctx_parts: list[str] = []
        for key, cvar in _CONTEXT_VARS.items():
            val = cvar.get("")
            if val:
                ctx_parts.append(f"{key}={val}")

        # Check for user-supplied extra
        _STDLIB = {
            "name", "msg", "args", "levelname", "levelno", "pathname",
            "filename", "module", "exc_info", "exc_text", "stack_info",
            "lineno", "funcName", "created", "msecs", "relativeCreated",
            "thread", "threadName", "process", "processName", "message",
            "taskName",
        }
        for k, v in record.__dict__.items():
            if k not in _STDLIB and not k.startswith("_"):
                ctx_parts.append(f"{k}={v}")

        ctx_str = ""
        if ctx_parts:
            ctx_str = "  {" + ", ".join(ctx_parts) + "}"

        msg = record.getMessage()

        if self.use_colour and sys.stderr.isatty():
            clr = _LEVEL_COLOURS.get(record.levelname, "")
            line = f"[{ts}] {clr}{level}{_RESET} {record.name} | {msg}{ctx_str}"
        else:
            line = f"[{ts}] {level} {record.name} | {msg}{ctx_str}"

        if record.exc_info and record.exc_info[1]:
            line += "\n" + self.formatException(record.exc_info)

        return line


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

# Map of context-var name → ContextVar instance, used by formatters
_CONTEXT_VARS: dict[str, ContextVar[str]] = {
    "agent_id":   ctx_agent_id,
    "node_id":    ctx_node_id,
    "request_id": ctx_request_id,
    "user_id":    ctx_user_id,
}


def set_context(*, agent_id: str = "", node_id: str = "",
                request_id: str = "", user_id: str = "") -> None:
    """Set context-vars for the current execution context (thread / coroutine)."""
    if agent_id:
        ctx_agent_id.set(agent_id)
    if node_id:
        ctx_node_id.set(node_id)
    if request_id:
        ctx_request_id.set(request_id)
    if user_id:
        ctx_user_id.set(user_id)


def clear_context() -> None:
    """Reset all context-vars to empty."""
    ctx_agent_id.set("")
    ctx_node_id.set("")
    ctx_request_id.set("")
    ctx_user_id.set("")


def get_logger(name: str) -> logging.Logger:
    """Return a logger by name.

    Unlike raw ``logging.getLogger``, this guarantees that
    ``setup_logging()`` has been called at least once (with defaults).
    """
    if not _setup_done:
        setup_logging()
    return logging.getLogger(name)


# ---------------------------------------------------------------------------
# Core setup
# ---------------------------------------------------------------------------

def setup_logging(
    *,
    level: str | None = None,
    fmt: str | None = None,
    log_file: str | None = None,
    max_mb: int | None = None,
    backups: int | None = None,
) -> None:
    """Configure the root logger for the entire application.

    Safe to call multiple times — only the first call takes effect.

    Parameters
    ----------
    level : str
        DEBUG / INFO / WARNING / ERROR.  Env ``TUDOU_LOG_LEVEL`` overrides.
    fmt : str
        ``"json"`` or ``"text"``.  Env ``TUDOU_LOG_FORMAT`` overrides.
    log_file : str | None
        If set, adds a RotatingFileHandler (always JSON).
        Env ``TUDOU_LOG_FILE`` overrides.
    max_mb : int
        Max megabytes per log file before rotation.
        Env ``TUDOU_LOG_MAX_MB`` overrides.
    backups : int
        Number of rotated backups to keep.
        Env ``TUDOU_LOG_BACKUPS`` overrides.
    """
    global _setup_done
    with _setup_lock:
        if _setup_done:
            return
        _setup_done = True

    # Resolve from env → parameter → default
    level_str = os.environ.get("TUDOU_LOG_LEVEL", level or "INFO").upper()
    fmt_str = os.environ.get("TUDOU_LOG_FORMAT", fmt or "text").lower()
    log_file = os.environ.get("TUDOU_LOG_FILE", log_file or "")
    max_bytes = int(os.environ.get("TUDOU_LOG_MAX_MB", max_mb or 50)) * 1024 * 1024
    backup_count = int(os.environ.get("TUDOU_LOG_BACKUPS", backups or 5))

    root = logging.getLogger()
    root.setLevel(getattr(logging, level_str, logging.INFO))

    # Remove any pre-existing handlers (from per-module setup)
    root.handlers.clear()

    # Also clean up any per-module handlers that were added before setup
    for name in list(logging.Logger.manager.loggerDict):
        lg = logging.getLogger(name)
        if lg.handlers:
            lg.handlers.clear()
            lg.propagate = True

    # Console handler
    console = logging.StreamHandler(sys.stderr)
    if fmt_str == "json":
        console.setFormatter(JSONFormatter())
    else:
        console.setFormatter(TextFormatter(use_colour=True))
    root.addHandler(console)

    # File handler (always JSON for machine parsing)
    if log_file:
        try:
            os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)
            fh = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            fh.setFormatter(JSONFormatter())
            root.addHandler(fh)
        except OSError as exc:
            root.warning("Failed to open log file %s: %s", log_file, exc)

    # Quieten noisy third-party loggers
    for noisy in ("urllib3", "requests", "websockets", "asyncio", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Convenience: drop-in replacement for the per-module boilerplate
# ---------------------------------------------------------------------------

def _compat_get_logger(name: str) -> logging.Logger:
    """Backward-compatible logger factory.

    Modules can replace their 6-line boilerplate::

        logger = logging.getLogger("tudou.agent")
        if not logger.handlers:
            _h = logging.StreamHandler()
            ...

    with a single line::

        from app.infra.logging import get_logger
        logger = get_logger("tudou.agent")
    """
    return get_logger(name)
