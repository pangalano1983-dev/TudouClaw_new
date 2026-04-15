#!/usr/bin/env python3
"""
Smoke test for app/agent_state/.

Exercises every core domain and every invariant. Run from the
project root:

    python tools/smoke_agent_state.py

Exit codes:
    0  all scenarios passed
    1  a positive scenario failed (something that should work broke)
    2  a negative scenario failed (an invariant that should fire didn't)
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback

# allow running from project root without installing
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.agent_state import (  # noqa: E402
    AgentState,
    ArtifactKind,
    Capability,
    CommitError,
    ConversationLog,
    ProducedBy,
    Role,
    TaskStackFull,
    TaskStatus,
    check_all,
)
from app.agent_state.capability import Availability, SideEffect  # noqa: E402


# ----------------------------------------------------------------------
# harness
# ----------------------------------------------------------------------
PASSED = []
FAILED = []


def case(name: str):
    def deco(fn):
        def runner():
            try:
                fn()
            except AssertionError as e:
                FAILED.append((name, f"AssertionError: {e}"))
                traceback.print_exc()
                return
            except Exception as e:
                FAILED.append((name, f"{type(e).__name__}: {e}"))
                traceback.print_exc()
                return
            PASSED.append(name)
        runner.__name__ = fn.__name__
        return runner
    return deco


# ----------------------------------------------------------------------
# positive scenarios
# ----------------------------------------------------------------------
@case("artifact: create + get + latest + list filters")
def t_artifact_basic():
    state = AgentState()
    a1 = state.artifacts.create(
        kind=ArtifactKind.URL,
        value="https://example.com/a.mp4",
        label="video A",
        produced_by=ProducedBy(task_id="task_1", tool_id="tool_x"),
    )
    a2 = state.artifacts.create(
        kind=ArtifactKind.URL,
        value="https://example.com/b.mp4",
        label="video B",
        produced_by=ProducedBy(task_id="task_1", tool_id="tool_x"),
    )
    a3 = state.artifacts.create(
        kind=ArtifactKind.RECORD,
        value='{"k":"v"}',
        label="side record",
        produced_by=ProducedBy(task_id="task_1", tool_id="tool_y"),
    )
    assert len(state.artifacts) == 3
    assert state.artifacts.get(a1.id) is a1
    latest_url = state.artifacts.latest(kind=ArtifactKind.URL)
    assert latest_url is not None and latest_url.id == a2.id, \
        f"expected latest URL to be a2, got {latest_url}"
    by_tool = state.artifacts.list(tool_id="tool_x")
    assert len(by_tool) == 2
    by_label = state.artifacts.search_by_label("video")
    assert len(by_label) == 2


@case("artifact: duplicate id rejected (append-only)")
def t_artifact_dup():
    state = AgentState()
    a = state.artifacts.create(
        kind=ArtifactKind.URL, value="https://x", label="x",
    )
    try:
        state.artifacts.put(a)  # same id again
    except ValueError:
        return
    raise AssertionError("duplicate put() should have raised ValueError")


@case("task: push / active / mark_done / recent_terminal")
def t_task_lifecycle():
    state = AgentState()
    t1 = state.tasks.push("generate video")
    assert state.tasks.top() is t1
    assert state.tasks.top().status == TaskStatus.ACTIVE
    t2 = state.tasks.push("download it", parent_task_id=t1.id)
    assert state.tasks.top() is t2
    # t1 should have been demoted to pending
    assert state.tasks.find(t1.id).status == TaskStatus.PENDING
    state.tasks.mark_done(t2.id)
    # t1 should have been promoted back to active
    assert state.tasks.find(t1.id).status == TaskStatus.ACTIVE
    assert state.tasks.top() is t1
    state.tasks.mark_done(t1.id)
    assert state.tasks.top() is None
    terms = state.tasks.recent_terminal(5)
    assert len(terms) == 2


@case("task: max_depth enforced")
def t_task_depth():
    state = AgentState()
    state.tasks._max_depth = 3
    state.tasks.push("a")
    state.tasks.push("b")
    state.tasks.push("c")
    try:
        state.tasks.push("d")
    except TaskStackFull:
        return
    raise AssertionError("4th push should have raised TaskStackFull")


@case("conversation: append + tail + rewrite preserves refs (I2)")
def t_conversation_rewrite():
    state = AgentState()
    a = state.artifacts.create(
        kind=ArtifactKind.URL, value="https://x", label="x",
    )
    state.conversation.append(Role.USER, "hi")
    turn = state.conversation.append(
        Role.ASSISTANT, "生成好了 see {art}", artifact_refs=[a.id],
    )
    # simulate a compression pass blanking text
    state.conversation.rewrite_text(turn.id, "[compressed]")
    # refs must survive
    reloaded = [t for t in state.conversation.all() if t.id == turn.id][0]
    assert reloaded.text == "[compressed]"
    assert reloaded.artifact_refs == [a.id], \
        f"refs corrupted by rewrite: {reloaded.artifact_refs}"


@case("commit: atomic rollback on exception")
def t_commit_rollback():
    state = AgentState()
    state.artifacts.create(kind=ArtifactKind.URL, value="https://a", label="a")
    state.tasks.push("pre-existing task")
    before = state.summary()
    try:
        with state.commit():
            state.artifacts.create(
                kind=ArtifactKind.URL, value="https://b", label="b",
            )
            state.tasks.push("doomed task")
            raise RuntimeError("simulated failure")
    except RuntimeError:
        pass
    after = state.summary()
    assert after == before, \
        f"rollback incomplete:\n  before={before}\n  after ={after}"


@case("commit: clean success")
def t_commit_ok():
    state = AgentState()
    with state.commit():
        t = state.tasks.push("do a thing")
        a = state.artifacts.create(
            kind=ArtifactKind.URL, value="https://ok", label="ok",
            produced_by=ProducedBy(task_id=t.id, tool_id="tool_x"),
        )
        state.tasks.attach_result(t.id, a.id)
        state.conversation.append(
            Role.ASSISTANT, "done, see {art}", artifact_refs=[a.id],
            task_id=t.id,
        )
        state.tasks.mark_done(t.id)
    assert state.tasks.find(t.id).status == TaskStatus.DONE
    assert state.tasks.find(t.id).result_refs == [a.id]


@case("I5: file artifact inside deliverable_dir passes")
def t_i5_ok():
    with tempfile.TemporaryDirectory() as td:
        state = AgentState()
        state.env.deliverable_dir = td
        path = os.path.join(td, "video.mp4")
        with state.commit():
            state.artifacts.create(
                kind=ArtifactKind.VIDEO, value=path, label="v",
            )
        assert not any(v.code == "I5" for v in state.last_violations)


# ----------------------------------------------------------------------
# negative scenarios — invariants must fire
# ----------------------------------------------------------------------
@case("I1: conversation ref to missing artifact -> commit error")
def t_i1_missing_ref():
    state = AgentState()
    try:
        with state.commit():
            state.conversation.append(
                Role.ASSISTANT, "see {art}", artifact_refs=["art_ghost"],
            )
    except CommitError as e:
        assert any(v.code == "I1" for v in e.violations), \
            f"expected I1 in {[v.code for v in e.violations]}"
        return
    raise AssertionError("expected CommitError for I1")


@case("I1: task result_ref to missing artifact -> commit error")
def t_i1_task_ref():
    state = AgentState()
    try:
        with state.commit():
            t = state.tasks.push("x")
            state.tasks.attach_result(t.id, "art_ghost")
    except CommitError as e:
        assert any(v.code == "I1" for v in e.violations)
        return
    raise AssertionError("expected CommitError for I1")


@case("I4: task plans unknown tool -> commit error")
def t_i4_unknown_tool():
    state = AgentState()
    state.capabilities.register(Capability(
        tool_id="tool_known", description="ok",
        side_effects=SideEffect.READ, availability=Availability.ONLINE,
    ))
    try:
        with state.commit():
            state.tasks.push(
                "do it", metadata={"planned_tool": "tool_hallucinated"},
            )
    except CommitError as e:
        assert any(v.code == "I4" for v in e.violations)
        return
    raise AssertionError("expected CommitError for I4")


@case("I5: file artifact outside deliverable_dir -> commit error")
def t_i5_outside():
    with tempfile.TemporaryDirectory() as deliverable:
        with tempfile.TemporaryDirectory() as other:
            state = AgentState()
            state.env.deliverable_dir = deliverable
            bad_path = os.path.join(other, "leaked.mp4")
            try:
                with state.commit():
                    state.artifacts.create(
                        kind=ArtifactKind.VIDEO, value=bad_path, label="bad",
                    )
            except CommitError as e:
                assert any(v.code == "I5" for v in e.violations), \
                    f"expected I5, got {[v.code for v in e.violations]}"
                return
            raise AssertionError("expected CommitError for I5")


@case("I5: URL artifact bypasses path check (as designed)")
def t_i5_url_ok():
    with tempfile.TemporaryDirectory() as td:
        state = AgentState()
        state.env.deliverable_dir = td
        with state.commit():
            state.artifacts.create(
                kind=ArtifactKind.VIDEO,
                value="https://signed.example.com/x.mp4",
                label="signed url",
            )
        # a URL video should NOT trigger I5
        assert not any(v.code == "I5" for v in state.last_violations)


# ----------------------------------------------------------------------
def main() -> int:
    tests = [
        t_artifact_basic, t_artifact_dup,
        t_task_lifecycle, t_task_depth,
        t_conversation_rewrite,
        t_commit_rollback, t_commit_ok,
        t_i5_ok,
        t_i1_missing_ref, t_i1_task_ref,
        t_i4_unknown_tool,
        t_i5_outside, t_i5_url_ok,
    ]
    print(f"running {len(tests)} smoke tests against app.agent_state")
    print("-" * 60)
    for t in tests:
        t()
    print("-" * 60)
    for name in PASSED:
        print(f"  OK   {name}")
    for name, err in FAILED:
        print(f"  FAIL {name}")
        print(f"       {err}")
    print("-" * 60)
    print(f"passed: {len(PASSED)}  failed: {len(FAILED)}")
    if FAILED:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
