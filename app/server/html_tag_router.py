"""
html_tag_router — backend handler for HTML-tag-driven artifact fetches.

When the frontend renders a chat message containing an artifact
reference, e.g.

    <video src="/api/agent_state/artifact/<agent_id>/<artifact_id>" controls>

the browser issues a GET to one of the routes defined here. This
module is the backend half of the "产物输出契约":

  * Opaque artifact ids in, byte streams out.
  * Mime type comes from ArtifactStore metadata, not from extension
    sniffing on the request URL.
  * I5 (path-cross-domain) is re-checked at fetch time, even though
    it was already checked at commit time, as defence in depth.
  * HTTP Range is supported so <video> can seek.
  * Phase-1: NO authentication. The user has explicitly chosen to
    get the flow working first; add auth in phase 2 by gating each
    handler with a session/owner check. Tracking note left below.

Routes registered (dispatched from portal_routes_get._do_get_inner):

    GET /api/agent_state/artifact/<agent_id>/<artifact_id>
        -> 200 + bytes  on success
        -> 206          on a Range request
        -> 404          unknown agent or unknown artifact
        -> 403          artifact is not file-kind, or path outside deliverable_dir
        -> 410          artifact has expired (ttl_s elapsed)
        -> 416          unsatisfiable Range
        -> 500          file missing on disk

This module deliberately does NOT import from app.agent (no circular
dep). It looks up agents through hub.get_agent(), and the artifact
through `agent._shadow.state.artifacts`.
"""
from __future__ import annotations

import logging
import os
import re
import time
from typing import Optional, Tuple

from ..defaults import PROJECT_SCAN_MAX_FILES

logger = logging.getLogger("tudou.html_tag_router")


# ----------------------------------------------------------------------
# config — single source of truth for every tunable in this router.
#
# Keep this dict small and self-contained. If/when any of these need to
# vary by environment, the migration target is one of two things:
#   1. promote `_CONFIG` to a module-level call into app.config (still
#      a dict, just sourced externally), or
#   2. inject via constructor when this router is moved off the
#      stdlib BaseHTTPRequestHandler shim.
# Until either of those is needed, leave it here.
# ----------------------------------------------------------------------
_CONFIG = {
    # ---- routing ------------------------------------------------------
    # Public URL prefix the frontend hits to fetch an artifact byte
    # stream. Anything that needs to construct one of these URLs MUST
    # go through `build_artifact_url()` — never hand-concatenate.
    "route_prefix": "/api/agent_state/artifact/",

    # Project-scoped artifact streaming. Project chat messages reference
    # files in `project.working_directory`, which is NOT owned by any
    # single agent's shadow store, so they need their own resolution
    # path. Construct via `build_project_artifact_url()`.
    "project_route_prefix": "/api/agent_state/project_artifact/",

    # Walking a project workspace to resolve a stable artifact id back
    # to a real path is O(n_files). Cap the walk so a runaway project
    # workspace can't pin a request thread.
    "project_scan_max_files": PROJECT_SCAN_MAX_FILES,

    # ---- streaming ----------------------------------------------------
    # Read buffer size for both full-file and Range responses. 64 KB is
    # the sweet spot for <video> seeking on local LAN.
    "chunk_size": 64 * 1024,

    # ---- caching ------------------------------------------------------
    # Cache-Control returned for successful artifact bytes. `private`
    # because artifacts are per-agent and should never end up in a
    # shared cache.
    "default_cache_control": "private, max-age=300",
    # Cache-Control for error / redirect responses — never cached.
    "error_cache_control": "no-store",

    # ---- kinds --------------------------------------------------------
    # Artifact kinds whose `.value` is a real on-disk path that this
    # router is allowed to stream. Must stay in sync with
    # `app/agent_state/artifact.py::ArtifactKind`.
    "file_kinds": frozenset({
        "file", "video", "image", "audio", "document", "archive",
    }),

    # ---- HTTP semantics ----------------------------------------------
    # Whether to advertise "Accept-Ranges: bytes". Off would break
    # <video> seek, but kept here so tests can flip it.
    "accept_ranges": True,

    # Maximum agent_id / artifact_id length we'll even look up. Cheap
    # guard against pathological URLs hitting hub.get_agent().
    "max_id_len": 256,

    # ---- Content-Disposition -----------------------------------------
    # render_hint values that should open in the browser tab when the
    # user clicks the file card. Anything not in this set is forced to
    # `attachment` so the browser triggers a download dialog.
    # Source: app/agent_state/mime_registry.py FileKindInfo.render_hint
    "inline_render_hints": frozenset({
        "inline_video",
        "inline_image",
        "inline_audio",
        "inline_pdf",
    }),

    # Fallback filename when an artifact has no filename in metadata.
    # The artifact id is opaque so we tag the extension on after, see
    # `_pick_filename()`.
    "fallback_filename": "file",
}

