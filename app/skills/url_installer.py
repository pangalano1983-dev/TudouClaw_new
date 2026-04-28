"""Install Anthropic Agent Skills from a URL — direct path (no LLM).

Use case: a user finds a skill on ClawHub (https://clawhub.ai/<author>/<slug>)
or has a direct .zip URL pointing at a SKILL.md-shaped skill bundle. They
want to install it as-is, no semantic conversion.

For incompatible skills that need rewriting (different SDK, different
conventions), see ``app/skills/builtin/tudou-builtin/skill-converter/`` —
that flow uses an LLM to adapt the skill.

Pipeline
========
1. Resolve URL → download ``.zip`` (or single ``SKILL.md``)
2. Extract to a temp dir
3. Locate the skill root (zip may have a wrapper directory)
4. Copy into the user catalog dir (so it persists in the SkillStore)
5. Call ``engine.install_from_directory`` (registers as installed → grantable)
6. Re-scan the SkillStore so the catalog list reflects the new entry

The whole pipeline is best-effort; each step's error is wrapped in a
clear ``InstallFromUrlError`` so the API can surface it to the UI.
"""
from __future__ import annotations

import io
import logging
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger("tudou.skill_url_installer")


# ──────────────────────────────────────────────────────────────────────
# Errors
# ──────────────────────────────────────────────────────────────────────


class InstallFromUrlError(RuntimeError):
    """Raised when the URL → install pipeline can't complete."""


# ──────────────────────────────────────────────────────────────────────
# URL → download URL resolution
# ──────────────────────────────────────────────────────────────────────


# ClawHub registry → underlying download API. Discovered by inspecting
# the page's Download button (April 2026). If ClawHub changes domains,
# this constant needs updating.
_CLAWHUB_DOWNLOAD_API = (
    "https://wry-manatee-359.convex.site/api/v1/download?slug={slug}"
)

_CLAWHUB_HOSTS = ("clawhub.ai", "www.clawhub.ai")


def resolve_download_url(url_or_slug: str) -> tuple[str, str]:
    """Resolve a user-provided URL or slug into (download_url, hint_name).

    Recognized inputs:
      * ``https://clawhub.ai/<author>/<slug>``     → ClawHub registry
      * ``https://clawhub.ai/<slug>``              → slug-only registry path
      * ``<author>/<slug>``                         → bare slug, treated as ClawHub
      * any URL ending with ``.zip``                → direct download
      * any URL ending with ``SKILL.md``           → single-file skill (we wrap it)

    Returns (download_url, hint_name) where ``hint_name`` is a best-guess
    folder name (used as a fallback when SKILL.md frontmatter has no slug).
    Raises ``InstallFromUrlError`` on unrecognized input.
    """
    s = (url_or_slug or "").strip()
    if not s:
        raise InstallFromUrlError("empty URL")

    # Bare slug like "ivangdavila/word-docx" or "word-docx"
    if "://" not in s:
        slug = s.split("/")[-1]  # last component
        if not slug:
            raise InstallFromUrlError(f"can't extract slug from {s!r}")
        return _CLAWHUB_DOWNLOAD_API.format(slug=slug), slug

    parsed = urlparse(s)
    host = (parsed.hostname or "").lower()
    path = parsed.path or ""

    # ClawHub URL → derive slug from path tail, hit download API
    if host in _CLAWHUB_HOSTS:
        parts = [p for p in path.split("/") if p]
        if not parts:
            raise InstallFromUrlError(
                f"ClawHub URL has no path: {s!r}"
            )
        slug = parts[-1]
        return _CLAWHUB_DOWNLOAD_API.format(slug=slug), slug

    # Direct .zip URL
    if path.lower().endswith(".zip"):
        name = Path(path).stem or (host or "downloaded-skill")
        return s, name

    # Direct SKILL.md URL — supported but treated specially (wrap in skill dir)
    if path.lower().endswith("skill.md"):
        # Caller path ``download_and_extract`` will detect and handle this.
        name = parsed.path.rstrip("/").split("/")[-2] if "/" in path else "downloaded-skill"
        return s, name

    raise InstallFromUrlError(
        f"unrecognized URL format: {s!r}. Supported: "
        f"clawhub.ai URL/slug, any .zip URL, raw SKILL.md URL."
    )


