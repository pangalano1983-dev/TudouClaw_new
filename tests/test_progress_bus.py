"""ProgressBus — tests.

Cover:
- publish / subscribe basic flow
- channel scoping: plan:X subscriber ignores plan:Y frames
- global subscriber sees everything
- pattern subscriber (plan:*) sees multiple plans
- replay: late subscriber catches up from ring buffer
- replay_since_seq: reconnecting subscriber skips already-seen frames
- slow consumer back-pressure (queue fills → drop oldest, not block)
- convenience emit_* helpers produce correct frame kinds
- unsubscribe cleanup
- thread safety: many publishers, one subscriber receives all
"""
from __future__ import annotations

import threading
import time
import pytest

from app.progress_bus import (
    get_bus, ProgressFrame, Subscriber,
    FRAME_STEP_STARTED, FRAME_STEP_HEARTBEAT, FRAME_STEP_COMPLETED,
    FRAME_STEP_FAILED, FRAME_PLAN_DIGEST, FRAME_MIRROR_TOOL_CALL,
    emit_step_started, emit_step_heartbeat, emit_step_completed,
    emit_step_failed, emit_plan_digest, mirror_agent_event,
)


@pytest.fixture
def bus():
    """Shared singleton across tests. Rings accumulate across test runs
    but each test uses unique channel names so we never see cross-test
    noise. subscribers are explicitly closed in each test."""
    return get_bus()


# ─── basic publish/subscribe ──────────────────────────────────────

def test_publish_delivers_to_matching_subscriber(bus):
    sub = bus.subscribe("plan:t-basic-1")
    try:
        bus.publish(ProgressFrame(
            kind=FRAME_STEP_STARTED,
            channel="plan:t-basic-1",
            plan_id="t-basic-1",
            data={"title": "do the thing"},
        ))
        frame = sub.next(timeout=1.0)
        assert frame is not None
        assert frame.kind == FRAME_STEP_STARTED
        assert frame.plan_id == "t-basic-1"
        assert frame.seq > 0
    finally:
        bus.unsubscribe(sub)


def test_channel_scoping_isolates_subscribers(bus):
    """A subscriber on plan:X must NOT receive frames from plan:Y."""
    sub_x = bus.subscribe("plan:t-scope-x")
    sub_y = bus.subscribe("plan:t-scope-y")
    try:
        bus.publish(ProgressFrame(
            kind=FRAME_STEP_COMPLETED,
            channel="plan:t-scope-x",
            plan_id="t-scope-x",
            data={"summary": "done x"},
        ))
        bus.publish(ProgressFrame(
            kind=FRAME_STEP_COMPLETED,
            channel="plan:t-scope-y",
            plan_id="t-scope-y",
            data={"summary": "done y"},
        ))
        # sub_x should see ONLY x
        f_x = sub_x.next(timeout=1.0)
        assert f_x is not None and f_x.plan_id == "t-scope-x"
        assert sub_x.next(timeout=0.2) is None  # no extra frame

        # sub_y should see ONLY y
        f_y = sub_y.next(timeout=1.0)
        assert f_y is not None and f_y.plan_id == "t-scope-y"
        assert sub_y.next(timeout=0.2) is None
    finally:
        bus.unsubscribe(sub_x)
        bus.unsubscribe(sub_y)


def test_global_subscriber_sees_all_channels(bus):
    sub = bus.subscribe("global")
    try:
        bus.publish(ProgressFrame(
            kind=FRAME_STEP_STARTED,
            channel="plan:t-global-a", plan_id="t-global-a",
        ))
        bus.publish(ProgressFrame(
            kind=FRAME_STEP_STARTED,
            channel="plan:t-global-b", plan_id="t-global-b",
        ))
        # Both should land in the global subscriber
        seen_plans = set()
        for _ in range(2):
            f = sub.next(timeout=1.0)
            assert f is not None
            seen_plans.add(f.plan_id)
        assert seen_plans == {"t-global-a", "t-global-b"}
    finally:
        bus.unsubscribe(sub)


def test_pattern_subscriber_matches_prefix(bus):
    """Subscriber on 'plan:*' should see any channel starting with plan:."""
    sub = bus.subscribe("plan:*")
    try:
        bus.publish(ProgressFrame(
            kind=FRAME_STEP_STARTED,
            channel="plan:t-pat-a", plan_id="t-pat-a",
        ))
        bus.publish(ProgressFrame(
            kind=FRAME_STEP_STARTED,
            channel="plan:t-pat-b", plan_id="t-pat-b",
        ))
        bus.publish(ProgressFrame(
            kind=FRAME_STEP_STARTED,
            channel="agent:other",  # NOT plan:, should NOT match
            agent_id="other",
        ))
        seen = []
        for _ in range(2):
            f = sub.next(timeout=1.0)
            assert f is not None
            seen.append(f.plan_id)
        # No third frame (agent:other doesn't match plan:*)
        assert sub.next(timeout=0.2) is None
        assert set(seen) == {"t-pat-a", "t-pat-b"}
    finally:
        bus.unsubscribe(sub)


