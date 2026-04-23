"""新 A.8 addendum — filter memory_refs to those actually used in the reply.

The UI 🧠 badge only makes sense when the agent's final answer genuinely
consumed a memory entry. Recalling but not using (e.g., memory was
irrelevant, agent searched fresh instead) should NOT surface the button.
"""
from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


from app.agent import Agent  # noqa: E402


def _ref(preview: str, rid: str = "m1") -> dict:
    return {
        "id": rid, "category": "outcome",
        "content_preview": preview,
        "confidence": 0.9, "age_days": 2, "source": "seed",
    }


# ── trivial guards ─────────────────────────────────────────────────


def test_empty_refs_returns_empty():
    out = Agent._filter_memory_refs_by_usage(
        [], "Some long final assistant reply content here.")
    assert out == []


def test_empty_final_content_returns_empty():
    refs = [_ref("project uses pytest for testing")]
    assert Agent._filter_memory_refs_by_usage(refs, "") == []


def test_short_final_content_returns_empty():
    """Short replies (< 30 chars) are almost always tool-call
    acknowledgments, not real answers — don't flag them."""
    refs = [_ref("pytest is the test runner")]
    assert Agent._filter_memory_refs_by_usage(refs, "ok") == []
    assert Agent._filter_memory_refs_by_usage(refs, "好的，收到") == []


# ── positive / negative cases ──────────────────────────────────────


def test_refs_used_by_final_reply_are_kept():
    refs = [_ref("The project uses pytest with fixtures in conftest.py")]
    final = (
        "Based on what I remember, this project uses pytest with fixtures "
        "defined in conftest.py. Here's how the tests are organized..."
    )
    kept = Agent._filter_memory_refs_by_usage(refs, final)
    assert len(kept) == 1
    assert "used_similarity" in kept[0]
    assert "matched_tokens" in kept[0]
    assert "pytest" in kept[0]["matched_tokens"]


def test_unrelated_memory_is_filtered_out():
    refs = [_ref("Deploy uses Kubernetes with GitOps")]
    final = (
        "Let me check the package.json to understand the frontend "
        "dependencies — I'll look for common UI libraries there."
    )
    kept = Agent._filter_memory_refs_by_usage(refs, final)
    assert kept == []


def test_mixed_refs_keeps_only_used_ones():
    refs = [
        _ref("pytest is the test framework", rid="m-pytest"),
        _ref("deploy pipeline is Github Actions", rid="m-deploy"),
        _ref("the user prefers Markdown over RST", rid="m-md"),
    ]
    final = (
        "The testing approach here uses pytest. For the specific case "
        "you asked about, configure fixtures in conftest.py. Tests live "
        "under the tests/ directory."
    )
    kept = Agent._filter_memory_refs_by_usage(refs, final)
    kept_ids = {r["id"] for r in kept}
    assert "m-pytest" in kept_ids
    assert "m-deploy" not in kept_ids
    assert "m-md" not in kept_ids


def test_similarity_score_attached_to_kept_refs():
    refs = [_ref("terraform apply blocked in production")]
    final = ("We've blocked terraform apply for production environments "
             "because the risk of accidental destruction is too high.")
    kept = Agent._filter_memory_refs_by_usage(refs, final)
    assert len(kept) == 1
    assert isinstance(kept[0]["used_similarity"], float)
    assert 0.0 <= kept[0]["used_similarity"] <= 1.0


def test_mutation_free():
    refs = [_ref("anything"), _ref("anything else", rid="m2")]
    import copy
    snap = copy.deepcopy(refs)
    _ = Agent._filter_memory_refs_by_usage(refs, "X" * 100)
    assert refs == snap


def test_missing_content_preview_field_is_skipped():
    refs = [{"id": "m1", "category": "outcome"}]  # no content_preview
    final = "Some answer about the project's architecture and conventions."
    # No preview → can't measure overlap → filtered out.
    assert Agent._filter_memory_refs_by_usage(refs, final) == []
