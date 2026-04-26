"""app.prompt_blocks + app.system_prompt_v2 + app.prompt_block_catalog —
declarative system prompt assembly (Stage A).

Covers:
- BlockGate dimensions individually + AND combination
- PromptBlock render (str / callable / exception-safe)
- AssemblyContext factory + frozen semantics
- assemble_static_prompt sorting, inclusion, exclusion reasoning
- assemble_with_log doesn't crash + emits structured log
- diff_summary basic
- Default catalog: 3-scenario integration (casual / pptx / meeting)
"""
from __future__ import annotations

import logging

import pytest

from app.prompt_blocks import (
    Always,
    AssemblyContext,
    BlockAssemblyResult,
    BlockGate,
    PromptBlock,
)
from app.system_prompt_v2 import (
    assemble_static_prompt,
    assemble_with_log,
    diff_summary,
)
from app.prompt_block_catalog import (
    DEFAULT_BLOCKS,
    block_by_id,
    get_default_catalog,
)


# ── BlockGate ─────────────────────────────────────────────────────────


def _ctx(**overrides) -> AssemblyContext:
    base = dict(
        scope_tags=("casual_chat",),
        granted_tools=frozenset(),
        granted_skills=frozenset(),
        role_kind="general",
        ctx_type="solo",
        has_image=False,
        extras={},
    )
    base.update(overrides)
    return AssemblyContext(**base)


def test_always_gate_passes_anything():
    assert Always().matches(_ctx())


@pytest.mark.parametrize("scopes,ctx_scopes,expected", [
    ({"casual_chat"},          ("casual_chat",),  True),
    ({"casual_chat", "meeting"}, ("meeting",),    True),
    ({"meeting"},              ("casual_chat",),  False),
    ({"a"},                    (),                 False),
])
def test_gate_scopes_dimension(scopes, ctx_scopes, expected):
    g = BlockGate(scopes=scopes)
    assert g.matches(_ctx(scope_tags=ctx_scopes)) == expected


def test_gate_tools_dimension():
    g = BlockGate(has_tools_in={"write_file", "edit_file"})
    assert g.matches(_ctx(granted_tools=frozenset({"write_file"})))
    assert g.matches(_ctx(granted_tools=frozenset({"edit_file", "x"})))
    assert not g.matches(_ctx(granted_tools=frozenset({"send_email"})))
    assert not g.matches(_ctx(granted_tools=frozenset()))


def test_gate_skill_dimension():
    g = BlockGate(has_skill_in={"pptx-author", "video-forge"})
    assert g.matches(_ctx(granted_skills=frozenset({"pptx-author"})))
    assert not g.matches(_ctx(granted_skills=frozenset({"file-ops"})))


def test_gate_role_kind_dimension():
    g = BlockGate(role_kind_in={"coder", "analyst"})
    assert g.matches(_ctx(role_kind="coder"))
    assert g.matches(_ctx(role_kind="analyst"))
    assert not g.matches(_ctx(role_kind="pm"))


def test_gate_ctx_type_dimension():
    g = BlockGate(ctx_type_in={"project", "meeting"})
    assert g.matches(_ctx(ctx_type="project"))
    assert g.matches(_ctx(ctx_type="meeting"))
    assert not g.matches(_ctx(ctx_type="solo"))


def test_gate_image_dimension():
    needs_image = BlockGate(requires_image=True)
    no_image = BlockGate(requires_image=False)
    assert needs_image.matches(_ctx(has_image=True))
    assert not needs_image.matches(_ctx(has_image=False))
    assert no_image.matches(_ctx(has_image=False))
    assert not no_image.matches(_ctx(has_image=True))


def test_gate_custom_dimension():
    g = BlockGate(custom=lambda c: c.extras.get("foo") == "bar")
    assert g.matches(_ctx(extras={"foo": "bar"}))
    assert not g.matches(_ctx(extras={"foo": "baz"}))
    assert not g.matches(_ctx(extras={}))


def test_gate_custom_exception_treated_as_fail():
    """custom 抛异常视为 fail,不会污染装配。"""
    def boom(_c):
        raise RuntimeError("evil")
    g = BlockGate(custom=boom)
    assert not g.matches(_ctx())