# ──────────────────────────────────────────────────────────────────────
# Download + extract
# ──────────────────────────────────────────────────────────────────────


_USER_AGENT = "TudouClaw-SkillInstaller/1.0"
_DOWNLOAD_TIMEOUT_S = 30
_MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024  # 50 MB cap — skill bundles are tiny


def fetch_url_binary(url: str, timeout: int = _DOWNLOAD_TIMEOUT_S) -> bytes:
    """Download URL as bytes. Caps at 50MB; raises on HTTP error / timeout."""
    try:
        import requests
    except ImportError as e:
        raise InstallFromUrlError(f"requests not installed: {e}") from e

    headers = {"User-Agent": _USER_AGENT, "Accept": "application/zip,*/*"}
    try:
        resp = requests.get(
            url, headers=headers, timeout=timeout,
            allow_redirects=True, stream=True,
        )
    except Exception as e:
        raise InstallFromUrlError(f"download failed: {e}") from e
    if resp.status_code >= 400:
        raise InstallFromUrlError(
            f"HTTP {resp.status_code} fetching {url}"
        )
    buf = io.BytesIO()
    total = 0
    for chunk in resp.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        total += len(chunk)
        if total > _MAX_DOWNLOAD_BYTES:
            raise InstallFromUrlError(
                f"download exceeds {_MAX_DOWNLOAD_BYTES // (1024*1024)} MB cap"
            )
        buf.write(chunk)
    return buf.getvalue()


def extract_to_temp(content: bytes, hint_name: str,
                     looks_like_zip: bool = True) -> Path:
    """Extract downloaded bytes into a fresh temp dir; return the dir.

    For zip: unzip everything. For raw SKILL.md: write a single file +
    treat the dir as a 1-file skill bundle.
    """
    tmp = Path(tempfile.mkdtemp(prefix="tudou-skill-install-"))
    if looks_like_zip:
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                # zip safety: reject entries with absolute paths or ".." traversal
                for member in zf.namelist():
                    if member.startswith("/") or ".." in member.split("/"):
                        raise InstallFromUrlError(
                            f"unsafe zip entry: {member!r}"
                        )
                zf.extractall(tmp)
        except zipfile.BadZipFile:
            # Maybe the URL was a single SKILL.md with .zip extension
            if content[:5] == b"---\n" or b"---" in content[:100]:
                (tmp / "SKILL.md").write_bytes(content)
            else:
                shutil.rmtree(tmp, ignore_errors=True)
                raise InstallFromUrlError(
                    "downloaded file is neither valid zip nor SKILL.md"
                )
    else:
        # Raw SKILL.md — wrap in a skill dir
        (tmp / "SKILL.md").write_bytes(content)
    return tmp


def find_skill_root(extracted_dir: Path) -> Path:
    """A zip may put the skill at the top level OR inside a single
    wrapper directory. Locate the dir that actually contains SKILL.md."""
    # Top level
    if (extracted_dir / "SKILL.md").exists():
        return extracted_dir
    # Case-insensitive top-level scan
    for child in extracted_dir.iterdir():
        if child.is_file() and child.name.lower() == "skill.md":
            return extracted_dir
    # Single subdir wrapper
    children = [c for c in extracted_dir.iterdir() if c.is_dir()]
    if len(children) == 1:
        sub = children[0]
        if (sub / "SKILL.md").exists() or any(
            f.name.lower() == "skill.md" for f in sub.iterdir() if f.is_file()
        ):
            return sub
    raise InstallFromUrlError(
        f"no SKILL.md found in downloaded archive (extracted to {extracted_dir})"
    )


# ──────────────────────────────────────────────────────────────────────
# Slug sanitization for catalog folder name
# ──────────────────────────────────────────────────────────────────────


_SLUG_SAFE_RE = re.compile(r"[^a-z0-9-]+")


