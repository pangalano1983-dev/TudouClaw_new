"""Regression for RAG provider ghost-entry filter.

The original bug: POSTing an empty body to /api/portal/rag/providers
(or calling RAGProviderRegistry.register with all defaults) accumulated
one 'ghost' entry per call — empty name, empty URL, kind=remote. On
the user's machine this grew to 59 unused entries. After fix:
  - register() raises ValueError when name+url are both empty on a
    remote provider
  - _ensure_loaded() skips ghost rows already on disk

Tests isolate via a tmp providers file — never touches the user's
real ~/.tudou_claw/rag_providers.json.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import rag_provider
from app.rag_provider import RAGProviderEntry, RAGProviderRegistry


@pytest.fixture
def isolated_registry(tmp_path, monkeypatch):
    """Point the registry module's _PROVIDERS_FILE at tmp and return a
    fresh registry instance. Real file is never touched."""
    fake_file = tmp_path / "rag_providers.json"
    monkeypatch.setattr(rag_provider, "_PROVIDERS_FILE", fake_file)
    monkeypatch.setattr(rag_provider, "_DATA_DIR", tmp_path)
    reg = RAGProviderRegistry()
    # Return both so tests can also inspect the backing file.
    return reg, fake_file


def test_register_rejects_ghost_remote(isolated_registry):
    reg, _ = isolated_registry
    with pytest.raises(ValueError, match="requires name or base_url"):
        reg.register(name="", kind="remote", base_url="")


def test_register_accepts_remote_with_name_only(isolated_registry):
    reg, _ = isolated_registry
    p = reg.register(name="EmbeddingSvc", kind="remote", base_url="")
    assert p.name == "EmbeddingSvc"
    assert p.id  # some id was assigned


def test_register_accepts_remote_with_url_only(isolated_registry):
    reg, _ = isolated_registry
    p = reg.register(name="", kind="remote",
                     base_url="http://rag.example:8000")
    # base_url stripped of trailing slash if any; name can remain blank.
    assert p.base_url == "http://rag.example:8000"


def test_register_accepts_local_without_fields(isolated_registry):
    """Local providers don't need a URL — they use the builtin ChromaDB.
    Guard must not block that legitimate path."""
    reg, _ = isolated_registry
    p = reg.register(name="", kind="local", base_url="")
    assert p.kind == "local"


def test_load_skips_ghost_rows_on_disk(isolated_registry):
    """Simulate an older file that accumulated ghosts before the fix.
    The loader must silently drop them."""
    _, fake_file = isolated_registry
    fake_file.write_text(json.dumps([
        # 2 ghosts
        {"id": "ghost1", "name": "", "kind": "remote", "base_url": "",
         "api_key": "", "config": {}, "enabled": True, "created_at": 1.0},
        {"id": "ghost2", "name": "", "kind": "remote", "base_url": "",
         "api_key": "", "config": {}, "enabled": True, "created_at": 2.0},
        # 1 real
        {"id": "real1", "name": "EmbedHost", "kind": "remote",
         "base_url": "http://localhost:9000", "api_key": "",
         "config": {}, "enabled": True, "created_at": 3.0},
    ]))
    reg = RAGProviderRegistry()
    providers = reg.list_providers()
    assert len(providers) == 1
    assert providers[0].id == "real1"


def test_ghost_helper_does_not_flag_local_providers():
    """Local (builtin ChromaDB) providers may legitimately have empty
    name+url — they must not be filtered out."""
    p_local = RAGProviderEntry(id="x", kind="local", name="", base_url="")
    p_ghost = RAGProviderEntry(id="y", kind="remote", name="", base_url="")
    assert not RAGProviderRegistry._is_ghost(p_local)
    assert RAGProviderRegistry._is_ghost(p_ghost)


def test_ghost_helper_does_not_flag_remote_with_config():
    """If the user filled in any config key, the entry is intentional
    even without name/url."""
    p = RAGProviderEntry(
        id="x", kind="remote", name="", base_url="",
        config={"custom_flag": True},
    )
    assert not RAGProviderRegistry._is_ghost(p)