def test_gate_AND_semantics_all_dimensions_must_pass():
    g = BlockGate(
        scopes={"casual_chat"},
        has_tools_in={"x"},
        role_kind_in={"coder"},
    )
    # 全过
    assert g.matches(_ctx(
        scope_tags=("casual_chat",),
        granted_tools=frozenset({"x"}),
        role_kind="coder",
    ))
    # 一项不过
    assert not g.matches(_ctx(
        scope_tags=("casual_chat",),
        granted_tools=frozenset({"x"}),
        role_kind="pm",  # ← 这条不过
    ))


# ── PromptBlock render ───────────────────────────────────────────────


def test_block_render_str():
    b = PromptBlock(id="x", text="hello")
    assert b.render(_ctx()) == "hello"


def test_block_render_callable():
    b = PromptBlock(
        id="x",
        text=lambda c: f"role={c.role_kind}",
    )
    assert b.render(_ctx(role_kind="coder")) == "role=coder"


def test_block_render_callable_exception_returns_empty():
    """render 中的 callable 抛异常时返回空,不影响装配。"""
    b = PromptBlock(id="x", text=lambda _c: 1 / 0)
    assert b.render(_ctx()) == ""


def test_block_render_callable_returns_non_str_returns_empty():
    """callable 返回非 str(如 None / 数字)时返回空。"""
    b = PromptBlock(id="x", text=lambda _c: None)
    assert b.render(_ctx()) == ""

    b2 = PromptBlock(id="y", text=lambda _c: 42)
    assert b2.render(_ctx()) == ""


# ── AssemblyContext factory ──────────────────────────────────────────


def test_context_make_coerces_types():
    ctx = AssemblyContext.make(
        scope_tags=["a", "b"],          # list → tuple
        granted_tools={"x", "y"},        # set → frozenset
        granted_skills={"s1"},
    )
    assert ctx.scope_tags == ("a", "b")
    assert isinstance(ctx.granted_tools, frozenset)
    assert isinstance(ctx.granted_skills, frozenset)


def test_context_is_frozen():
    """AssemblyContext 是 frozen dataclass — 试图修改会抛。"""
    ctx = AssemblyContext.make()
    with pytest.raises(Exception):  # FrozenInstanceError
        ctx.role_kind = "x"  # type: ignore


# ── assemble_static_prompt — core ────────────────────────────────────


def test_assemble_sorts_by_priority_then_id():
    blocks = [
        PromptBlock(id="b", text="B", priority=20),
        PromptBlock(id="a", text="A", priority=20),
        PromptBlock(id="c", text="C", priority=10),
    ]
    text, res = assemble_static_prompt(blocks, _ctx())
    assert res.included == ["c", "a", "b"]
    assert text == "C\n\nA\n\nB"


def test_assemble_excludes_failed_gate_with_reason():
    blocks = [
        PromptBlock(
            id="needs_tool",
            text="X",
            applies_when=BlockGate(has_tools_in={"non_existent"}),
        ),
    ]
    _text, res = assemble_static_prompt(blocks, _ctx())
    assert res.included == []
    assert len(res.excluded) == 1
    eid, reason = res.excluded[0]
    assert eid == "needs_tool"
    assert "missing_tool" in reason


def test_assemble_excludes_empty_render():
    """callable 返回空 → 不装入,记 'empty_render' 原因。"""
    blocks = [
        PromptBlock(id="empty_lambda", text=lambda _c: ""),
        PromptBlock(id="whitespace_only", text=lambda _c: "   \n  \t  "),
        PromptBlock(id="ok", text="real content"),
    ]
    text, res = assemble_static_prompt(blocks, _ctx())
    assert res.included == ["ok"]
    excluded_ids = [eid for eid, _ in res.excluded]
    assert "empty_lambda" in excluded_ids
    assert "whitespace_only" in excluded_ids


def test_assemble_records_cache_anchors():
    blocks = [
        PromptBlock(id="x", text="X", priority=10, cache_anchor=True),
        PromptBlock(id="y", text="Y", priority=20),
        PromptBlock(id="z", text="Z", priority=30, cache_anchor=True),
    ]
    _text, res = assemble_static_prompt(blocks, _ctx())
    assert res.cache_anchor_ids == ["x", "z"]


