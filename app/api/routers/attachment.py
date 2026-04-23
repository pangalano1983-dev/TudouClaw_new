"""Attachment router — serve workspace files for inline rendering."""
from __future__ import annotations

import logging
import mimetypes
import os
from pathlib import Path as _P

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse

from ..deps.hub import get_hub
from ..deps.auth import CurrentUser, get_current_user

logger = logging.getLogger("tudouclaw.api.attachment")

router = APIRouter(tags=["attachment"])

# Max entries to scan when doing basename fallback walk
_MAX_WALK_ENTRIES = 10_000


@router.get("/api/portal/attachment")
async def get_attachment(
    path: str = Query(..., description="File path (absolute or relative-to-workspace)"),
    agent_id: str = Query("", description="Agent ID for workspace resolution"),
    hub=Depends(get_hub),
    user: CurrentUser = Depends(get_current_user),
):
    """Serve a file from an agent's workspace for inline rendering.

    Used by chat bubbles to render ``![](local-path)`` markdown images.
    """
    req_path = (path or "").strip()
    if not req_path:
        raise HTTPException(400, "path required")

    # Build allowed base dirs
    from ... import DEFAULT_DATA_DIR
    data_dir = os.environ.get("TUDOU_CLAW_DATA_DIR") or DEFAULT_DATA_DIR
    allowed_bases: list[str] = [
        os.path.normpath(str(_P(data_dir) / "workspaces")),
    ]

    agent_obj = None
    if agent_id:
        try:
            agent_obj = hub.get_agent(agent_id)
        except Exception:
            pass
        if agent_obj is not None:
            for getter in ("_effective_working_dir", "_get_agent_workspace", "_get_agent_home"):
                fn = getattr(agent_obj, getter, None)
                if callable(fn):
                    try:
                        p = fn()
                        if p:
                            allowed_bases.append(os.path.normpath(str(p)))
                    except Exception:
                        pass
            for attr in ("shared_workspace", "working_dir"):
                val = getattr(agent_obj, attr, "") or ""
                if val:
                    allowed_bases.append(os.path.normpath(str(val)))

    # De-dupe
    seen: set = set()
    unique_bases = []
    for b in allowed_bases:
        if b and b not in seen:
            seen.add(b)
            unique_bases.append(b)
    allowed_bases = unique_bases

    # Normalise
    req_path_norm = req_path.replace("\\", "/").lstrip("./").lstrip("/")

    # Resolve
    candidate = ""
    if os.path.isabs(req_path):
        candidate = os.path.normpath(req_path)
    else:
        for base in allowed_bases:
            maybe = os.path.normpath(os.path.join(base, req_path_norm))
            if os.path.isfile(maybe):
                candidate = maybe
                break

    # Basename fallback
    if not candidate and not os.path.isabs(req_path):
        basename = os.path.basename(req_path_norm)
        if basename:
            scanned = 0
            for base in allowed_bases:
                if not os.path.isdir(base):
                    continue
                for dirpath, dirnames, filenames in os.walk(base):
                    dirnames[:] = [d for d in dirnames
                                   if not d.startswith(".")
                                   and d not in ("node_modules", "__pycache__", ".git")]
                    for fn in filenames:
                        scanned += 1
                        if scanned > _MAX_WALK_ENTRIES:
                            break
                        if fn == basename:
                            candidate = os.path.join(dirpath, fn)
                            break
                    if candidate or scanned > _MAX_WALK_ENTRIES:
                        break
                if candidate:
                    break

    if not candidate or not os.path.isfile(candidate):
        raise HTTPException(404, "File not found")

    # Security: ensure file is under an allowed base
    norm_candidate = os.path.normpath(candidate)
    if not any(norm_candidate.startswith(b + os.sep) or norm_candidate == b
               for b in allowed_bases):
        raise HTTPException(403, "Access denied")

    content_type = mimetypes.guess_type(candidate)[0] or "application/octet-stream"
    return FileResponse(candidate, media_type=content_type)


# ---------------------------------------------------------------------------
# Artifact download — opaque ID → file bytes
# ---------------------------------------------------------------------------
# Matches: GET /api/agent_state/artifact/{agent_id}/{artifact_id}
# This replaces html_tag_router._handle_inner for the FastAPI server.

# ArtifactKinds that represent downloadable files
_FILE_KINDS = frozenset({
    "file", "image", "video", "audio", "document", "archive",
})


