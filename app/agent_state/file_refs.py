"""
file_refs — turn arbitrary chat-message text into FileCard-ready ref dicts.

Why a separate module instead of folding this into ``shadow.py``?

  * Project chat and meeting chat have NO shadow recorder of their own —
    their messages are not part of any single agent's event stream. They
    still need exactly the same path-extraction + dedup behaviour the
    agent chat already has, just keyed off a different ``base_dir`` and
    routed through a different artifact URL.
  * The agent-chat path keeps its existing pipeline (event walk → ingest
    into shadow store → URL via ``build_artifact_url``) intact. This
    module is the slim, store-less variant for callers that only need
    "given a string and a directory, give me FileCard dicts".

Public API
----------

``build_refs_from_text(text, base_dir, *, url_for_path) -> list[dict]``

    Pure helper. Pulls every URL and absolute/relative filesystem path
    out of ``text``, normalises relative paths against ``base_dir``,
    de-duplicates by absolute value, stats the file (for size/mtime),
    classifies via ``mime_registry``, and returns FileCard-shaped dicts.

    ``url_for_path(abs_path, art_id)`` is injected by the caller so this
    module stays agnostic of routing — meeting chat routes through the
    sender agent's existing artifact route; project chat routes through
    a project-scoped route. Both end up with the same dict shape the
    frontend's ``_appendFileCards`` expects.

The dict shape mirrors what ``ShadowRecorder._artifact_to_ref`` produces
so frontend code can be shared.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Callable, Dict, List, Optional

from .extractors import (
    extract_from_text,
    normalize_path_candidates,
    stable_artifact_id,
)
from .mime_registry import DEFAULT_INFO, info_for_value

logger = logging.getLogger("tudou.agent_state.file_refs")


# Artifact kind values that should render as a FileCard. Mirrors the
# `_FILE_KINDS` set used by html_tag_router and ShadowRecorder.
_FILE_KINDS = frozenset({
    "file", "video", "image", "audio", "document", "archive",
})


def _safe_stat(path: str) -> Optional[os.stat_result]:
    try:
        return os.stat(path)
    except OSError:
        return None


def _is_inside(path: str, base: str) -> bool:
    """True iff ``path`` is inside ``base`` after normalisation. Defence
    in depth: keeps ../../etc/passwd from escaping a project workspace."""
    try:
        p = os.path.realpath(path)
        b = os.path.realpath(base)
        if not b:
            return True
        return p == b or p.startswith(b.rstrip(os.sep) + os.sep)
    except Exception:
        return False


def build_refs_from_text(
    text: str,
    base_dir: str,
    *,
    url_for_path: Callable[[str, str], str],
    require_inside_base: bool = True,
) -> List[Dict[str, Any]]:
    """Extract file refs from a chat-message body.

    Parameters
    ----------
    text : str
        Raw assistant / user message content.
    base_dir : str
        Directory to resolve relative paths against. Also used as the
        whitelist when ``require_inside_base=True`` — paths that escape
        this dir are dropped to prevent the chat from linking to random
        files on disk.
    url_for_path : callable
        ``(abs_path, art_id) -> str``. The caller decides how to route
        the click — agent route, project route, http URL passthrough, etc.
    require_inside_base : bool
        If True (default), local paths outside ``base_dir`` are dropped.
        Set False for the meeting case where messages may legitimately
        reference any agent's workspace.

    Returns
    -------
    list[dict]
        FileCard-shaped dicts. May be empty. Never raises.
    """
    out: List[Dict[str, Any]] = []
    if not text:
        return out
    try:
        cands = extract_from_text(text)
        if base_dir:
            normalize_path_candidates(cands, base_dir)
    except Exception as e:
        logger.debug("file_refs: extract failed: %s", e)
        return out

    seen_ids: set = set()
    base_abs = ""
    if base_dir:
        try:
            base_abs = os.path.abspath(base_dir)
        except Exception:
            base_abs = ""

    for c in cands:
        try:
            v = c.get("value") or ""
            if not v:
                continue
            md = c.get("metadata") or {}

            # URL candidates pass through unchanged. They get a stable
            # id off the URL string itself (so multiple mentions dedup).
            is_url = v.startswith(("http://", "https://"))
            if is_url:
                art_id = stable_artifact_id(v)
                if art_id in seen_ids:
                    continue
                seen_ids.add(art_id)
                kind_val = c.get("kind")
                kind_str = kind_val.value if hasattr(kind_val, "value") else str(kind_val or "url")
                if kind_str not in _FILE_KINDS and kind_str != "url":
                    continue
                ref = {
                    "id": art_id,
                    "url": v,
                    "filename": md.get("filename") or c.get("label") or art_id,
                    "label": c.get("label") or md.get("filename") or art_id,
                    "kind": kind_str,
                    "mime": c.get("mime"),
                    "render_hint": md.get("render_hint") or "card",
                    "category": md.get("category") or "other",
                    "size": None,
                    "produced_at": None,
                }
                out.append(ref)
                continue

            # Local path candidates: must exist on disk + be a file +
            # have a recognised extension.
            abs_path = os.path.abspath(v)
            info = info_for_value(abs_path)
            if info is DEFAULT_INFO:
                continue
            kind_str = info.kind.value
            if kind_str not in _FILE_KINDS:
                continue
            if require_inside_base and base_abs and not _is_inside(abs_path, base_abs):
                continue
            st = _safe_stat(abs_path)
            if st is None or not os.path.isfile(abs_path):
                # Path looks plausible but isn't there — skip rather than
                # render a broken card.
                continue
            art_id = stable_artifact_id(abs_path)
            if art_id in seen_ids:
                continue
            seen_ids.add(art_id)
            filename = md.get("filename") or os.path.basename(abs_path) or abs_path
            url = ""
            try:
                url = url_for_path(abs_path, art_id) or ""
            except Exception as e:
                logger.debug("file_refs: url_for_path failed: %s", e)
                url = ""
            ref = {
                "id": art_id,
                "url": url,
                "filename": filename,
                "label": filename,
                "kind": kind_str,
                "mime": info.mime,
                "render_hint": info.render_hint,
                "category": info.category,
                "size": st.st_size,
                "produced_at": st.st_mtime,
            }
            out.append(ref)
        except Exception as e:
            logger.debug("file_refs: candidate failed: %s", e)
            continue
    return out


__all__ = ["build_refs_from_text"]