def test_assemble_total_chars_matches_text():
    blocks = [
        PromptBlock(id="x", text="hello"),
        PromptBlock(id="y", text="world"),
    ]
    text, res = assemble_static_prompt(blocks, _ctx())
    assert res.total_chars == len(text)


def test_assemble_scope_tags_recorded():
    text, res = assemble_static_prompt(
        [PromptBlock(id="x", text="x")],
        _ctx(scope_tags=("data_analysis", "tech_review")),
    )
    assert res.scope_tags == ("data_analysis", "tech_review")


def test_assemble_empty_blocks_returns_empty_text():
    text, res = assemble_static_prompt([], _ctx())
    assert text == ""
    assert res.included == []
    assert res.total_chars == 0


# ── exclusion reasons cover all dimensions ───────────────────────────


@pytest.mark.parametrize("gate_kwargs,ctx_kwargs,expected_substr", [
    ({"scopes": {"meeting"}}, {"scope_tags": ("casual_chat",)}, "scope_mismatch"),
    ({"has_tools_in": {"x"}}, {"granted_tools": frozenset()}, "missing_tool"),
    ({"has_skill_in": {"x"}}, {"granted_skills": frozenset()}, "missing_skill"),
    ({"role_kind_in": {"coder"}}, {"role_kind": "pm"}, "role_mismatch"),
    ({"ctx_type_in": {"project"}}, {"ctx_type": "solo"}, "ctx_mismatch"),
    ({"requires_image": True}, {"has_image": False}, "image_mismatch"),
    ({"custom": lambda _c: False}, {}, "custom_gate"),
])
def test_exclusion_reasons_are_actionable(gate_kwargs, ctx_kwargs, expected_substr):
    block = PromptBlock(id="t", text="x", applies_when=BlockGate(**gate_kwargs))
    _text, res = assemble_static_prompt([block], _ctx(**ctx_kwargs))
    assert len(res.excluded) == 1
    _eid, reason = res.excluded[0]
    assert expected_substr in reason


# ── assemble_with_log ────────────────────────────────────────────────


def test_assemble_with_log_does_not_crash(caplog):
    blocks = [
        PromptBlock(id="a", text="A"),
        PromptBlock(id="b", text="", applies_when=BlockGate(scopes={"NOPE"})),
    ]
    with caplog.at_level(logging.INFO, logger="tudou.prompt_v2"):
        text, res = assemble_with_log(blocks, _ctx(), agent_id="ag-12345678")
    assert text == "A"
    assert any("[prompt_v2]" in r.message for r in caplog.records)


# ── diff_summary ─────────────────────────────────────────────────────


def test_diff_summary_basic():
    v1 = "alpha\nbeta\ngamma"
    v2 = "alpha\ndelta\ngamma"
    d = diff_summary(v1, v2)
    assert d["v1_chars"] == len(v1)
    assert d["v2_chars"] == len(v2)
    assert d["only_in_v1_count"] == 1
    assert d["only_in_v2_count"] == 1
    assert "beta" in d["only_in_v1_sample"]
    assert "delta" in d["only_in_v2_sample"]


def test_diff_summary_empty_inputs():
    d = diff_summary("", "")
    assert d["v1_chars"] == 0
    assert d["v2_chars"] == 0
    assert d["delta_chars"] == 0


# ── Default catalog integration ──────────────────────────────────────


def test_default_catalog_size():
    cat = get_default_catalog()
    assert len(cat) == 13
    assert cat is not DEFAULT_BLOCKS  # 副本


def test_block_by_id_lookup():
    cat = get_default_catalog()
    b = block_by_id(cat, "tool_rules")
    assert b is not None and b.id == "tool_rules"
    assert block_by_id(cat, "no_such_block") is None


def test_default_catalog_blocks_have_unique_ids():
    ids = [b.id for b in DEFAULT_BLOCKS]
    assert len(ids) == len(set(ids)), "duplicate block id in DEFAULT_BLOCKS"


# ── 3-scenario integration ───────────────────────────────────────────