# ─── replay ──────────────────────────────────────────────────────

def test_replay_seeds_subscriber_with_recent_history(bus):
    """A subscriber with replay=True should see frames published BEFORE
    it connected (up to ring size)."""
    ch = "plan:t-replay-1"
    # Publish 5 frames first
    for i in range(5):
        bus.publish(ProgressFrame(
            kind=FRAME_STEP_HEARTBEAT,
            channel=ch, plan_id="t-replay-1", step_id=f"s{i}",
        ))
    # Now subscribe with replay
    sub = bus.subscribe(ch, replay=True)
    try:
        received_steps = []
        for _ in range(5):
            f = sub.next(timeout=1.0)
            assert f is not None
            received_steps.append(f.step_id)
        # Order preserved from publish order
        assert received_steps == ["s0", "s1", "s2", "s3", "s4"]
    finally:
        bus.unsubscribe(sub)


def test_replay_since_seq_skips_already_seen(bus):
    """Reconnecting client says 'I saw up to seq=N' — only newer frames replay."""
    ch = "plan:t-since-1"
    bus.publish(ProgressFrame(kind="test", channel=ch, plan_id="t-since-1"))
    last_seq = bus.stats()["total_published"]
    # Three more frames
    for i in range(3):
        bus.publish(ProgressFrame(kind="test", channel=ch, plan_id="t-since-1",
                                    step_id=f"after-{i}"))
    sub = bus.subscribe(ch, replay=True, replay_since_seq=last_seq)
    try:
        seen = []
        for _ in range(3):
            f = sub.next(timeout=1.0)
            assert f is not None
            seen.append(f.step_id)
        assert seen == ["after-0", "after-1", "after-2"]
    finally:
        bus.unsubscribe(sub)


# ─── slow consumer / back-pressure ────────────────────────────────

def test_slow_consumer_drops_oldest_without_blocking(bus):
    """Publishing faster than the subscriber drains should drop frames,
    not block the publisher."""
    sub = bus.subscribe("plan:t-slow-1")
    try:
        # Flood beyond queue cap without draining
        n = Subscriber.QUEUE_CAP + 50
        start = time.time()
        for i in range(n):
            bus.publish(ProgressFrame(
                kind="test", channel="plan:t-slow-1",
                plan_id="t-slow-1", step_id=f"s{i}",
            ))
        elapsed = time.time() - start
        # Should not have blocked — publishing 300 in-memory frames is <1s
        assert elapsed < 1.0, f"publisher blocked ({elapsed:.2f}s)"
        # Subscriber recorded drops
        assert sub.dropped_count > 0
        # Queue is at cap
        drained = 0
        while sub.next(timeout=0.01) is not None:
            drained += 1
            if drained > Subscriber.QUEUE_CAP + 5:
                break
        assert drained <= Subscriber.QUEUE_CAP
    finally:
        bus.unsubscribe(sub)


# ─── unsubscribe ──────────────────────────────────────────────────

def test_unsubscribe_stops_delivery(bus):
    sub = bus.subscribe("plan:t-unsub-1")
    bus.unsubscribe(sub)
    # Publish after unsubscribe
    bus.publish(ProgressFrame(
        kind="test", channel="plan:t-unsub-1", plan_id="t-unsub-1",
    ))
    # next() on closed subscriber returns None quickly
    assert sub.next(timeout=0.2) is None


def test_unsubscribe_idempotent(bus):
    sub = bus.subscribe("plan:t-unsub-idem")
    bus.unsubscribe(sub)
    bus.unsubscribe(sub)  # should not raise


# ─── convenience emit_* helpers ──────────────────────────────────

def test_emit_step_started_publishes_correct_frame(bus):
    sub = bus.subscribe("plan:t-helper-1")
    try:
        emit_step_started(plan_id="t-helper-1", step_id="s1",
                           agent_id="小土", title="Collect data",
                           estimated_duration_s=300.0)
        f = sub.next(timeout=1.0)
        assert f is not None
        assert f.kind == FRAME_STEP_STARTED
        assert f.plan_id == "t-helper-1"
        assert f.step_id == "s1"
        assert f.agent_id == "小土"
        assert f.data["title"] == "Collect data"
        assert f.data["estimated_duration_s"] == 300.0
    finally:
        bus.unsubscribe(sub)


