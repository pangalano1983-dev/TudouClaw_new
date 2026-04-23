"""Progress Bus — 统一发布订阅系统，服务三种场景：

1. 短任务的 tool_call / tool_result（从 agent.events 自动转发）
2. 生产 skill 的实时预览（tool_preview / tool_live / tool_abort 帧）
3. 长任务的周期性可见（step_started / step_heartbeat / step_completed /
   step_failed / plan_digest 帧）

订阅者按 channel 注册：
    "plan:<plan_id>"      — 某个 plan 的所有帧
    "agent:<agent_id>"    — 某个 agent 的所有帧
    "tool:<session_id>"   — 某次生产工具调用（live preview）
    "global"              — 全量 firehose，给 admin dashboard

实现细节：
- 单例（get_bus()）
- 每个 channel 有独立 ring buffer（最近 N 条，默认 200）用于断线重连 replay
- 每个 subscriber 是一个线程安全 Queue；SSE handler drain 该 Queue
- 线程安全（publish 可由任何线程调用，包括 agent 执行线程、工具线程）
- 超时、背压：单个 subscriber 的 queue 满了丢最老帧，不阻塞 publisher
- 零外部依赖 — 不引入 redis / kafka / anyio.Stream

使用示例：
    from app.progress_bus import get_bus, ProgressFrame
    bus = get_bus()
    bus.publish(ProgressFrame(
        kind="step_heartbeat",
        channel="plan:abc123",
        plan_id="abc123",
        step_id="step-2",
        agent_id="小土",
        data={"elapsed_s": 45, "note": "processing file 47/100"},
    ))

    # 订阅端（SSE handler 里）：
    sub = bus.subscribe("plan:abc123", replay=True)
    for frame in sub.stream():
        yield f"data: {json.dumps(frame.to_dict())}\\n\\n"
"""
from __future__ import annotations

import json
import logging
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import Iterator, Optional

logger = logging.getLogger("tudou.progress_bus")


# ─── Frame kinds ──────────────────────────────────────────────────
# String constants rather than an Enum so non-Python subscribers (JS
# frontend, audit log viewer) can match without mapping. Add new kinds
# here in one place; subscribers use kind.startswith(...) for families.

# Task / plan level — long-running work progress
FRAME_STEP_STARTED    = "step_started"
FRAME_STEP_HEARTBEAT  = "step_heartbeat"   # periodic, even when no state change
FRAME_STEP_COMPLETED  = "step_completed"
FRAME_STEP_FAILED     = "step_failed"
FRAME_PLAN_DIGEST     = "plan_digest"      # 30-min rollup summary

# Tool invocation level — production skill live preview (Phase 2)
FRAME_TOOL_PREVIEW    = "tool_preview"     # "here's what I'm about to do"
FRAME_TOOL_LIVE       = "tool_live"        # streamed stdout during execution
FRAME_TOOL_ABORT      = "tool_abort"       # aborted with inconsistent-state report
FRAME_TOOL_DONE       = "tool_done"

# Stale step — plan shows in_progress but agent is idle OR agent has made no
# progress within threshold. Surfaces as yellow warning in UI so human can
# pick: mark_failed / skip / resume. See Agent._detect_stale_plan_steps.
FRAME_STEP_STALE      = "step_stale"

# Verifier result (Block 2 Review loop) — ok | not-ok + details
FRAME_VERIFY_RESULT   = "verify_result"

# Mirrored from existing agent.events — kept so a single subscriber can
# see both old-style tool_call events and new progress frames.
FRAME_MIRROR_TOOL_CALL    = "mirror_tool_call"
FRAME_MIRROR_TOOL_RESULT  = "mirror_tool_result"
FRAME_MIRROR_MESSAGE      = "mirror_message"


@dataclass
class ProgressFrame:
    """One event on the bus.

    `channel` is the primary routing key. Frames with a scoped channel
    (e.g. "plan:X") are also automatically forked to "global" so the
    admin dashboard can see everything with one subscription.
    """
    kind: str
    channel: str
    timestamp: float = field(default_factory=time.time)
    # Optional routing IDs — used by frontend to correlate frames, NOT
    # for channel dispatch (channel field is the source of truth).
    plan_id: str = ""
    step_id: str = ""
    agent_id: str = ""
    session_id: str = ""     # production-skill tool invocation id
    # Free-form payload, kind-specific. Kept small; large stdout blobs
    # should be truncated by the publisher, not stuffed in verbatim.
    data: dict = field(default_factory=dict)

    # Monotonically increasing sequence number, assigned by the bus on
    # publish. Lets subscribers diff "I saw up to seq=42" → replay from
    # seq > 42 only on reconnect.
    seq: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)


