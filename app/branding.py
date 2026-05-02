"""
Branding store — site name + logo, persisted per-deployment.

Single TudouClaw deployment = one company (per user direction
2026-05-02; multi-tenancy is out of scope). So branding is a single
JSON file under ``<data_dir>/branding.json``, not per-tenant.

Default values keep the original "Tudou Claws" experience intact so
fresh installs don't suddenly look unbranded. Admin can replace via
the Settings → 品牌 tab.

Schema:

    {
      "site_name": "Tudou Claws",     # text in the header H1
      "site_subtitle": "Admin Console", # small text below the logo
      "logo_url": "",                  # optional image URL; empty = use built-in icon
      "updated_at": 1777...
    }
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path

logger = logging.getLogger("tudou.branding")


DEFAULTS = {
    "site_name": "Tudou Claws",
    "site_subtitle": "Admin Console",
    "logo_url": "",
}


class BrandingStore:
    """Read-mostly JSON file with single write lock."""

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self._path = self.data_dir / "branding.json"
        self._lock = threading.Lock()
        self._cache: dict | None = None

    def _load_unlocked(self) -> dict:
        if self._cache is not None:
            return self._cache
        if not self._path.exists():
            self._cache = dict(DEFAULTS)
            return self._cache
        try:
            d = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(d, dict):
                d = {}
        except Exception as e:
            logger.warning("branding.json read failed: %s — using defaults", e)
            d = {}
        # Merge with defaults so missing keys fall back gracefully
        merged = dict(DEFAULTS)
        merged.update({k: v for k, v in d.items() if k in DEFAULTS or k == "updated_at"})
        self._cache = merged
        return merged

    def get(self) -> dict:
        """Return current branding (always succeeds — falls back to defaults)."""
        with self._lock:
            return dict(self._load_unlocked())

    def update(self, patch: dict) -> dict:
        """Apply a partial update. Only DEFAULTS keys are persisted —
        unknown keys silently ignored (defends against API misuse)."""
        with self._lock:
            current = dict(self._load_unlocked())
            for k, v in (patch or {}).items():
                if k not in DEFAULTS:
                    continue   # silently drop unknown keys
                # Empty string / None clears the field back to its default,
                # even though "" technically passes isinstance(v, str).
                if v is None or v == "":
                    current[k] = DEFAULTS[k]
                elif isinstance(v, type(DEFAULTS[k])):
                    current[k] = v
                # else: type mismatch — silently drop (defensive)
            current["updated_at"] = time.time()
            self.data_dir.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(current, ensure_ascii=False, indent=2),
                           encoding="utf-8")
            os.replace(tmp, self._path)
            self._cache = current
            return dict(current)

    def reset(self) -> dict:
        """Remove customizations, restore defaults."""
        with self._lock:
            current = dict(DEFAULTS)
            current["updated_at"] = time.time()
            try:
                if self._path.exists():
                    self._path.unlink()
            except OSError as e:
                logger.warning("branding.json delete failed: %s", e)
            self._cache = current
            return current


# ── Module-level singleton (matches other store patterns) ──────────


_STORE: BrandingStore | None = None
_STORE_LOCK = threading.Lock()


def init_store(data_dir: str | Path) -> BrandingStore:
    global _STORE
    with _STORE_LOCK:
        if _STORE is None:
            _STORE = BrandingStore(data_dir)
    return _STORE


def get_store() -> BrandingStore | None:
    return _STORE