def safe_folder_name(name_or_slug: str, fallback: str = "imported-skill") -> str:
    """Turn a skill name/slug into a filesystem-safe folder name. Lowercase,
    strip non-[a-z0-9-], collapse runs of '-'. ClawHub allows fancy names
    like ``Word / DOCX`` so this matters."""
    s = (name_or_slug or "").strip().lower()
    s = _SLUG_SAFE_RE.sub("-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or fallback


# ──────────────────────────────────────────────────────────────────────
# Top-level entry point
# ──────────────────────────────────────────────────────────────────────


def install_skill_from_url(
    url_or_slug: str,
    *,
    catalog_dir: str,
    skill_registry,
    skill_store=None,
    installed_by: str = "",
    overwrite: bool = False,
    progress_id: str | None = None,
) -> dict:
    """Download + extract + install a remote SKILL.md-style skill.

    Pipeline:
      1. Resolve URL → download URL
      2. Download zip / SKILL.md bytes
      3. Extract to temp dir, locate the skill root
      4. Copy into ``<catalog_dir>/imported/<slug>/`` (so SkillStore picks it up)
      5. Call ``skill_registry.install_from_directory(<target>)`` so it
         becomes an installed/grantable skill
      6. If ``skill_store`` provided, re-scan it so the new entry appears
         in the marketplace listing

    Args:
        url_or_slug: ClawHub URL, ``author/slug``, ``.zip`` URL, or raw
            ``SKILL.md`` URL
        catalog_dir: filesystem path to the user catalog directory
            (typically ``<data_dir>/skill_catalog``)
        skill_registry: SkillRegistry instance (engine) — must expose
            ``install_from_directory(src_dir, installed_by) -> SkillInstall``
        skill_store: optional SkillStore — if provided, ``rescan()`` is called
        installed_by: actor name for audit trail
        overwrite: if a folder with the same slug already exists in the
            catalog dir, replace it. False (default) refuses re-install
            with a clear error.

    Returns dict:
        {
          "ok": True,
          "source_url": <input>,
          "download_url": <resolved>,
          "skill_id": <manifest.id>,           # e.g. "word-docx@1.0.2"
          "name": <manifest.name>,
          "version": <manifest.version>,
          "catalog_path": <copied to>,         # filesystem path
          "installed": True,                    # engine registered
        }

    Raises ``InstallFromUrlError`` with a specific message at any step.
    """
    if not catalog_dir:
        raise InstallFromUrlError("catalog_dir is required")
    if not skill_registry:
        raise InstallFromUrlError("skill_registry is required")

    # Helper to report progress (no-op when progress_id is None)
    def _progress(phase: str, message: str, pct: int) -> None:
        if not progress_id:
            return
        try:
            from . import install_progress as _ip
            _ip.update(progress_id, phase=phase, message=message, progress_pct=pct)
        except Exception:
            pass

    # 1. Resolve
    _progress("resolve", f"解析 URL: {url_or_slug}", 5)
    download_url, hint_name = resolve_download_url(url_or_slug)
    logger.info("install_from_url: source=%s download=%s hint=%s",
                url_or_slug, download_url, hint_name)

    # 2. Download
    _progress("download", f"下载中: {download_url[:80]}", 15)
    content = fetch_url_binary(download_url)
    if not content:
        raise InstallFromUrlError("downloaded 0 bytes")
    _progress("download", f"下载完成: {len(content)} 字节", 35)

    # 3. Extract + locate skill root
    _progress("extract", "解压 + 定位 SKILL.md", 45)
    looks_like_zip = (
        content[:2] == b"PK"  # ZIP magic
        or download_url.lower().endswith(".zip")
        or "convex.site" in download_url   # ClawHub API returns zip
    )
    extracted = extract_to_temp(
        content, hint_name, looks_like_zip=looks_like_zip,
    )
    try:
        skill_root = find_skill_root(extracted)

        # Pre-flight: parse SKILL.md frontmatter so we can name the folder
        # using the skill's own slug/name rather than the URL hint.
        from .engine import _read_skill_md_frontmatter
        skill_md_path = skill_root / "SKILL.md"
        if not skill_md_path.exists():
            # case-insensitive recovery
            for f in skill_root.iterdir():
                if f.is_file() and f.name.lower() == "skill.md":
                    skill_md_path = f
                    break
        fm = _read_skill_md_frontmatter(str(skill_md_path)) if skill_md_path.exists() else {}
        slug = (
            str(fm.get("slug") or fm.get("name") or hint_name).strip()
        )
        target_folder = safe_folder_name(slug, fallback=safe_folder_name(hint_name))

        # 4. Copy into catalog dir
        catalog_root = Path(catalog_dir).expanduser().resolve()
        catalog_root.mkdir(parents=True, exist_ok=True)
        target_dir = catalog_root / "imported" / target_folder
        target_dir.parent.mkdir(parents=True, exist_ok=True)

        if target_dir.exists():
            if not overwrite:
                raise InstallFromUrlError(
                    f"skill already exists at {target_dir} — pass overwrite=True to replace"
                )
            shutil.rmtree(target_dir)

        _progress("copy", f"复制到 catalog: {target_folder}", 60)
        shutil.copytree(skill_root, target_dir)

        # Make copied files writable in case the source archive set
        # restrictive perms.
        for f in target_dir.rglob("*"):
            try:
                f.chmod(0o644 if f.is_file() else 0o755)
            except Exception:
                pass

        # Drop a sidecar so we know where this came from
        try:
            import json
            import time
            (target_dir / ".tudou_install.json").write_text(
                json.dumps({
                    "source": url_or_slug,
                    "download_url": download_url,
                    "installed_by": installed_by,
                    "installed_at": time.time(),
                }, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

        # 5. Register with engine (this is what makes it grantable to agents)
        _progress("install", "注册到 engine(校验 + leak check)", 75)
        try:
            inst = skill_registry.install_from_directory(
                str(target_dir), installed_by=installed_by or "url-install",
            )
        except ValueError as e:
            # "already installed" — common when re-fetching same skill.
            # The error message is i18n'd so we have to match en + zh + the
            # raw key. Use install_or_upgrade_from_directory to recover the
            # existing install rather than failing.
            err_msg = str(e)
            already_installed = (
                "already_installed" in err_msg
                or "already installed" in err_msg.lower()
                or "已安装" in err_msg  # zh-CN: "技能已安装"
            )
            if already_installed:
                logger.info(
                    "skill %s already installed (engine); recovering via "
                    "install_or_upgrade_from_directory", target_folder,
                )
                try:
                    inst = skill_registry.install_or_upgrade_from_directory(
                        str(target_dir),
                        installed_by=installed_by or "url-install",
                    )
                except Exception as _re:
                    # Couldn't upgrade either — fall back to "found by name"
                    # so caller still gets the manifest info.
                    logger.warning(
                        "install_or_upgrade fallback failed: %s — "
                        "looking up existing install by name", _re,
                    )
                    inst = None
                    for _sid, _existing in (
                        getattr(skill_registry, "_installs", {}) or {}
                    ).items():
                        m = getattr(_existing, "manifest", None)
                        if m and m.name == target_folder:
                            inst = _existing
                            break
            else:
                raise InstallFromUrlError(
                    f"engine registration failed: {e}"
                ) from e
        except Exception as e:
            raise InstallFromUrlError(
                f"engine registration failed: {e}"
            ) from e

        # 6. Re-scan store so catalog list reflects the new entry
        _progress("rescan", "刷新 catalog 列表", 90)
        if skill_store is not None:
            try:
                skill_store.scan(force=True)
            except TypeError:
                try:
                    skill_store.scan()
                except Exception as e:
                    logger.warning("skill_store re-scan failed (non-fatal): %s", e)
            except Exception as e:
                logger.warning("skill_store re-scan failed (non-fatal): %s", e)

        result = {
            "ok": True,
            "source_url": url_or_slug,
            "download_url": download_url,
            "name": (inst.manifest.name if inst else slug),
            "version": (inst.manifest.version if inst else (fm.get("version") or "1.0.0")),
            "skill_id": (inst.id if inst else f"{slug}@{fm.get('version','1.0.0')}"),
            "catalog_path": str(target_dir),
            "installed": inst is not None,
        }
        logger.info("install_from_url OK: %s -> %s",
                    url_or_slug, result["skill_id"])
        return result
    finally:
        # Always clean up temp dir
        try:
            shutil.rmtree(extracted, ignore_errors=True)
        except Exception:
            pass


__all__ = [
    "InstallFromUrlError",
    "resolve_download_url",
    "fetch_url_binary",
    "extract_to_temp",
    "find_skill_root",
    "safe_folder_name",
    "install_skill_from_url",
]