# ─── Subscriber ──────────────────────────────────────────────────

class Subscriber:
    """Represents one connected client (SSE request, test harness, etc.).

    Each subscriber has its own Queue. publish() fans out by putting a
    copy into every matching subscriber's queue. Queue is bounded —
    slow consumer = drop oldest, not block the publisher.
    """

    # Per-subscriber queue cap. One HTTP client can fall behind briefly;
    # beyond this cap we drop oldest frames to keep the bus flowing.
    # 256 covers ~80s of frames at 3 Hz or ~4min at 1 Hz.
    QUEUE_CAP = 256

    def __init__(self, channel_pattern: str, sub_id: str):
        self.channel_pattern = channel_pattern
        self.sub_id = sub_id
        self._q: queue.Queue[ProgressFrame] = queue.Queue(maxsize=self.QUEUE_CAP)
        self._closed = False
        self.dropped_count = 0
        self.created_at = time.time()

    def _match(self, channel: str) -> bool:
        """True if a frame on `channel` belongs to this subscriber."""
        if self.channel_pattern == "global":
            return True
        if self.channel_pattern == channel:
            return True
        # Prefix-pattern support: subscriber on "plan:*" sees all plan
        # frames (handy for admin dashboards). Keep simple: only `*`
        # suffix supported, no regex.
        if self.channel_pattern.endswith("*"):
            return channel.startswith(self.channel_pattern[:-1])
        return False

    def _offer(self, frame: ProgressFrame) -> None:
        """Non-blocking enqueue. If full, drop oldest and record."""
        if self._closed:
            return
        try:
            self._q.put_nowait(frame)
        except queue.Full:
            # Slow consumer — drop oldest, record, try again.
            try:
                self._q.get_nowait()
                self.dropped_count += 1
            except queue.Empty:
                pass
            try:
                self._q.put_nowait(frame)
            except queue.Full:
                # Double failure shouldn't happen with a single-threaded
                # queue, but don't crash.
                pass

    def next(self, timeout: float = 30.0) -> Optional[ProgressFrame]:
        """Block for next frame. Returns None on timeout (SSE handler
        can use this as a heartbeat opportunity)."""
        if self._closed:
            return None
        try:
            return self._q.get(timeout=timeout)
        except queue.Empty:
            return None

    def stream(self, heartbeat_s: float = 25.0) -> Iterator[ProgressFrame]:
        """Yield frames until closed. Emits a synthetic heartbeat frame
        periodically so SSE clients stay alive even on quiet channels."""
        while not self._closed:
            f = self.next(timeout=heartbeat_s)
            if f is None:
                if self._closed:
                    return
                # Synthetic keepalive — doesn't go through publish(), so
                # it doesn't clutter other subscribers' queues.
                yield ProgressFrame(
                    kind="heartbeat",
                    channel=self.channel_pattern,
                    data={"note": "bus keepalive"},
                )
                continue
            yield f

    def close(self) -> None:
        self._closed = True


# ─── ProgressBus ──────────────────────────────────────────────────

