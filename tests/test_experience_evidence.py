"""Sprint 3.2: experience evidence references.

Covers:
  - Experience.evidence field round-trips through to_dict / from_dict
  - Backward compat: old records without 'evidence' default to []
  - to_prompt_text includes citations when present
  - _tool_save_experience normalizes (strip + dedup + order-preserve)
"""
from __future__ import annotations

from app.experience_library import Experience, ExperienceLibrary
from app.tools_split.knowledge import _tool_save_experience
from app import experience_library as _explib_mod


def test_evidence_defaults_to_empty():
    exp = Experience(scene="demo", core_knowledge="kw")
    assert exp.evidence == []


def test_evidence_roundtrips_through_dict():
    exp = Experience(
        id="DEMO-1",
        scene="testing",
        core_knowledge="something",
        evidence=["app/tools.py:42", "docs/SPEC.md#auth"],
    )
    d = exp.to_dict()
    assert d["evidence"] == ["app/tools.py:42", "docs/SPEC.md#auth"]
    restored = Experience.from_dict(d)
    assert restored.evidence == exp.evidence


def test_from_dict_without_evidence_key_gets_empty_list():
    """Backward-compat: old persisted experiences don't have the
    'evidence' field in their JSON blob. Must still load."""
    old_style = {
        "id": "LEGACY-1",
        "scene": "old entry",
        "core_knowledge": "still useful",
        # no "evidence" key
    }
    exp = Experience.from_dict(old_style)
    assert exp.evidence == []


def test_prompt_text_omits_evidence_when_empty():
    exp = Experience(id="DEMO-2", scene="s", core_knowledge="k")
    text = exp.to_prompt_text()
    assert "依据" not in text  # no section header when list is empty


def test_prompt_text_includes_evidence_when_present():
    exp = Experience(
        id="DEMO-3", scene="s", core_knowledge="k",
        evidence=["a.py:10", "b.md#x"],
    )
    text = exp.to_prompt_text()
    assert "依据" in text
    assert "a.py:10" in text
    assert "b.md#x" in text


def test_prompt_text_caps_long_evidence_list():
    """With >5 references, show 5 + a "+N more" suffix. Keeps the prompt
    footprint bounded when an experience cites many sources."""
    exp = Experience(
        id="DEMO-4", scene="s", core_knowledge="k",
        evidence=[f"file{i}.py:{i*10}" for i in range(10)],
    )
    text = exp.to_prompt_text()
    # First 5 appear, last 5 don't.
    assert "file0.py:0" in text
    assert "file4.py:40" in text
    assert "file9.py:90" not in text
    assert "+5 more" in text


# ── tool handler normalization ───────────────────────────────────────

def _isolate_library(tmp_path, monkeypatch) -> ExperienceLibrary:
    """Make the global library point at an empty tmpdir for this test.

    Also blocks the legacy-migration path — the production init copies
    `app/data/experience/` into the new home if it exists, which would
    pollute the tmpdir with every pre-existing experience.
    """
    monkeypatch.setattr(_explib_mod, "_global_library", None)
    isolated_root = tmp_path / ".tudou_claw"
    lib = ExperienceLibrary(data_dir=str(isolated_root / "experience"))
    # Force get_experience_library() to return THIS instance.
    monkeypatch.setattr(_explib_mod, "_global_library", lib)
    return lib


def _save_and_get_latest(
    lib: ExperienceLibrary,
    **kwargs,
) -> Experience:
    """Call _tool_save_experience against the isolated library, return
    the experience just added (matched by created_at ~= now).

    Using add-time match rather than len==1 because tests share the
    process's Experience library cache in some CI environments; we
    just need to confirm OUR save survived intact.
    """
    before_ids = {e.id for e in lib.get_all_experiences("default")}
    result = _tool_save_experience(**kwargs)
    assert "Experience saved" in result, result
    after = lib.get_all_experiences("default")
    added = [e for e in after if e.id not in before_ids]
    assert len(added) == 1, (
        f"Expected exactly one new experience, got {len(added)}; "
        f"returned message was: {result}"
    )
    return added[0]


def test_save_experience_strips_and_dedups_evidence(tmp_path, monkeypatch):
    """Whitespace stripping, empty-string dropping, dedup preserves order."""
    lib = _isolate_library(tmp_path, monkeypatch)
    exp = _save_and_get_latest(
        lib,
        scene="s", core_knowledge="k",
        evidence=[
            "a.py:1",
            "  b.py:2  ",       # leading/trailing space
            "",                  # empty - drop
            "a.py:1",            # dup
            "c.py:3",
            "   ",               # whitespace-only - drop
        ],
    )
    assert exp.evidence == ["a.py:1", "b.py:2", "c.py:3"]


def test_save_experience_without_evidence_still_works(tmp_path, monkeypatch):
    """Evidence is optional — older callers shouldn't break."""
    lib = _isolate_library(tmp_path, monkeypatch)
    exp = _save_and_get_latest(lib, scene="s", core_knowledge="k")
    assert exp.evidence == []


# ── schema ───────────────────────────────────────────────────────────

def test_save_experience_schema_declares_evidence():
    from app import tools
    schema = next(
        (d for d in tools.TOOL_DEFINITIONS
         if d["function"]["name"] == "save_experience"),
        None,
    )
    assert schema is not None
    props = schema["function"]["parameters"]["properties"]
    assert "evidence" in props
    assert props["evidence"]["type"] == "array"
