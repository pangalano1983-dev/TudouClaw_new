"""
i18n 国际化模块。

设计目标:
- 所有面向用户的字符串（错误消息、提示、UI 标签）通过 t(key) 取
- 不在代码中硬编码任何用户可见文本
- locale 文件外置 (app/locales/*.yaml)，运行时热加载
- 支持参数插值: t("skills.installed", name="send_email")
- 缺失 key 自动 fallback: 当前 locale → 默认 locale (zh-CN) → key 本身
- 支持嵌套 key: "skills.errors.not_found"
- 前端可通过 GET /api/portal/i18n/<locale> 取整个 locale 表

用法:
    from .i18n import t, set_locale, get_locale
    msg = t("skills.installed", name="send_email")
    set_locale("en")
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

logger = logging.getLogger("tudou.i18n")

DEFAULT_LOCALE = "zh-CN"
FALLBACK_LOCALE = "zh-CN"

_LOCK = threading.RLock()
_LOCALES: dict[str, dict] = {}        # locale -> dict tree
_CURRENT_LOCALE = DEFAULT_LOCALE
_LOCALE_DIR: Path | None = None
_LOADED = False


def _resolve_locale_dir() -> Path:
    global _LOCALE_DIR
    if _LOCALE_DIR is not None:
        return _LOCALE_DIR
    here = Path(__file__).parent
    _LOCALE_DIR = here / "locales"
    return _LOCALE_DIR


def _load_locale_file(locale: str) -> dict:
    """加载单个 locale 文件，返回 nested dict。"""
    if yaml is None:
        logger.warning("PyYAML not installed; i18n falling back to keys")
        return {}
    fp = _resolve_locale_dir() / f"{locale}.yaml"
    if not fp.exists():
        logger.debug("Locale file not found: %s", fp)
        return {}
    try:
        with open(fp, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.error("Failed to load locale %s: %s", locale, e)
        return {}


def reload_locales() -> None:
    """重新加载所有 locale 文件。"""
    global _LOADED
    with _LOCK:
        _LOCALES.clear()
        d = _resolve_locale_dir()
        if d.exists():
            for fp in d.glob("*.yaml"):
                locale = fp.stem
                _LOCALES[locale] = _load_locale_file(locale)
                logger.debug("Loaded locale %s with %d top keys",
                             locale, len(_LOCALES[locale]))
        _LOADED = True


def _ensure_loaded() -> None:
    if not _LOADED:
        reload_locales()


def list_locales() -> list[str]:
    _ensure_loaded()
    return sorted(_LOCALES.keys())


def get_locale() -> str:
    return _CURRENT_LOCALE


def set_locale(locale: str) -> None:
    global _CURRENT_LOCALE
    _ensure_loaded()
    if locale in _LOCALES:
        _CURRENT_LOCALE = locale
    else:
        logger.warning("Locale %s not loaded, keeping %s",
                       locale, _CURRENT_LOCALE)


def _lookup(table: dict, key: str):
    """支持点号分隔的 nested key 查找。"""
    parts = key.split(".")
    node = table
    for p in parts:
        if not isinstance(node, dict) or p not in node:
            return None
        node = node[p]
    return node


def t(key: str, locale: str | None = None, **vars) -> str:
    """
    翻译函数。

    Args:
        key: 点号分隔的 key 路径，如 "skills.errors.not_found"
        locale: 指定 locale，None 则用当前 locale
        **vars: 插值变量

    Returns:
        翻译后的字符串。如果 key 不存在，返回 key 本身（便于发现遗漏）。
    """
    _ensure_loaded()
    use = locale or _CURRENT_LOCALE

    val = None
    if use in _LOCALES:
        val = _lookup(_LOCALES[use], key)
    if val is None and use != FALLBACK_LOCALE and FALLBACK_LOCALE in _LOCALES:
        val = _lookup(_LOCALES[FALLBACK_LOCALE], key)
    if val is None:
        return key  # 兜底：返回 key 本身，方便发现未翻译

    if not isinstance(val, str):
        return str(val)

    if vars:
        try:
            return val.format(**vars)
        except (KeyError, IndexError) as e:
            logger.debug("i18n format error for %s: %s", key, e)
            return val
    return val


def get_locale_table(locale: str | None = None) -> dict:
    """返回某个 locale 的完整 dict（用于前端拉取）。"""
    _ensure_loaded()
    use = locale or _CURRENT_LOCALE
    return _LOCALES.get(use, {})