class _ProgressBus:
    """Singleton. Mutations behind a single lock — contention negligible
    in practice (publish rate is at most a few Hz per agent).

    Ring buffer per-channel so a late subscriber can request `replay=True`
    and catch up on recent history.
    """

    # Per-channel ring size. 200 = ~3-5min of history at 1Hz; enough for
    # a refresh-after-disconnect scenario, not for real log archival
    # (audit bucket handles persistence).
    RING_SIZE = 200

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subscribers: list[Subscriber] = []
        self._rings: dict[str, deque[ProgressFrame]] = {}
        self._seq_counter = 0
        self._sub_counter = 0

    # ── publish ──────────────────────────────────────────────────
    def publish(self, frame: ProgressFrame) -> None:
        """Thread-safe publish. Blocks only on the singleton lock (micro-
        second contention)."""
        if not frame.channel:
            logger.warning("progress_bus: frame missing channel, dropped")
            return
        with self._lock:
            self._seq_counter += 1
            frame.seq = self._seq_counter
            # Append to the primary channel's ring
            ring = self._rings.setdefault(frame.channel, deque(maxlen=self.RING_SIZE))
            ring.append(frame)
            # "global" ring also gets it (so global subscribers can replay)
            if frame.channel != "global":
                global_ring = self._rings.setdefault("global", deque(maxlen=self.RING_SIZE))
                global_ring.append(frame)
            # Fan out to matching subscribers (outside lock isn't trivial
            # because we'd need to snapshot the list; holding the lock
            # during .put_nowait is cheap because queues are bounded).
            for sub in self._subscribers:
                if sub._closed:
                    continue
                if sub._match(frame.channel):
                    sub._offer(frame)

    # ── subscribe ────────────────────────────────────────────────
    def subscribe(self, channel_pattern: str, *, replay: bool = False,
                   replay_since_seq: int | None = None) -> Subscriber:
        """Register a subscriber.

        `replay=True` seeds the subscriber's queue with the ring buffer's
        current contents for the matched channel — lets a newly connected
        client catch up on recent history before listening for new frames.

        `replay_since_seq` (if set) only replays frames with seq > that
        value, for clients reconnecting mid-stream.
        """
        with self._lock:
            self._sub_counter += 1
            sub = Subscriber(channel_pattern=channel_pattern,
                              sub_id=f"sub-{self._sub_counter}")
            self._subscribers.append(sub)

            if replay:
                # Seed from ring. For pattern subscribers (e.g. "plan:*")
                # we merge all matching rings. Global replay reads the
                # "global" ring (which already contains everything).
                if channel_pattern == "global":
                    rings_to_scan = [self._rings.get("global", deque())]
                elif channel_pattern.endswith("*"):
                    prefix = channel_pattern[:-1]
                    rings_to_scan = [
                        ring for ch, ring in self._rings.items()
                        if ch.startswith(prefix)
                    ]
                else:
                    rings_to_scan = [self._rings.get(channel_pattern, deque())]
                # Flatten + sort by seq so replay preserves order across channels
                seeds: list[ProgressFrame] = []
                for r in rings_to_scan:
                    seeds.extend(r)
                seeds.sort(key=lambda f: f.seq)
                for f in seeds:
                    if replay_since_seq is not None and f.seq <= replay_since_seq:
                        continue
                    sub._offer(f)
            return sub

    def unsubscribe(self, sub: Subscriber) -> None:
        """Cleanup. Safe to call repeatedly."""
        sub.close()
        with self._lock:
            try:
                self._subscribers.remove(sub)
            except ValueError:
                pass

    # ── introspection ────────────────────────────────────────────
    def stats(self) -> dict:
        with self._lock:
            return {
                "subscribers": len(self._subscribers),
                "channels": len(self._rings),
                "total_published": self._seq_counter,
                "channel_sizes": {
                    ch: len(ring) for ch, ring in self._rings.items()
                },
            }


# ─── Singleton accessor ──────────────────────────────────────────

_bus: _ProgressBus | None = None
_bus_lock = threading.Lock()


def get_bus() -> _ProgressBus:
    """Returns the global ProgressBus singleton. Safe to call from any thread."""
    global _bus
    if _bus is None:
        with _bus_lock:
            if _bus is None:
                _bus = _ProgressBus()
    return _bus


# ─── Convenience helpers ─────────────────────────────────────────
# Cut the boilerplate for the most common publish sites. Kind-specific
# wrappers enforce required fields and keep publisher call-sites short.

def emit_step_started(*, plan_id: str, step_id: str, agent_id: str,
                       title: str = "", estimated_duration_s: float = 0.0) -> None:
    get_bus().publish(ProgressFrame(
        kind=FRAME_STEP_STARTED,
        channel=f"plan:{plan_id}",
        plan_id=plan_id, step_id=step_id, agent_id=agent_id,
        data={"title": title[:200],
              "estimated_duration_s": estimated_duration_s},
    ))


def emit_step_heartbeat(*, plan_id: str, step_id: str, agent_id: str,
                         elapsed_s: float, note: str = "") -> None:
    get_bus().publish(ProgressFrame(
        kind=FRAME_STEP_HEARTBEAT,
        channel=f"plan:{plan_id}",
        plan_id=plan_id, step_id=step_id, agent_id=agent_id,
        data={"elapsed_s": round(elapsed_s, 1), "note": note[:300]},
    ))