# Backward-compatible aliases — existing imports keep working.
ROUTE_PREFIX = _CONFIG["route_prefix"]
CHUNK_SIZE = _CONFIG["chunk_size"]
DEFAULT_CACHE_CONTROL = _CONFIG["default_cache_control"]
_FILE_KINDS = _CONFIG["file_kinds"]


# ----------------------------------------------------------------------
# entry point — called by portal_routes_get._do_get_inner
# ----------------------------------------------------------------------
def matches(path: str) -> bool:
    """True iff `path` should be handled by this router."""
    return (
        path.startswith(_CONFIG["route_prefix"])
        or path.startswith(_CONFIG["project_route_prefix"])
    )


def handle(handler, path: str) -> None:
    """Dispatch a single GET request. `handler` is a stdlib
    BaseHTTPRequestHandler instance with the project's `_json` /
    `_html` helpers attached.
    """
    try:
        if path.startswith(_CONFIG["project_route_prefix"]):
            _handle_project_inner(handler, path)
        else:
            _handle_inner(handler, path)
    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError) as e:
        # client disconnected mid-stream — not our problem
        logger.debug("client disconnected during artifact fetch: %s", e)
    except Exception as e:
        logger.error("artifact route error for %s: %s", path, e, exc_info=True)
        try:
            _send_plain_error(handler, 500, f"server error: {type(e).__name__}")
        except Exception:
            pass


