"""Tests for app.paths — single source of truth for the data dir.

Verifies the env-var resolution rules and that downstream modules pick
up the override. See ``docs/data-dir-config.md`` for the full ruleset.
"""

from __future__ import annotations

from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Resolution rules
# ---------------------------------------------------------------------------


def test_default_is_home_tudou_claw(monkeypatch):
    """No env var → ~/.tudou_claw."""
    monkeypatch.delenv("TUDOU_CLAW_DATA_DIR", raising=False)
    monkeypatch.delenv("TUDOU_CLAW_HOME", raising=False)
    from app.paths import data_dir

    result = data_dir()
    assert result == Path.home() / ".tudou_claw"


def test_canonical_var_wins(monkeypatch, tmp_path):
    """TUDOU_CLAW_DATA_DIR is the canonical override."""
    monkeypatch.setenv("TUDOU_CLAW_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("TUDOU_CLAW_HOME", raising=False)
    from app.paths import data_dir

    assert data_dir() == tmp_path.resolve()


def test_legacy_var_falls_back(monkeypatch, tmp_path):
    """TUDOU_CLAW_HOME still works (legacy alias)."""
    monkeypatch.delenv("TUDOU_CLAW_DATA_DIR", raising=False)
    monkeypatch.setenv("TUDOU_CLAW_HOME", str(tmp_path))
    from app.paths import data_dir

    assert data_dir() == tmp_path.resolve()


def test_canonical_beats_legacy(monkeypatch, tmp_path):
    """When both set, canonical wins."""
    canonical = tmp_path / "canonical"
    legacy = tmp_path / "legacy"
    canonical.mkdir()
    legacy.mkdir()
    monkeypatch.setenv("TUDOU_CLAW_DATA_DIR", str(canonical))
    monkeypatch.setenv("TUDOU_CLAW_HOME", str(legacy))
    from app.paths import data_dir

    assert data_dir() == canonical.resolve()


def test_empty_string_treated_as_unset(monkeypatch):
    """Empty string env vars should not override default."""
    monkeypatch.setenv("TUDOU_CLAW_DATA_DIR", "")
    monkeypatch.setenv("TUDOU_CLAW_HOME", "")
    from app.paths import data_dir

    result = data_dir()
    assert result == Path.home() / ".tudou_claw"


def test_tilde_expanded(monkeypatch):
    """A path with ~ should be expanded to the user home."""
    monkeypatch.setenv("TUDOU_CLAW_DATA_DIR", "~/test-tudou")
    monkeypatch.delenv("TUDOU_CLAW_HOME", raising=False)
    from app.paths import data_dir

    assert data_dir() == (Path.home() / "test-tudou").resolve()


def test_no_disk_write(monkeypatch, tmp_path):
    """data_dir() should NOT create the directory on disk."""
    target = tmp_path / "absent"
    monkeypatch.setenv("TUDOU_CLAW_DATA_DIR", str(target))
    monkeypatch.delenv("TUDOU_CLAW_HOME", raising=False)
    from app.paths import data_dir

    result = data_dir()
    assert result == target.resolve()
    assert not target.exists(), "data_dir() must not create the directory"


# ---------------------------------------------------------------------------
# Downstream modules pick up the override
# ---------------------------------------------------------------------------


def test_rag_provider_paths_follow_env(monkeypatch, tmp_path):
    """Switching the env var redirects rag_providers.json + domain KB."""
    monkeypatch.setenv("TUDOU_CLAW_DATA_DIR", str(tmp_path))
    from app.rag_provider import _providers_file, _domain_kb_file

    assert _providers_file() == tmp_path.resolve() / "rag_providers.json"
    assert _domain_kb_file() == tmp_path.resolve() / "domain_knowledge_bases.json"


def test_checkpoint_db_path_follows_env(monkeypatch, tmp_path):
    """checkpoint._default_db_path tracks the env var."""
    monkeypatch.setenv("TUDOU_CLAW_DATA_DIR", str(tmp_path))
    from app.checkpoint import _default_db_path

    assert _default_db_path() == str(tmp_path.resolve() / "checkpoints.db")


def test_llm_tier_router_persist_path_follows_env(monkeypatch, tmp_path):
    """LLMTierRouter() default persist path tracks the env var."""
    monkeypatch.setenv("TUDOU_CLAW_DATA_DIR", str(tmp_path))
    from app.llm_tier_routing import LLMTierRouter

    router = LLMTierRouter()
    assert router._persist_path == str(tmp_path.resolve() / "llm_tiers.json")


def test_explicit_path_wins_over_env(monkeypatch, tmp_path):
    """Caller-supplied path always overrides the env-var default."""
    monkeypatch.setenv("TUDOU_CLAW_DATA_DIR", str(tmp_path))
    from app.llm_tier_routing import LLMTierRouter

    explicit = "/tmp/custom_tiers.json"
    router = LLMTierRouter(persist_path=explicit)
    assert router._persist_path == explicit


# ---------------------------------------------------------------------------
# Backward compat: existing default flow still works
# ---------------------------------------------------------------------------


def test_no_env_default_lookup(monkeypatch):
    """No env var → all downstreams use ~/.tudou_claw subpaths."""
    monkeypatch.delenv("TUDOU_CLAW_DATA_DIR", raising=False)
    monkeypatch.delenv("TUDOU_CLAW_HOME", raising=False)
    expected_root = Path.home() / ".tudou_claw"

    from app.paths import data_dir
    from app.rag_provider import _providers_file
    from app.checkpoint import _default_db_path

    assert data_dir() == expected_root
    assert _providers_file() == expected_root / "rag_providers.json"
    assert _default_db_path() == str(expected_root / "checkpoints.db")
