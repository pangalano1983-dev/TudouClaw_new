"""
mime_registry — central source of truth for "what is this file?"

Every other module that needs to answer "given this filename or URL,
what kind of artifact is it / what mime type / how should the
frontend render it" MUST come through here. The point of this file
is that adding a new file type is a one-line change, and every part
of the pipeline (extractor, store, router, eventually the frontend
renderer) picks it up automatically.

The registry is a flat dict keyed by lowercase extension (with the
leading dot). Each entry holds:

    kind         — ArtifactKind value
    mime         — IANA media type
    render_hint  — string token telling the frontend how to display
    category     — coarse bucket for icons / fallback grouping

`render_hint` values used in phase 1:

    "inline_video"   browser <video> can play it
    "inline_image"   browser <img> can render it
    "inline_audio"   browser <audio> can play it
    "inline_pdf"     browser native PDF viewer (or pdf.js)
    "card"           render a file card with icon + filename + size +
                     download link (e.g. office docs, archives, txt)
    "download"       force a download attachment (no preview)

The frontend is expected to map render_hint -> a render function;
unknown render_hints fall back to "card".

Office docs (docx/xlsx/pptx) get "card" rather than "inline_office"
because no browser can render them inline reliably without an
embedded viewer. We can promote them later when an inline viewer is
in place.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from .artifact import ArtifactKind


@dataclass(frozen=True)
class FileKindInfo:
    kind: ArtifactKind
    mime: str
    render_hint: str       # see module docstring
    category: str          # "video" | "image" | "audio" | "document" | "archive" | "code" | "text" | "other"


# default for unknown extensions / extensionless files
DEFAULT_INFO = FileKindInfo(
    kind=ArtifactKind.FILE,
    mime="application/octet-stream",
    render_hint="card",
    category="other",
)


# ----------------------------------------------------------------------
# THE registry. One line per file type. Add new types here, nowhere else.
# ----------------------------------------------------------------------
_REGISTRY: Dict[str, FileKindInfo] = {
    # ── video ─────────────────────────────────────────────────────────
    ".mp4":  FileKindInfo(ArtifactKind.VIDEO, "video/mp4",       "inline_video", "video"),
    ".mov":  FileKindInfo(ArtifactKind.VIDEO, "video/quicktime", "inline_video", "video"),
    ".webm": FileKindInfo(ArtifactKind.VIDEO, "video/webm",      "inline_video", "video"),
    ".mkv":  FileKindInfo(ArtifactKind.VIDEO, "video/x-matroska", "inline_video", "video"),
    ".m4v":  FileKindInfo(ArtifactKind.VIDEO, "video/mp4",       "inline_video", "video"),
    ".avi":  FileKindInfo(ArtifactKind.VIDEO, "video/x-msvideo", "inline_video", "video"),
    # ── image ─────────────────────────────────────────────────────────
    ".png":  FileKindInfo(ArtifactKind.IMAGE, "image/png",  "inline_image", "image"),
    ".jpg":  FileKindInfo(ArtifactKind.IMAGE, "image/jpeg", "inline_image", "image"),
    ".jpeg": FileKindInfo(ArtifactKind.IMAGE, "image/jpeg", "inline_image", "image"),
    ".gif":  FileKindInfo(ArtifactKind.IMAGE, "image/gif",  "inline_image", "image"),
    ".webp": FileKindInfo(ArtifactKind.IMAGE, "image/webp", "inline_image", "image"),
    ".bmp":  FileKindInfo(ArtifactKind.IMAGE, "image/bmp",  "inline_image", "image"),
    ".svg":  FileKindInfo(ArtifactKind.IMAGE, "image/svg+xml", "inline_image", "image"),
    ".ico":  FileKindInfo(ArtifactKind.IMAGE, "image/x-icon",   "inline_image", "image"),
    ".tiff": FileKindInfo(ArtifactKind.IMAGE, "image/tiff", "card", "image"),
    ".heic": FileKindInfo(ArtifactKind.IMAGE, "image/heic", "card", "image"),
    # ── audio ─────────────────────────────────────────────────────────
    ".mp3":  FileKindInfo(ArtifactKind.AUDIO, "audio/mpeg", "inline_audio", "audio"),
    ".wav":  FileKindInfo(ArtifactKind.AUDIO, "audio/wav",  "inline_audio", "audio"),
    ".m4a":  FileKindInfo(ArtifactKind.AUDIO, "audio/mp4",  "inline_audio", "audio"),
    ".flac": FileKindInfo(ArtifactKind.AUDIO, "audio/flac", "inline_audio", "audio"),
    ".ogg":  FileKindInfo(ArtifactKind.AUDIO, "audio/ogg",  "inline_audio", "audio"),
    ".aac":  FileKindInfo(ArtifactKind.AUDIO, "audio/aac",  "inline_audio", "audio"),
    # ── document: pdf is special — browser-renderable inline ─────────
    ".pdf":  FileKindInfo(ArtifactKind.DOCUMENT, "application/pdf", "inline_pdf", "document"),
    # ── document: office (no inline viewer in phase 1) ───────────────
    ".doc":  FileKindInfo(ArtifactKind.DOCUMENT, "application/msword",                                                     "card", "document"),
    ".docx": FileKindInfo(ArtifactKind.DOCUMENT, "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "card", "document"),
    ".xls":  FileKindInfo(ArtifactKind.DOCUMENT, "application/vnd.ms-excel",                                                "card", "document"),
    ".xlsx": FileKindInfo(ArtifactKind.DOCUMENT, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",       "card", "document"),
    ".xlsm": FileKindInfo(ArtifactKind.DOCUMENT, "application/vnd.ms-excel.sheet.macroEnabled.12",                          "card", "document"),
    ".ppt":  FileKindInfo(ArtifactKind.DOCUMENT, "application/vnd.ms-powerpoint",                                           "card", "document"),
    ".pptx": FileKindInfo(ArtifactKind.DOCUMENT, "application/vnd.openxmlformats-officedocument.presentationml.presentation","card", "document"),
    ".odt":  FileKindInfo(ArtifactKind.DOCUMENT, "application/vnd.oasis.opendocument.text",        "card", "document"),
    ".ods":  FileKindInfo(ArtifactKind.DOCUMENT, "application/vnd.oasis.opendocument.spreadsheet", "card", "document"),
    ".odp":  FileKindInfo(ArtifactKind.DOCUMENT, "application/vnd.oasis.opendocument.presentation","card", "document"),
    ".rtf":  FileKindInfo(ArtifactKind.DOCUMENT, "application/rtf", "card", "document"),
    # ── plain text / markup ───────────────────────────────────────────
    ".txt":  FileKindInfo(ArtifactKind.DOCUMENT, "text/plain",       "card", "text"),
    ".md":   FileKindInfo(ArtifactKind.DOCUMENT, "text/markdown",    "card", "text"),
    ".csv":  FileKindInfo(ArtifactKind.DOCUMENT, "text/csv",         "card", "text"),
    ".tsv":  FileKindInfo(ArtifactKind.DOCUMENT, "text/tab-separated-values", "card", "text"),
    ".log":  FileKindInfo(ArtifactKind.DOCUMENT, "text/plain",       "card", "text"),
    ".json": FileKindInfo(ArtifactKind.DOCUMENT, "application/json", "card", "text"),
    ".yaml": FileKindInfo(ArtifactKind.DOCUMENT, "application/yaml", "card", "text"),
    ".yml":  FileKindInfo(ArtifactKind.DOCUMENT, "application/yaml", "card", "text"),
    ".xml":  FileKindInfo(ArtifactKind.DOCUMENT, "application/xml",  "card", "text"),
    ".html": FileKindInfo(ArtifactKind.DOCUMENT, "text/html",        "card", "text"),
    ".htm":  FileKindInfo(ArtifactKind.DOCUMENT, "text/html",        "card", "text"),
    # ── source code ───────────────────────────────────────────────────
    ".py":   FileKindInfo(ArtifactKind.DOCUMENT, "text/x-python",    "card", "code"),
    ".js":   FileKindInfo(ArtifactKind.DOCUMENT, "application/javascript", "card", "code"),
    ".ts":   FileKindInfo(ArtifactKind.DOCUMENT, "application/typescript", "card", "code"),
    ".tsx":  FileKindInfo(ArtifactKind.DOCUMENT, "application/typescript", "card", "code"),
    ".jsx":  FileKindInfo(ArtifactKind.DOCUMENT, "application/javascript", "card", "code"),
    ".java": FileKindInfo(ArtifactKind.DOCUMENT, "text/x-java",      "card", "code"),
    ".go":   FileKindInfo(ArtifactKind.DOCUMENT, "text/x-go",        "card", "code"),
    ".rs":   FileKindInfo(ArtifactKind.DOCUMENT, "text/x-rust",      "card", "code"),
    ".c":    FileKindInfo(ArtifactKind.DOCUMENT, "text/x-c",         "card", "code"),
    ".cpp":  FileKindInfo(ArtifactKind.DOCUMENT, "text/x-c++",       "card", "code"),
    ".h":    FileKindInfo(ArtifactKind.DOCUMENT, "text/x-c",         "card", "code"),
    ".sh":   FileKindInfo(ArtifactKind.DOCUMENT, "application/x-sh", "card", "code"),
    ".sql":  FileKindInfo(ArtifactKind.DOCUMENT, "application/sql",  "card", "code"),
    # ── archive ───────────────────────────────────────────────────────
    ".zip":  FileKindInfo(ArtifactKind.ARCHIVE, "application/zip",          "download", "archive"),
    ".tar":  FileKindInfo(ArtifactKind.ARCHIVE, "application/x-tar",        "download", "archive"),
    ".gz":   FileKindInfo(ArtifactKind.ARCHIVE, "application/gzip",         "download", "archive"),
    ".tgz":  FileKindInfo(ArtifactKind.ARCHIVE, "application/gzip",         "download", "archive"),
    ".bz2":  FileKindInfo(ArtifactKind.ARCHIVE, "application/x-bzip2",      "download", "archive"),
    ".7z":   FileKindInfo(ArtifactKind.ARCHIVE, "application/x-7z-compressed", "download", "archive"),
    ".rar":  FileKindInfo(ArtifactKind.ARCHIVE, "application/vnd.rar",      "download", "archive"),
}


# ----------------------------------------------------------------------
# public API
# ----------------------------------------------------------------------
def info_for_extension(ext: str) -> FileKindInfo:
    """Return the registry entry for `ext` (case-insensitive, leading
    dot optional). Falls back to DEFAULT_INFO when unknown.
    """
    if not ext:
        return DEFAULT_INFO
    ext = ext.lower()
    if not ext.startswith("."):
        ext = "." + ext
    return _REGISTRY.get(ext, DEFAULT_INFO)


def info_for_value(value: str) -> FileKindInfo:
    """Given a filename, path, or URL, return the registry entry that
    matches its extension. URLs are stripped of query string and
    fragment first.
    """
    if not value:
        return DEFAULT_INFO
    base = value.split("?", 1)[0].split("#", 1)[0]
    # last segment after / or \
    last_slash = max(base.rfind("/"), base.rfind("\\"))
    name = base[last_slash + 1:] if last_slash >= 0 else base
    dot = name.rfind(".")
    if dot < 0 or dot == len(name) - 1:
        return DEFAULT_INFO
    return info_for_extension(name[dot:])


def is_inline_renderable(render_hint: str) -> bool:
    return render_hint in (
        "inline_video", "inline_image", "inline_audio", "inline_pdf",
    )


def all_known_extensions() -> tuple:
    """For tests / introspection."""
    return tuple(sorted(_REGISTRY.keys()))


def register(ext: str, info: FileKindInfo) -> None:
    """Programmatic extension point — used by tests or future plugins
    to add a new file type at runtime. Not intended for general use;
    edit the table above instead.
    """
    if not ext.startswith("."):
        ext = "." + ext
    _REGISTRY[ext.lower()] = info