# ----------------------------------------------------------------------
def _handle_inner(handler, path: str) -> None:
    rest = path[len(_CONFIG["route_prefix"]):]
    parts = rest.split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        _send_plain_error(handler, 400, "expected /agent_id/artifact_id")
        return
    agent_id, artifact_id = parts[0], parts[1]
    # path may carry trailing slash or query — strip both
    artifact_id = artifact_id.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    if not artifact_id:
        _send_plain_error(handler, 400, "missing artifact id")
        return
    max_id = _CONFIG["max_id_len"]
    if len(agent_id) > max_id or len(artifact_id) > max_id:
        _send_plain_error(handler, 400, "id too long")
        return

    # ------------------------------------------------------------------
    # 1. find the agent
    # ------------------------------------------------------------------
    from ..hub import get_hub  # local import: avoid import cycles at module load
    hub = get_hub()
    agent = hub.get_agent(agent_id) if hub else None
    if agent is None:
        _send_plain_error(handler, 404, "agent not found")
        return

    # ------------------------------------------------------------------
    # 2. find the shadow recorder + the artifact
    # ------------------------------------------------------------------
    shadow = getattr(agent, "_shadow", None)
    if shadow is None:
        # Lazy-install: after a restart _shadow doesn't exist until the
        # first chat. Install it now so artifact URLs from the previous
        # session can still be resolved.
        try:
            from ..agent_state.shadow import install_into_agent
            shadow = install_into_agent(agent)
        except Exception:
            shadow = None
    if shadow is None:
        _send_plain_error(handler, 404, "no shadow state on agent")
        return
    try:
        artifact = shadow.state.artifacts.get(artifact_id)
    except Exception as e:
        logger.warning("artifact lookup failed: %s", e)
        _send_plain_error(handler, 500, "lookup failed")
        return
    if artifact is None:
        # After a restart the in-memory store is empty. Rebuild it
        # from events + deliverable_dir scan, then retry the lookup.
        try:
            shadow.rescan_deliverable_dir()
            shadow.compute_file_index_from_events()
            artifact = shadow.state.artifacts.get(artifact_id)
        except Exception as e:
            logger.debug("artifact rebuild failed: %s", e)
    if artifact is None:
        _send_plain_error(handler, 404, "artifact not found")
        return

    # ------------------------------------------------------------------
    # 3. validate kind — only file-like artifacts get streamed
    # ------------------------------------------------------------------
    if artifact.kind.value not in _CONFIG["file_kinds"]:
        _send_plain_error(handler, 403, f"kind {artifact.kind.value} not streamable")
        return

    # ------------------------------------------------------------------
    # 4. Resolve artifact value (file path)
    # ------------------------------------------------------------------
    val = artifact.value or ""

    # Resolve relative paths (e.g. "./workspace/report.pptx") against the
    # agent's sandbox root / working directory.  Tool results store the
    # original path the LLM passed to write_file, which is relative to
    # the sandbox root, NOT the server process CWD.
    if val and not val.startswith(("/", "http://", "https://")):
        _search_dirs = []
        # 1. Agent's sandbox root (tools resolve paths against this)
        try:
            from .. import DEFAULT_DATA_DIR as _DD
            _sb_root = os.path.join(
                os.environ.get("TUDOU_CLAW_DATA_DIR") or _DD,
                "workspaces", agent.id, "sandbox")
            _search_dirs.append(_sb_root)
        except Exception:
            pass
        # 2. Agent's working_dir / effective working dir
        _wd = getattr(agent, "working_dir", "") or ""
        if _wd:
            _search_dirs.append(_wd)
        else:
            try:
                _search_dirs.append(str(agent._effective_working_dir()))
            except Exception:
                pass
        # 3. Agent workspace root
        try:
            _search_dirs.append(str(agent._get_agent_workspace()))
        except Exception:
            pass
        for _base in _search_dirs:
            if not _base:
                continue
            resolved = os.path.normpath(os.path.join(_base, val))
            if os.path.isfile(resolved):
                val = resolved
                break

    # ------------------------------------------------------------------
    # 4b. URL-valued artifacts: redirect, don't stream
    # ------------------------------------------------------------------
    if val.startswith(("http://", "https://")):
        try:
            handler.send_response(302)
            handler.send_header("Location", val)
            handler.send_header("Cache-Control", _CONFIG["error_cache_control"])
            handler.end_headers()
        except Exception:
            pass
        return

    # ------------------------------------------------------------------
    # 5. ttl
    # ------------------------------------------------------------------
    if artifact.is_expired():
        _send_plain_error(handler, 410, "artifact expired")
        return

    # ------------------------------------------------------------------
    # 6. I5 re-check (defence in depth) — must be inside deliverable_dir
    # ------------------------------------------------------------------
    env = shadow.state.env
    if env.deliverable_dir and not env.is_public_path(val):
        logger.warning(
            "I5 violation at fetch time: artifact=%s path=%s deliverable=%s",
            artifact.id, val, env.deliverable_dir,
        )
        _send_plain_error(handler, 403, "path outside deliverable_dir")
        return

    # ------------------------------------------------------------------
    # 7. real file?
    # ------------------------------------------------------------------
    if not os.path.isfile(val):
        _send_plain_error(handler, 500, "file missing on disk")
        return

    try:
        file_size = os.path.getsize(val)
    except OSError as e:
        _send_plain_error(handler, 500, f"stat failed: {e}")
        return

    # ------------------------------------------------------------------
    # 8. Range parsing + streaming
    # ------------------------------------------------------------------
    range_header = handler.headers.get("Range") if hasattr(handler, "headers") else None
    rng = _parse_range(range_header, file_size) if range_header else None
    mime = artifact.mime or "application/octet-stream"
    disposition = _build_content_disposition(artifact)

    # audit
    logger.info(
        "artifact fetch agent=%s id=%s kind=%s size=%d range=%s disp=%s",
        agent_id, artifact_id, artifact.kind.value, file_size, rng, disposition,
    )

    if rng is None:
        _stream_full(handler, val, file_size, mime, disposition)
        return

    start, end = rng
    if start >= file_size or end >= file_size or start > end:
        # 416
        try:
            handler.send_response(416)
            handler.send_header("Content-Range", f"bytes */{file_size}")
            handler.end_headers()
        except Exception:
            pass
        return

    _stream_range(handler, val, file_size, mime, start, end, disposition)


