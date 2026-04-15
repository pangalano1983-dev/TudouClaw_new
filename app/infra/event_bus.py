"""
EventBus — 进程内发布-订阅事件系统。

设计目标：
  - Agent/Hub/Workflow 可以发布事件（如 agent.status_changed, task.completed）
  - 订阅方通过 callback 或 queue 接收事件
  - 支持通配符订阅（如 "agent.*" 匹配所有 agent 事件）
  - 线程安全，适合多 Agent 并行场景
  - 支持事件历史回溯（ring buffer）

事件命名约定：
  {domain}.{action}
  - agent.created, agent.status_changed, agent.deleted
  - task.started, task.completed, task.failed
  - workflow.step_completed, workflow.completed, workflow.failed
  - approval.requested, approval.decided
  - delegation.requested, delegation.accepted, delegation.rejected
  - project.task_created, project.task_completed
  - hub.message_sent, hub.node_connected, hub.node_disconnected
"""
from __future__ import annotations

import fnmatch
import logging
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger("tudou.events")


# ─────────────────────────────────────────────────────────────
# Event 数据结构
# ─────────────────────────────────────────────────────────────

@dataclass
class Event:
    """一个事件。"""
    topic: str                            # e.g. "agent.status_changed"
    data: dict[str, Any] = field(default_factory=dict)
    source: str = ""                      # 发送者 ID (agent_id, hub, system)
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "topic": self.topic,
            "data": self.data,
            "source": self.source,
            "timestamp": self.timestamp,
        }


# ─────────────────────────────────────────────────────────────
# Subscription
# ─────────────────────────────────────────────────────────────

@dataclass
class Subscription:
    """一个订阅。"""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    pattern: str = ""                     # 订阅的 topic 模式 (支持 * 通配符)
    callback: Callable[[Event], None] | None = None
    subscriber_id: str = ""               # 订阅者标识
    created_at: float = field(default_factory=time.time)


# ─────────────────────────────────────────────────────────────
# EventBus
# ─────────────────────────────────────────────────────────────