@router.get("/api/agent_state/artifact/{agent_id}/{artifact_id}")
async def get_artifact(
    agent_id: str,
    artifact_id: str,
    hub=Depends(get_hub),
):
    """Stream an artifact file by its opaque ID.

    No auth required (phase-1 — matches html_tag_router behaviour).
    """
    # 1. find agent
    agent = hub.get_agent(agent_id) if hub else None
    if agent is None:
        raise HTTPException(404, "agent not found")

    # 2. get or install shadow recorder
    shadow = getattr(agent, "_shadow", None)
    if shadow is None:
        try:
            from ...agent_state.shadow import install_into_agent
            shadow = install_into_agent(agent)
        except Exception:
            shadow = None
    if shadow is None:
        raise HTTPException(404, "no shadow state on agent")

    # 3. look up artifact, rebuild store on miss
    try:
        artifact = shadow.state.artifacts.get(artifact_id)
    except Exception as e:
        logger.warning("artifact lookup failed: %s", e)
        raise HTTPException(500, "lookup failed")

    if artifact is None:
        try:
            shadow.rescan_deliverable_dir()
            shadow.compute_file_index_from_events()
            artifact = shadow.state.artifacts.get(artifact_id)
        except Exception as e:
            logger.debug("artifact rebuild failed: %s", e)

    if artifact is None:
        raise HTTPException(404, "artifact not found")

    # 4. validate kind
    if artifact.kind.value not in _FILE_KINDS:
        raise HTTPException(403, f"kind {artifact.kind.value} not streamable")

    # 5. resolve file path
    val = artifact.value or ""

    # Relative path resolution. Search order walks from most-specific
    # (agent's sandbox) to most-general (meeting / project shared
    # workspaces), because artifacts produced in a meeting are more
    # often there than in the agent's private dir.
    if val and not val.startswith(("/", "http://", "https://")):
        _search_dirs = []
        try:
            from ... import DEFAULT_DATA_DIR as _DD
            _sb_root = os.path.join(
                os.environ.get("TUDOU_CLAW_DATA_DIR") or _DD,
                "workspaces", agent.id, "sandbox")
            _search_dirs.append(_sb_root)
        except Exception:
            pass
        _wd = getattr(agent, "working_dir", "") or ""
        if _wd:
            _search_dirs.append(_wd)
        else:
            try:
                _search_dirs.append(str(agent._effective_working_dir()))
            except Exception:
                pass
        try:
            _search_dirs.append(str(agent._get_agent_workspace()))
        except Exception:
            pass
        # Shared workspace (meeting / project) — required for files
        # produced during a meeting, which land outside the agent's
        # own workspace.
        _sws = getattr(agent, "shared_workspace", "") or ""
        if _sws:
            _search_dirs.append(_sws)
        for _base in _search_dirs:
            if not _base:
                continue
            resolved = os.path.normpath(os.path.join(_base, val))
            if os.path.isfile(resolved):
                val = resolved
                break

    # URL redirect
    if val.startswith(("http://", "https://")):
        from fastapi.responses import RedirectResponse
        return RedirectResponse(val)

    # TTL check
    if artifact.is_expired():
        raise HTTPException(410, "artifact expired")

    # Refresh extra_public_roots right before the I5 check so a file
    # produced in the currently-attached meeting/project workspace is
    # considered public even if the shadow state hasn't been refreshed
    # since the agent last changed contexts. Without this the download
    # hits "path outside deliverable_dir" 403 for every meeting artifact
    # (exact symptom users hit on cloud_delivery_insights.pptx links).
    env = shadow.state.env
    _sws = getattr(agent, "shared_workspace", "") or ""
    if _sws and _sws not in env.extra_public_roots:
        env.extra_public_roots = list(env.extra_public_roots or []) + [_sws]

    # I5 security check
    if env.deliverable_dir and not env.is_public_path(val):
        logger.warning("I5 violation: artifact=%s path=%s deliverable=%s extras=%s",
                        artifact.id, val, env.deliverable_dir,
                        env.extra_public_roots)
        raise HTTPException(403, "path outside deliverable_dir")

    # File existence
    if not os.path.isfile(val):
        raise HTTPException(500, "file missing on disk")

    mime = artifact.mime or mimetypes.guess_type(val)[0] or "application/octet-stream"

    # Build filename for Content-Disposition
    md = getattr(artifact, "metadata", None) or {}
    filename = md.get("filename") or os.path.basename(val) or "download"

    logger.info("artifact fetch agent=%s id=%s kind=%s path=%s",
                agent_id, artifact_id, artifact.kind.value, val)

    return FileResponse(
        val,
        media_type=mime,
        filename=filename,
    )