def test_emit_step_completed_includes_duration_and_summary(bus):
    sub = bus.subscribe("plan:t-helper-2")
    try:
        emit_step_completed(plan_id="t-helper-2", step_id="s1",
                             agent_id="小土", duration_s=42.7,
                             summary="wrote report.pptx (12 slides)")
        f = sub.next(timeout=1.0)
        assert f.kind == FRAME_STEP_COMPLETED
        assert f.data["duration_s"] == 42.7
        assert "report.pptx" in f.data["summary"]
    finally:
        bus.unsubscribe(sub)


def test_emit_plan_digest_truncates_long_summary(bus):
    sub = bus.subscribe("plan:t-helper-3")
    try:
        long_summary = "x" * 3000
        emit_plan_digest(plan_id="t-helper-3", agent_id="小土",
                          window_s=1800, summary=long_summary)
        f = sub.next(timeout=1.0)
        assert f.kind == FRAME_PLAN_DIGEST
        assert len(f.data["summary"]) == 2000  # truncation cap
    finally:
        bus.unsubscribe(sub)


def test_mirror_agent_event_bridges_old_tool_calls(bus):
    """mirror_agent_event takes an agent.events kind and republishes to bus."""
    sub = bus.subscribe("agent:t-mirror-1")
    try:
        mirror_agent_event(agent_id="t-mirror-1", kind="tool_call",
                            data={"name": "read_file", "args": "foo.py"})
        f = sub.next(timeout=1.0)
        assert f.kind == FRAME_MIRROR_TOOL_CALL
        assert f.agent_id == "t-mirror-1"
        assert f.data["name"] == "read_file"
    finally:
        bus.unsubscribe(sub)


def test_mirror_ignores_unmapped_kinds(bus):
    """Internal debug events shouldn't flood the bus."""
    sub = bus.subscribe("agent:t-mirror-noise")
    try:
        mirror_agent_event(agent_id="t-mirror-noise", kind="internal_trace",
                            data={"foo": "bar"})
        mirror_agent_event(agent_id="t-mirror-noise", kind="heartbeat_tick",
                            data={"tick": 42})
        # Nothing should arrive
        assert sub.next(timeout=0.2) is None
    finally:
        bus.unsubscribe(sub)


def test_mirror_trims_heavy_data(bus):
    """Long stdout strings in tool_result shouldn't clog the bus."""
    sub = bus.subscribe("agent:t-mirror-trim")
    try:
        big = "x" * 2000
        mirror_agent_event(agent_id="t-mirror-trim", kind="tool_result",
                            data={"name": "bash", "result": big})
        f = sub.next(timeout=1.0)
        assert f is not None
        assert len(f.data["result"]) < 600  # trimmed to 500 + marker
        assert "trimmed" in f.data["result"]
    finally:
        bus.unsubscribe(sub)


# ─── thread safety ────────────────────────────────────────────────

def test_concurrent_publishers_all_land(bus):
    """Many threads publishing to the same channel — subscriber should
    see every frame exactly once."""
    ch = "plan:t-concurrent-1"
    n_threads = 8
    per_thread = 20
    expected = n_threads * per_thread
    sub = bus.subscribe(ch)

    def publisher(tid: int):
        for i in range(per_thread):
            bus.publish(ProgressFrame(
                kind="test", channel=ch, plan_id="t-concurrent-1",
                step_id=f"t{tid}-i{i}",
            ))

    try:
        threads = [threading.Thread(target=publisher, args=(t,), daemon=True)
                    for t in range(n_threads)]
        for t in threads: t.start()
        for t in threads: t.join()

        # Drain
        received = set()
        while True:
            f = sub.next(timeout=0.3)
            if f is None:
                break
            received.add(f.step_id)
        assert len(received) == expected, \
            f"expected {expected} unique frames, got {len(received)}"
    finally:
        bus.unsubscribe(sub)


def test_publish_without_channel_is_dropped(bus):
    """Frames missing channel are dropped (logged) not crashed."""
    # No subscriber needed — just verify it doesn't raise
    bus.publish(ProgressFrame(kind="test", channel="", plan_id="x"))
    # If we got here without exception, pass


# ─── stats ────────────────────────────────────────────────────────

def test_stats_exposes_subscriber_and_channel_counts(bus):
    before = bus.stats()
    sub = bus.subscribe("plan:t-stats-1")
    try:
        bus.publish(ProgressFrame(kind="test", channel="plan:t-stats-1"))
        after = bus.stats()
        assert after["subscribers"] >= before["subscribers"] + 1
        assert after["total_published"] > before["total_published"]
        assert "plan:t-stats-1" in after["channel_sizes"]
    finally:
        bus.unsubscribe(sub)