# ----------------------------------------------------------------------
# Content-Disposition
# ----------------------------------------------------------------------
def _pick_filename(artifact) -> str:
    """Best filename for the Content-Disposition header.

    Order of preference:
      1. metadata["filename"] (set by extractor from the original
         path / URL — this is the human-meaningful name)
      2. basename of artifact.value (in case metadata is missing)
      3. fallback string from _CONFIG
    Always non-empty, always stripped of path separators.
    """
    md = getattr(artifact, "metadata", None) or {}
    name = md.get("filename") or ""
    if not name:
        v = artifact.value or ""
        # split on both unix and windows separators
        last = max(v.rfind("/"), v.rfind("\\"))
        name = v[last + 1:] if last >= 0 else v
        # strip query / fragment if value was a URL
        name = name.split("?", 1)[0].split("#", 1)[0]
    name = name.strip().replace("\r", "").replace("\n", "")
    if not name:
        name = _CONFIG["fallback_filename"]
    return name


def _encode_filename_header(filename: str) -> str:
    """Return the `filename=...; filename*=...` portion of a
    Content-Disposition header.

    For ASCII names we emit only `filename="x.ext"`. For names with
    non-ASCII chars (Chinese / emoji / accents) we ALSO emit the
    RFC 5987 `filename*=UTF-8''...` form so modern browsers pick the
    correct decoding.
    """
    safe_ascii = filename.encode("ascii", "ignore").decode("ascii") or _CONFIG["fallback_filename"]
    safe_ascii = safe_ascii.replace('"', "").replace("\\", "")
    if safe_ascii == filename:
        return f'filename="{safe_ascii}"'
    # RFC 5987 percent-encoding for the UTF-8 form
    from urllib.parse import quote
    encoded = quote(filename, safe="")
    return f"filename=\"{safe_ascii}\"; filename*=UTF-8''{encoded}"


def _build_content_disposition(artifact) -> str:
    """Decide `inline` vs `attachment` based on the artifact's
    render_hint, and append a properly-encoded filename.

    The render_hint is set at extraction time by mime_registry. If
    missing (e.g. older artifact), we fall back to `attachment` —
    safer default: a download dialog never breaks the page.
    """
    md = getattr(artifact, "metadata", None) or {}
    hint = md.get("render_hint") or ""
    disposition_type = "inline" if hint in _CONFIG["inline_render_hints"] else "attachment"
    filename = _pick_filename(artifact)
    return f"{disposition_type}; {_encode_filename_header(filename)}"


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$", re.IGNORECASE)


def _parse_range(header: str, file_size: int) -> Optional[Tuple[int, int]]:
    """Parse a single-range `Range: bytes=N-M` header.

    Multi-range (`bytes=0-100,200-300`) is intentionally not supported
    in phase 1 — browsers almost never use it for video. Returns
    (start, end) inclusive, or None if the header is malformed.
    """
    if not header:
        return None
    m = _RANGE_RE.match(header.strip())
    if not m:
        return None
    s_raw, e_raw = m.group(1), m.group(2)
    if s_raw == "" and e_raw == "":
        return None
    if s_raw == "":
        # suffix range: last N bytes
        n = int(e_raw)
        if n <= 0:
            return None
        start = max(0, file_size - n)
        end = file_size - 1
        return (start, end)
    start = int(s_raw)
    end = int(e_raw) if e_raw else file_size - 1
    return (start, end)


def _stream_full(handler, path: str, file_size: int, mime: str, disposition: str) -> None:
    handler.send_response(200)
    handler.send_header("Content-Type", mime)
    handler.send_header("Content-Length", str(file_size))
    handler.send_header("Content-Disposition", disposition)
    if _CONFIG["accept_ranges"]:
        handler.send_header("Accept-Ranges", "bytes")
    handler.send_header("Cache-Control", _CONFIG["default_cache_control"])
    _add_artifact_security_headers(handler)
    handler.end_headers()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(_CONFIG["chunk_size"])
            if not chunk:
                break
            try:
                handler.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                return