def test_casual_chat_scenario_minimum_blocks():
    """casual_chat + 无 persona + 无文件工具 → 最小集合,不该有 file_display
    long / attachment_contract / project_context_md。"""
    cat = get_default_catalog()
    ctx = AssemblyContext.make(
        scope_tags=["casual_chat"],
        granted_tools={"memory_recall", "knowledge_lookup"},
        role_kind="general",
        ctx_type="solo",
        extras={
            "agent_name": "Alice",
            "agent_role": "assistant",
            "language": "zh",
        },
    )
    _text, res = assemble_static_prompt(cat, ctx)
    excluded_ids = [eid for eid, _ in res.excluded]
    # 必须不被装入
    for unwanted in ("file_display_long", "attachment_contract",
                     "project_context_md", "image_display"):
        assert unwanted in excluded_ids, f"{unwanted} should be excluded for casual_chat"
    # 必须装入(基础块)
    for required in ("identity", "tool_rules", "knowledge_rules"):
        assert required in res.included, f"{required} should be included always"


def test_pptx_authoring_scenario_full_blocks():
    """pptx_authoring + project + 有 persona → 应包含 file_display_long /
    attachment_contract(因为 send_email 也有)/ project_context_md 等。"""
    cat = get_default_catalog()
    ctx = AssemblyContext.make(
        scope_tags=["pptx_authoring"],
        granted_tools={"write_file", "create_pptx", "send_email", "memory_recall"},
        role_kind="analyst",
        ctx_type="project",
        extras={
            "agent_name": "Bob",
            "agent_role": "analyst",
            "language": "zh",
            "agent_system_prompt": "资深分析师",
            "working_dir": "/tmp/ws",
            "shared_workspace": "/tmp/proj",
            "project_name": "Q3 Review",
            "project_id": "p1",
            "project_context_files": [("PROJECT_CONTEXT.md", "目标")],
            "model_guidance": "GPT-4o specific",
        },
    )
    _text, res = assemble_static_prompt(cat, ctx)
    for required in (
        "identity", "tool_rules", "knowledge_rules", "image_display",
        "workspace_context_basic", "persona", "file_display_long",
        "project_context_md", "model_guidance", "attachment_contract",
    ):
        assert required in res.included, f"{required} should be included for pptx_authoring/project"


def test_meeting_scenario_blocks():
    """meeting + send_email 无文件工具 → image_display 跳过(scope 不在白名单),
    file_display_long 跳过(没文件工具),attachment_contract 装入。"""
    cat = get_default_catalog()
    ctx = AssemblyContext.make(
        scope_tags=["meeting"],
        granted_tools={"send_email", "send_message", "memory_recall"},
        role_kind="pm",
        ctx_type="meeting",
        extras={
            "agent_name": "Carol",
            "agent_role": "pm",
            "language": "en",
            "agent_system_prompt": "PM facilitator",
            "working_dir": "/tmp/m",
            "shared_workspace": "/tmp/m",
            "meeting_id": "m42",
        },
    )
    _text, res = assemble_static_prompt(cat, ctx)
    excluded_ids = [eid for eid, _ in res.excluded]
    assert "attachment_contract" in res.included
    assert "image_display" in excluded_ids
    assert "file_display_long" in excluded_ids
    assert "project_context_md" in excluded_ids  # custom gate: no project_context_files


def test_scope_change_alters_block_set():
    """同一 agent,只换 scope_tags,装入集合应该不同(缓存稳定性的核心)。"""
    cat = get_default_catalog()
    base_extras = {
        "agent_name": "X", "agent_role": "engineer", "language": "zh",
        "agent_system_prompt": "engineer",
    }
    ctx_a = AssemblyContext.make(
        scope_tags=["casual_chat"], role_kind="coder", ctx_type="solo",
        granted_tools={"write_file"}, extras=base_extras,
    )
    ctx_b = AssemblyContext.make(
        scope_tags=["pptx_authoring"], role_kind="coder", ctx_type="solo",
        granted_tools={"write_file"}, extras=base_extras,
    )
    _, res_a = assemble_static_prompt(cat, ctx_a)
    _, res_b = assemble_static_prompt(cat, ctx_b)
    # casual_chat 不该有 image_display,pptx_authoring 应该有
    assert "image_display" not in res_a.included
    assert "image_display" in res_b.included
