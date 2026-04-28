"""Write-path isolation guard for sub-task agents.

Wired into the existing PRE_TOOL middleware stage. When a sub-task
agent (i.e., one whose ``ProjectTask`` carries a ``parent_task_id``
pointing at a decomposition's parent) tries to write a file outside
its declared ``output_path``, this guard short-circuits the tool call
with a clear error message.

Trade-offs:
  * Hard block (per Q4=A) — better to fail loud than let one agent
    silently corrupt another's work.
  * Only fires when the agent is currently working on a sub-task
    spawned by ``confirm.py``. Regular agents are untouched.
  * Read paths are NOT restricted (sub-agents need to read shared
    PRD / interfaces / scaffold files).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger("tudouclaw.long_task.isolation")

# Tool names that write to the filesystem. Add to this set when new
# write tools land. Listed conservatively — false positives just produce
# a misleading error, false negatives let isolation breaks slip through.
_WRITE_TOOLS = {
    "write_file", "edit_file", "apply_diff",
    "create_pptx", "create_pptx_from_template",
    "create_docx", "create_xlsx",
    "save_file", "append_file",
    # bash is checked separately below — too coarse to gate at this level
}

# Path arg names commonly used by the write tools above.
_PATH_ARG_KEYS = ("path", "file_path", "output_path", "filename",
                  "target", "dest", "destination")


def _extract_target_path(tool_name: str, args: dict) -> Optional[str]:
    """Pull the destination path from common write-tool arg shapes.
    Returns None if no path-like arg found (caller will skip the check).
    """
    if not isinstance(args, dict):
        return None
    for k in _PATH_ARG_KEYS:
        v = args.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def check_write_path(*, agent, tool_name: str, args: dict) -> Optional[str]:
    """Return an error message if this tool call would write outside
    the agent's allowed wd. Returns ``None`` if the call is fine.

    Allowed write zone is the union of:
      * agent.working_dir (the sub-task's isolated dir)
      * any path under it (recursively)

    Plus, agents may always write to ``/tmp/...`` for transient work
    (we don't want to block them from using bash temp files).

    The middleware caller is responsible for converting a non-None
    return value into a SHORT_CIRCUIT MiddlewareResult.
    """
    if tool_name not in _WRITE_TOOLS:
        return None

    # Only enforce for sub-task agents — i.e. those whose currently
    # active task has a parent_task_id (set by confirm.py).
    cur_task = getattr(agent, "_current_task", None) or \
               getattr(agent, "current_task", None)
    parent_id = ""
    if cur_task is not None:
        parent_id = getattr(cur_task, "parent_task_id", "") or ""
        if not parent_id and isinstance(cur_task, dict):
            parent_id = cur_task.get("parent_task_id", "") or ""
    if not parent_id:
        return None  # not a sub-task agent — no isolation needed

    target = _extract_target_path(tool_name, args)
    if not target:
        return None  # nothing to check

    # Resolve to absolute. We compare canonical paths so symlinks and
    # ``..`` shenanigans don't bypass the check.
    try:
        target_abs = Path(target).expanduser().resolve()
    except (OSError, ValueError):
        return None  # weird path, let downstream handle

    # /tmp escape hatch — agents can always write there for transient
    # work (zip extraction, scratch files). On macOS ``/tmp`` resolves
    # to ``/private/tmp`` and ``/var/folders`` to ``/private/var/folders``,
    # so we check both forms (``Path.resolve()`` follows the symlinks).
    _tmp_prefixes = (
        "/tmp/", "/var/folders/",
        "/private/tmp/", "/private/var/folders/",
    )
    if str(target_abs).startswith(_tmp_prefixes):
        return None

    wd = getattr(agent, "working_dir", "") or ""
    if not wd:
        return None  # no wd configured, can't enforce

    try:
        wd_abs = Path(wd).expanduser().resolve()
    except (OSError, ValueError):
        return None

    try:
        # Path.is_relative_to in 3.9+
        if hasattr(target_abs, "is_relative_to"):
            inside = target_abs.is_relative_to(wd_abs)
        else:
            inside = str(target_abs).startswith(str(wd_abs) + os.sep) \
                     or str(target_abs) == str(wd_abs)
    except Exception:
        inside = False

    if inside:
        return None

    msg = (
        f"⛔ 写入隔离: 你是子任务 agent,只能写自己的工作区:\n"
        f"  工作区: {wd_abs}\n"
        f"  你想写: {target_abs}\n\n"
        f"如果你需要修改工作区外的文件:\n"
        f"  • 共享资产(PRD / interfaces / shared/)是只读的\n"
        f"  • 跨模块通信请走接口契约,不要直接改其他模块的文件\n"
        f"  • 真要跨界改,先汇报给主 agent,让主 agent 协调"
    )
    logger.warning(
        "Long-task isolation block: agent=%s task_parent=%s tool=%s target=%s wd=%s",
        getattr(agent, "id", "?")[:8], parent_id[:8],
        tool_name, target_abs, wd_abs,
    )
    return msg