def emit_step_completed(*, plan_id: str, step_id: str, agent_id: str,
                         duration_s: float, summary: str = "") -> None:
    get_bus().publish(ProgressFrame(
        kind=FRAME_STEP_COMPLETED,
        channel=f"plan:{plan_id}",
        plan_id=plan_id, step_id=step_id, agent_id=agent_id,
        data={"duration_s": round(duration_s, 1), "summary": summary[:500]},
    ))


def emit_step_failed(*, plan_id: str, step_id: str, agent_id: str,
                      error: str, will_retry: bool = False) -> None:
    get_bus().publish(ProgressFrame(
        kind=FRAME_STEP_FAILED,
        channel=f"plan:{plan_id}",
        plan_id=plan_id, step_id=step_id, agent_id=agent_id,
        data={"error": error[:500], "will_retry": will_retry},
    ))


def emit_step_stale(*, plan_id: str, step_id: str, agent_id: str,
                     step_title: str, stale_s: float, reason: str = "") -> None:
    """Warn the UI that a step has been in_progress with no activity.

    Does NOT mutate step state — consumer (UI / human) decides what to do.
    Three human actions are wired through separate API endpoints:
    mark_failed / skip / resume.
    """
    get_bus().publish(ProgressFrame(
        kind=FRAME_STEP_STALE,
        channel=f"plan:{plan_id}" if plan_id else f"agent:{agent_id}",
        plan_id=plan_id, step_id=step_id, agent_id=agent_id,
        data={
            "title": step_title[:200],
            "stale_s": round(stale_s, 1),
            "reason": reason[:300] or "agent idle with step in_progress",
        },
    ))


def emit_plan_digest(*, plan_id: str, agent_id: str,
                      window_s: float, summary: str) -> None:
    get_bus().publish(ProgressFrame(
        kind=FRAME_PLAN_DIGEST,
        channel=f"plan:{plan_id}",
        plan_id=plan_id, agent_id=agent_id,
        data={"window_s": round(window_s, 1), "summary": summary[:2000]},
    ))


def mirror_agent_event(*, agent_id: str, kind: str, data: dict) -> None:
    """Bridge existing agent.events into the progress bus.

    Called by the agent execution loop after its own _log()/emit, so a
    single subscriber on "agent:<id>" sees both old-style tool_call /
    tool_result events AND new progress frames without maintaining two
    subscriptions.

    Only mirrors a small whitelist of kinds to keep firehose clean.
    """
    # Map internal event kinds → mirrored frame kinds. Unlisted kinds
    # are dropped so we don't flood the bus with internal debug events.
    _MAP = {
        "tool_call": FRAME_MIRROR_TOOL_CALL,
        "tool_result": FRAME_MIRROR_TOOL_RESULT,
        "message": FRAME_MIRROR_MESSAGE,
    }
    mirrored = _MAP.get(kind)
    if not mirrored:
        return
    # Trim heavy fields (tool_result can be 1000 chars; we snapshot here)
    trimmed: dict = {}
    for k, v in (data or {}).items():
        if isinstance(v, str) and len(v) > 500:
            trimmed[k] = v[:500] + "...[trimmed]"
        else:
            trimmed[k] = v
    get_bus().publish(ProgressFrame(
        kind=mirrored,
        channel=f"agent:{agent_id}",
        agent_id=agent_id,
        data=trimmed,
    ))


__all__ = [
    "ProgressFrame", "Subscriber", "get_bus",
    # kind constants
    "FRAME_STEP_STARTED", "FRAME_STEP_HEARTBEAT",
    "FRAME_STEP_COMPLETED", "FRAME_STEP_FAILED",
    "FRAME_STEP_STALE", "FRAME_VERIFY_RESULT",
    "FRAME_PLAN_DIGEST",
    "FRAME_TOOL_PREVIEW", "FRAME_TOOL_LIVE",
    "FRAME_TOOL_ABORT", "FRAME_TOOL_DONE",
    "FRAME_MIRROR_TOOL_CALL", "FRAME_MIRROR_TOOL_RESULT",
    "FRAME_MIRROR_MESSAGE",
    # helpers
    "emit_step_started", "emit_step_heartbeat",
    "emit_step_completed", "emit_step_failed",
    "emit_step_stale", "emit_plan_digest", "mirror_agent_event",
]