class EventBus:
    """
    进程内事件总线。

    Usage:
        bus = EventBus()

        # 订阅
        bus.subscribe("agent.status_changed", my_callback)
        bus.subscribe("agent.*", my_wildcard_callback)

        # 发布
        bus.publish("agent.status_changed", {"agent_id": "xxx", "new_status": "busy"})

        # 取消订阅
        bus.unsubscribe(subscription_id)
    """

    def __init__(self, history_size: int = 5000):
        self._subscriptions: list[Subscription] = []
        self._lock = threading.RLock()
        self._history: deque[Event] = deque(maxlen=history_size)
        self._paused = False
        # 异步分发线程池（避免 callback 阻塞 publisher）
        self._dispatch_pool: list[threading.Thread] = []

    def subscribe(self, pattern: str, callback: Callable[[Event], None],
                  subscriber_id: str = "") -> str:
        """
        订阅事件。

        Args:
            pattern:       topic 匹配模式，支持 fnmatch 通配符
                           如 "agent.*", "workflow.step_*", "*.completed"
            callback:      事件回调 fn(Event)
            subscriber_id: 订阅者标识（可选，用于管理）

        Returns:
            subscription_id
        """
        sub = Subscription(
            pattern=pattern,
            callback=callback,
            subscriber_id=subscriber_id,
        )
        with self._lock:
            self._subscriptions.append(sub)
        logger.debug(f"EventBus: subscribe '{pattern}' by {subscriber_id or sub.id}")
        return sub.id

    def unsubscribe(self, subscription_id: str) -> bool:
        """取消订阅。"""
        with self._lock:
            before = len(self._subscriptions)
            self._subscriptions = [
                s for s in self._subscriptions if s.id != subscription_id
            ]
            return len(self._subscriptions) < before

    def unsubscribe_all(self, subscriber_id: str) -> int:
        """取消某个订阅者的所有订阅。"""
        with self._lock:
            before = len(self._subscriptions)
            self._subscriptions = [
                s for s in self._subscriptions if s.subscriber_id != subscriber_id
            ]
            return before - len(self._subscriptions)

    def publish(self, topic: str, data: dict = None, source: str = ""):
        """
        发布事件。

        匹配所有符合 topic 模式的订阅，在后台线程中调用 callback。
        """
        if self._paused:
            return

        event = Event(topic=topic, data=data or {}, source=source)

        # 记录历史
        with self._lock:
            self._history.append(event)

        # 查找匹配的订阅
        with self._lock:
            matching = [
                s for s in self._subscriptions
                if fnmatch.fnmatch(topic, s.pattern)
            ]

        if not matching:
            return

        # 异步分发（不阻塞 publisher）
        for sub in matching:
            t = threading.Thread(
                target=self._safe_dispatch,
                args=(sub, event),
                daemon=True,
            )
            t.start()

    def publish_sync(self, topic: str, data: dict = None, source: str = ""):
        """同步发布事件（在当前线程中调用所有 callback）。"""
        if self._paused:
            return

        event = Event(topic=topic, data=data or {}, source=source)

        with self._lock:
            self._history.append(event)
            matching = [
                s for s in self._subscriptions
                if fnmatch.fnmatch(topic, s.pattern)
            ]

        for sub in matching:
            self._safe_dispatch(sub, event)

    def _safe_dispatch(self, sub: Subscription, event: Event):
        """安全地调用 callback，捕获所有异常。"""
        try:
            if sub.callback:
                sub.callback(event)
        except Exception as e:
            logger.error(
                f"EventBus dispatch error: topic={event.topic}, "
                f"subscriber={sub.subscriber_id}, error={e}",
                exc_info=True,
            )

    # ── 历史查询 ──

    def get_history(self, topic_filter: str = "*",
                    since: float = 0, limit: int = 100) -> list[dict]:
        """
        查询事件历史。

        Args:
            topic_filter: fnmatch 模式
            since:        时间戳过滤
            limit:        最大返回数
        """
        with self._lock:
            results = []
            for evt in reversed(self._history):
                if evt.timestamp < since:
                    break
                if fnmatch.fnmatch(evt.topic, topic_filter):
                    results.append(evt.to_dict())
                    if len(results) >= limit:
                        break
            return list(reversed(results))

    def get_subscriber_count(self, topic: str = "*") -> int:
        """获取匹配某 topic 的订阅者数量。"""
        with self._lock:
            return sum(1 for s in self._subscriptions
                       if fnmatch.fnmatch(topic, s.pattern))

    def list_subscriptions(self) -> list[dict]:
        """列出所有活跃订阅。"""
        with self._lock:
            return [
                {
                    "id": s.id,
                    "pattern": s.pattern,
                    "subscriber_id": s.subscriber_id,
                    "created_at": s.created_at,
                }
                for s in self._subscriptions
            ]

    def pause(self):
        """暂停事件分发。"""
        self._paused = True

    def resume(self):
        """恢复事件分发。"""
        self._paused = False

    def clear_history(self):
        """清空事件历史。"""
        with self._lock:
            self._history.clear()


# ─────────────────────────────────────────────────────────────
# 全局单例
# ─────────────────────────────────────────────────────────────

_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """获取全局 EventBus 单例。"""
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus


# ─────────────────────────────────────────────────────────────
# 便捷函数（供全局使用）
# ─────────────────────────────────────────────────────────────

def emit(topic: str, data: dict = None, source: str = ""):
    """快捷发布事件。"""
    get_event_bus().publish(topic, data, source)


def on(pattern: str, callback: Callable[[Event], None],
       subscriber_id: str = "") -> str:
    """快捷订阅事件。"""
    return get_event_bus().subscribe(pattern, callback, subscriber_id)


def off(subscription_id: str) -> bool:
    """快捷取消订阅。"""
    return get_event_bus().unsubscribe(subscription_id)
