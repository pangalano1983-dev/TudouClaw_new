"""Parity lint: zh.js and en.js must define the same key set.

Missing keys on either side cause silent UX regressions — labels
revert to Chinese on the English UI, or show the raw dot-key
("nav.agents") as text. This test fails CI any time the key sets
diverge so translators notice immediately.
"""
from __future__ import annotations

import os
import re
import pathlib


_ROOT = pathlib.Path(__file__).resolve().parent.parent
ZH = _ROOT / "app/server/static/js/i18n/zh.js"
EN = _ROOT / "app/server/static/js/i18n/en.js"


def _extract_keys(path: pathlib.Path) -> set[str]:
    """Pull out dictionary keys from the JS object literal.

    Matches lines like:  "nav.dashboard":   "工作台",
    Ignores inline // comments. JS is not parsed — we look for
    key: string pairs which is all these files contain.
    """
    src = path.read_text(encoding="utf-8")
    # Strip line comments so regex doesn't match commented-out pairs
    src = re.sub(r"//[^\n]*", "", src)
    pat = re.compile(r'"([^"]+)"\s*:\s*"', re.MULTILINE)
    return set(pat.findall(src))


def test_zh_and_en_have_identical_key_sets():
    zh = _extract_keys(ZH)
    en = _extract_keys(EN)
    assert zh, "zh.js extracted zero keys — check parser vs file syntax"
    assert en, "en.js extracted zero keys — check parser vs file syntax"
    missing_in_en = zh - en
    missing_in_zh = en - zh
    msg = []
    if missing_in_en:
        msg.append("Keys in zh.js but MISSING from en.js:")
        for k in sorted(missing_in_en):
            msg.append(f"  - {k}")
    if missing_in_zh:
        msg.append("Keys in en.js but MISSING from zh.js:")
        for k in sorted(missing_in_zh):
            msg.append(f"  - {k}")
    assert not (missing_in_en or missing_in_zh), "\n".join(msg)


def test_i18n_files_loaded_before_bundle():
    """portal.html MUST load zh.js + en.js before portal_bundle.js,
    otherwise window.t() is undefined at boot and labels fall back
    to raw HTML defaults (all Chinese, never switching)."""
    html = (_ROOT / "app/templates/portal.html").read_text(encoding="utf-8")
    idx_zh = html.find("/static/js/i18n/zh.js")
    idx_en = html.find("/static/js/i18n/en.js")
    idx_bundle = html.find("/static/js/portal_bundle.js")
    assert idx_zh > 0, "zh.js not loaded by portal.html"
    assert idx_en > 0, "en.js not loaded by portal.html"
    assert idx_bundle > 0, "portal_bundle.js not found in portal.html"
    assert idx_zh < idx_bundle, "zh.js must precede portal_bundle.js"
    assert idx_en < idx_bundle, "en.js must precede portal_bundle.js"


def test_boot_script_preloads_lang_attr():
    """The inline <head> script must stamp data-lang on <html>
    BEFORE portal_bundle.js runs, so localStorage preference is
    honored on first paint (no flash of Chinese on an EN session)."""
    html = (_ROOT / "app/templates/portal.html").read_text(encoding="utf-8")
    boot_section_start = html.find("Applied BEFORE body renders")
    assert boot_section_start > 0, "boot preloader script missing"
    # The next 1KB should reference tudou_lang AND set data-lang
    snippet = html[boot_section_start:boot_section_start + 2000]
    assert "tudou_lang" in snippet, "boot script doesn't read tudou_lang"
    assert "data-lang" in snippet, "boot script doesn't stamp data-lang"


def test_lang_toggle_button_present():
    """Top-bar language toggle must be present and wired to _toggleLang."""
    html = (_ROOT / "app/templates/portal.html").read_text(encoding="utf-8")
    assert 'id="global-lang-btn"' in html
    assert '_toggleLang()' in html
    assert 'id="global-lang-label"' in html


def test_core_i18n_functions_defined():
    """Critical runtime functions must be present in portal_bundle.js."""
    js = (_ROOT / "app/server/static/js/portal_bundle.js").read_text(
        encoding="utf-8")
    for sym in ("window.t", "_applyI18nToDom", "_toggleLang",
                "_applyLangButtonStyle", "window._currentLang"):
        assert sym in js, f"{sym} missing from portal_bundle.js"


def test_required_high_frequency_keys_exist():
    """Guard: the 8 highest-traffic UI strings must never disappear."""
    zh = _extract_keys(ZH)
    required = {
        "nav.dashboard", "nav.agents", "nav.knowledge",
        "chat.soul", "chat.think", "chat.rag", "chat.wake",
        "chat.placeholder", "chat.thinking",
        "theme.dark", "theme.light", "lang.switch",
        "user.logout",
        "action.save", "action.cancel",
    }
    missing = required - zh
    assert not missing, f"high-frequency keys dropped from zh.js: {missing}"