def _stream_range(
    handler, path: str, file_size: int, mime: str, start: int, end: int, disposition: str
) -> None:
    length = end - start + 1
    handler.send_response(206)
    handler.send_header("Content-Type", mime)
    handler.send_header("Content-Length", str(length))
    handler.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
    handler.send_header("Content-Disposition", disposition)
    if _CONFIG["accept_ranges"]:
        handler.send_header("Accept-Ranges", "bytes")
    handler.send_header("Cache-Control", _CONFIG["default_cache_control"])
    _add_artifact_security_headers(handler)
    handler.end_headers()
    remaining = length
    with open(path, "rb") as f:
        f.seek(start)
        while remaining > 0:
            chunk = f.read(min(_CONFIG["chunk_size"], remaining))
            if not chunk:
                break
            try:
                handler.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                return
            remaining -= len(chunk)


def _add_artifact_security_headers(handler) -> None:
    """Add standard security headers to artifact responses."""
    # Prevent MIME-type sniffing attacks
    handler.send_header("X-Content-Type-Options", "nosniff")
    # Prevent clickjacking attacks
    handler.send_header("X-Frame-Options", "DENY")
    # Enable browser XSS protection
    handler.send_header("X-XSS-Protection", "1; mode=block")


def _send_plain_error(handler, code: int, message: str) -> None:
    """Tiny helper that emits an error without depending on
    handler._json (which would set Content-Type: application/json
    and confuse a <video> element issuing the request)."""
    body = message.encode("utf-8")
    try:
        handler.send_response(code)
        handler.send_header("Content-Type", "text/plain; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("Cache-Control", _CONFIG["error_cache_control"])
        _add_artifact_security_headers(handler)
        handler.end_headers()
        handler.wfile.write(body)
    except Exception:
        pass


# ----------------------------------------------------------------------
# URL helper — used by ShadowRecorder.get_public_url
# ----------------------------------------------------------------------
def build_artifact_url(agent_id: str, artifact_id: str) -> str:
    """Return the public URL the frontend should use to <video src=...>
    a given artifact. This is the canonical place that knows the URL
    shape — never hand-construct it elsewhere.
    """
    if not agent_id or not artifact_id:
        return ""
    return f"{_CONFIG['route_prefix']}{agent_id}/{artifact_id}"


# ----------------------------------------------------------------------
# Project artifact route — store-less variant for project chat.
#
# Project chat messages reference files in `project.working_directory`.
# There is no per-project shadow store; instead we resolve the stable
# artifact id back to an on-disk path by walking the project workspace
# at fetch time. This is O(n_files) but bounded by `project_scan_max_files`
# and only runs on click — usually fine for human-scale workspaces.
# ----------------------------------------------------------------------
def build_project_artifact_url(project_id: str, artifact_id: str) -> str:
    """Public URL for a file inside ``project.working_directory``.

    Mirrors ``build_artifact_url()`` for the project case.
    """
    if not project_id or not artifact_id:
        return ""
    return f"{_CONFIG['project_route_prefix']}{project_id}/{artifact_id}"


def _handle_project_inner(handler, path: str) -> None:
    rest = path[len(_CONFIG["project_route_prefix"]):]
    parts = rest.split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        _send_plain_error(handler, 400, "expected /project_id/artifact_id")
        return
    project_id, artifact_id = parts[0], parts[1]
    artifact_id = artifact_id.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    if not artifact_id:
        _send_plain_error(handler, 400, "missing artifact id")
        return
    max_id = _CONFIG["max_id_len"]
    if len(project_id) > max_id or len(artifact_id) > max_id:
        _send_plain_error(handler, 400, "id too long")
        return

    # 1. find the project
    from ..hub import get_hub
    hub = get_hub()
    project = hub.get_project(project_id) if hub else None
    if project is None:
        _send_plain_error(handler, 404, "project not found")
        return

    work_dir = (getattr(project, "working_directory", "") or "").strip()
    if not work_dir or not os.path.isdir(work_dir):
        _send_plain_error(handler, 404, "project working_directory unavailable")
        return

    # 2. resolve artifact_id back to a real path inside work_dir
    abs_path = _resolve_project_artifact_path(work_dir, artifact_id)
    if abs_path is None:
        _send_plain_error(handler, 404, "artifact not found")
        return

    # 3. defence-in-depth path containment check
    try:
        real_path = os.path.realpath(abs_path)
        real_base = os.path.realpath(work_dir)
        if not (real_path == real_base or real_path.startswith(real_base.rstrip(os.sep) + os.sep)):
            _send_plain_error(handler, 403, "path outside project workspace")
            return
    except Exception:
        _send_plain_error(handler, 500, "path validation failed")
        return

    if not os.path.isfile(real_path):
        _send_plain_error(handler, 500, "file missing on disk")
        return

    try:
        file_size = os.path.getsize(real_path)
    except OSError as e:
        _send_plain_error(handler, 500, f"stat failed: {e}")
        return

    # 4. classify via mime_registry to pick mime + render_hint + filename
    try:
        from ..agent_state.mime_registry import info_for_value, DEFAULT_INFO
        info = info_for_value(real_path)
        if info is DEFAULT_INFO:
            _send_plain_error(handler, 403, "unsupported file type")
            return
        if info.kind.value not in _CONFIG["file_kinds"]:
            _send_plain_error(handler, 403, f"kind {info.kind.value} not streamable")
            return
        mime = info.mime or "application/octet-stream"
        render_hint = info.render_hint or ""
    except Exception as e:
        logger.warning("project artifact classify failed: %s", e)
        _send_plain_error(handler, 500, "classify failed")
        return

    filename = os.path.basename(real_path) or _CONFIG["fallback_filename"]
    disposition_type = "inline" if render_hint in _CONFIG["inline_render_hints"] else "attachment"
    disposition = f"{disposition_type}; {_encode_filename_header(filename)}"

    logger.info(
        "project artifact fetch project=%s id=%s size=%d disp=%s",
        project_id, artifact_id, file_size, disposition,
    )

    # 5. Range parsing + streaming (reuse helpers from agent route)
    range_header = handler.headers.get("Range") if hasattr(handler, "headers") else None
    rng = _parse_range(range_header, file_size) if range_header else None
    if rng is None:
        _stream_full(handler, real_path, file_size, mime, disposition)
        return
    start, end = rng
    if start >= file_size or end >= file_size or start > end:
        try:
            handler.send_response(416)
            handler.send_header("Content-Range", f"bytes */{file_size}")
            handler.end_headers()
        except Exception:
            pass
        return
    _stream_range(handler, real_path, file_size, mime, start, end, disposition)


def _resolve_project_artifact_path(work_dir: str, artifact_id: str) -> Optional[str]:
    """Walk ``work_dir`` looking for a file whose ``stable_artifact_id``
    matches ``artifact_id``. Returns the absolute path or None.

    Bounded by ``project_scan_max_files`` to keep a runaway workspace
    from pinning the request thread. Skips hidden + cache directories
    to mirror ``scan_deliverable_dir``.
    """
    try:
        from ..agent_state.extractors import stable_artifact_id
    except Exception as e:
        logger.warning("project artifact resolve: import failed: %s", e)
        return None
    try:
        root_abs = os.path.abspath(work_dir)
    except Exception:
        return None
    seen = 0
    cap = _CONFIG.get("project_scan_max_files", 5000)
    for dirpath, dirnames, filenames in os.walk(root_abs, followlinks=False):
        # mirror scanner: skip hidden + __pycache__
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d != "__pycache__"]
        for fn in filenames:
            if fn.startswith("."):
                continue
            seen += 1
            if seen > cap:
                logger.warning(
                    "project artifact resolve: scan cap %d hit in %s",
                    cap, root_abs,
                )
                return None
            try:
                full = os.path.abspath(os.path.join(dirpath, fn))
            except Exception:
                continue
            try:
                if stable_artifact_id(full) == artifact_id:
                    return full
            except Exception:
                continue
    return None
