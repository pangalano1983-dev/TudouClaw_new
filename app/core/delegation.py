"""
Delegation Protocol — Agent 间结构化委派协议。

取代旧的纯文本 agent.delegate(task_str) 方式，
提供结构化的任务描述、输入上下文、期望输出、超时、优先级等。

使用方式：
    req = DelegationRequest(
        from_agent="agent_a",
        to_agent="agent_b",
        task="Review this code for security issues",
        context=DelegationContext(text=code, files=[...]),
        expected_output="Security review report with severity ratings",
        priority=Priority.HIGH,
        timeout=300,
    )
    resp = delegation_manager.submit(req)
    # resp.status == "completed" / "rejected" / "timeout"
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger("tudou.delegation")


# ─────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────

class Priority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class DelegationStatus(str, Enum):
    PENDING = "pending"           # 等待接收方处理
    ACCEPTED = "accepted"         # 已接受，处理中
    COMPLETED = "completed"       # 已完成
    REJECTED = "rejected"         # 被拒绝
    TIMEOUT = "timeout"           # 超时
    CANCELLED = "cancelled"       # 被取消
    NEEDS_APPROVAL = "needs_approval"  # 需要审批


# ─────────────────────────────────────────────────────────────
# 委派上下文
# ─────────────────────────────────────────────────────────────

@dataclass
class DelegationContext:
    """委派任务的输入上下文（结构化）。"""
    text: str = ""                        # 主文本上下文
    files: list[dict] = field(default_factory=list)
    # [{path, name, type, description}]
    data: dict[str, Any] = field(default_factory=dict)
    # 结构化参数
    parent_task_id: str = ""              # 父任务 ID（如果来自 Workflow）
    project_id: str = ""                  # 关联项目 ID

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "files": self.files,
            "data": self.data,
            "parent_task_id": self.parent_task_id,
            "project_id": self.project_id,
        }

    @staticmethod
    def from_dict(d: dict | None) -> DelegationContext:
        if not d:
            return DelegationContext()
        return DelegationContext(
            text=d.get("text", ""),
            files=d.get("files", []),
            data=d.get("data", {}),
            parent_task_id=d.get("parent_task_id", ""),
            project_id=d.get("project_id", ""),
        )

    def to_prompt(self) -> str:
        """转为可嵌入 Prompt 的文本。"""
        parts = []
        if self.text:
            parts.append(self.text)
        if self.files:
            file_lines = [f"  - {f.get('name', '?')}: {f.get('description', '')}"
                          for f in self.files]
            parts.append("Related files:\n" + "\n".join(file_lines))
        if self.data:
            import json
            parts.append("Parameters:\n" + json.dumps(self.data, ensure_ascii=False, indent=2))
        return "\n\n".join(parts)


# ─────────────────────────────────────────────────────────────
# 委派请求 & 响应
# ─────────────────────────────────────────────────────────────

@dataclass
class DelegationRequest:
    """Agent 间的委派请求。"""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    from_agent: str = ""                  # 委派方 Agent ID
    to_agent: str = ""                    # 接收方 Agent ID
    task: str = ""                        # 任务描述
    context: DelegationContext = field(default_factory=DelegationContext)
    expected_output: str = ""             # 期望输出格式描述
    priority: Priority = Priority.NORMAL
    timeout: int = 300                    # 超时秒数 (0=无限)
    status: DelegationStatus = DelegationStatus.PENDING
    requires_approval: bool = False       # 是否需要人工审批
    # 创建时间
    created_at: float = field(default_factory=time.time)
    # 完成时间
    completed_at: float = 0
    # 响应
    result: str = ""                      # 执行结果
    result_data: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    # 等待通知
    _event: threading.Event = field(default_factory=threading.Event, repr=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "task": self.task,
            "context": self.context.to_dict(),
            "expected_output": self.expected_output,
            "priority": self.priority.value,
            "timeout": self.timeout,
            "status": self.status.value,
            "requires_approval": self.requires_approval,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "result": self.result[:2000] if self.result else "",
            "result_data": self.result_data,
            "error": self.error,
        }

    @staticmethod
    def from_dict(d: dict) -> DelegationRequest:
        return DelegationRequest(
            id=d.get("id", uuid.uuid4().hex[:12]),
            from_agent=d.get("from_agent", ""),
            to_agent=d.get("to_agent", ""),
            task=d.get("task", ""),
            context=DelegationContext.from_dict(d.get("context")),
            expected_output=d.get("expected_output", ""),
            priority=Priority(d.get("priority", "normal")),
            timeout=d.get("timeout", 300),
            status=DelegationStatus(d.get("status", "pending")),
            requires_approval=d.get("requires_approval", False),
            created_at=d.get("created_at", time.time()),
            completed_at=d.get("completed_at", 0),
            result=d.get("result", ""),
            result_data=d.get("result_data", {}),
            error=d.get("error", ""),
        )

    def build_prompt(self) -> str:
        """将委派请求转为发送给接收方 Agent 的 Prompt。"""
        parts = [f"## Delegated Task\n{self.task}"]
        if self.expected_output:
            parts.append(f"## Expected Output\n{self.expected_output}")
        ctx_text = self.context.to_prompt()
        if ctx_text:
            parts.append(f"## Context\n{ctx_text}")
        if self.priority in (Priority.HIGH, Priority.URGENT):
            parts.append(f"**Priority: {self.priority.value.upper()}**")
        return "\n\n".join(parts)


# ─────────────────────────────────────────────────────────────
# DelegationManager
# ─────────────────────────────────────────────────────────────

class DelegationManager:
    """
    管理 Agent 间委派请求的生命周期。

    需要注入：
        agent_chat_fn(agent_id: str, message: str) -> str
        approval_fn(req: DelegationRequest) -> bool (可选)
    """

    def __init__(self, agent_chat_fn: Callable[[str, str], str] = None,
                 event_bus=None):
        self._chat = agent_chat_fn
        self._bus = event_bus
        self._requests: dict[str, DelegationRequest] = {}
        self._lock = threading.RLock()
        # 审批回调（如果需要人工审批）
        self._approval_fn: Callable[[DelegationRequest], bool] | None = None

    def set_chat_fn(self, fn: Callable[[str, str], str]):
        self._chat = fn

    def set_approval_fn(self, fn: Callable[[DelegationRequest], bool]):
        self._approval_fn = fn

    def submit(self, req: DelegationRequest, blocking: bool = True) -> DelegationRequest:
        """
        提交委派请求。

        如果 blocking=True，阻塞等待结果（受 timeout 限制）。
        如果 blocking=False，立即返回，后续通过 get_request() 查询状态。
        """
        with self._lock:
            self._requests[req.id] = req

        # 发布事件
        if self._bus:
            self._bus.publish("delegation.requested", req.to_dict(), source=req.from_agent)

        # 审批检查
        if req.requires_approval:
            req.status = DelegationStatus.NEEDS_APPROVAL
            if self._bus:
                self._bus.publish("approval.requested", {
                    "type": "delegation",
                    "delegation_id": req.id,
                    "from_agent": req.from_agent,
                    "to_agent": req.to_agent,
                    "task": req.task,
                }, source=req.from_agent)
            if blocking:
                # 等待审批
                approved = req._event.wait(timeout=min(req.timeout, 600))
                if not approved:
                    req.status = DelegationStatus.TIMEOUT
                    return req
                if req.status == DelegationStatus.REJECTED:
                    return req

        # 执行委派
        if blocking:
            self._execute(req)
            return req
        else:
            t = threading.Thread(target=self._execute, args=(req,), daemon=True)
            t.start()
            return req

    def _execute(self, req: DelegationRequest):
        """执行委派（调用目标 Agent chat）。"""
        if not self._chat:
            req.status = DelegationStatus.REJECTED
            req.error = "No chat function configured"
            req._event.set()
            return

        req.status = DelegationStatus.ACCEPTED
        if self._bus:
            self._bus.publish("delegation.accepted", {
                "delegation_id": req.id,
                "to_agent": req.to_agent,
            }, source=req.to_agent)

        try:
            prompt = req.build_prompt()
            result = self._chat(req.to_agent, prompt)
            req.result = result
            req.status = DelegationStatus.COMPLETED
            req.completed_at = time.time()

            if self._bus:
                self._bus.publish("delegation.completed", {
                    "delegation_id": req.id,
                    "from_agent": req.from_agent,
                    "to_agent": req.to_agent,
                    "result_preview": result[:300],
                }, source=req.to_agent)

        except Exception as e:
            req.status = DelegationStatus.REJECTED
            req.error = str(e)
            req.completed_at = time.time()

            if self._bus:
                self._bus.publish("delegation.failed", {
                    "delegation_id": req.id,
                    "error": str(e),
                }, source=req.to_agent)

        finally:
            req._event.set()

    def approve_delegation(self, delegation_id: str) -> bool:
        """审批通过委派请求。"""
        req = self._requests.get(delegation_id)
        if not req or req.status != DelegationStatus.NEEDS_APPROVAL:
            return False
        req.status = DelegationStatus.PENDING
        req._event.set()
        if self._bus:
            self._bus.publish("approval.decided", {
                "type": "delegation",
                "delegation_id": delegation_id,
                "decision": "approved",
            })
        return True

    def reject_delegation(self, delegation_id: str, reason: str = "") -> bool:
        """拒绝委派请求。"""
        req = self._requests.get(delegation_id)
        if not req or req.status != DelegationStatus.NEEDS_APPROVAL:
            return False
        req.status = DelegationStatus.REJECTED
        req.error = reason or "Delegation rejected"
        req._event.set()
        if self._bus:
            self._bus.publish("approval.decided", {
                "type": "delegation",
                "delegation_id": delegation_id,
                "decision": "rejected",
                "reason": reason,
            })
        return True

    def cancel(self, delegation_id: str) -> bool:
        """取消委派。"""
        req = self._requests.get(delegation_id)
        if not req or req.status in (DelegationStatus.COMPLETED, DelegationStatus.CANCELLED):
            return False
        req.status = DelegationStatus.CANCELLED
        req._event.set()
        return True

    def get_request(self, delegation_id: str) -> DelegationRequest | None:
        return self._requests.get(delegation_id)

    def list_requests(self, agent_id: str = "", status: str = "") -> list[dict]:
        """列出委派请求。"""
        with self._lock:
            results = []
            for req in self._requests.values():
                if agent_id and req.from_agent != agent_id and req.to_agent != agent_id:
                    continue
                if status and req.status.value != status:
                    continue
                results.append(req.to_dict())
            return results

    def get_stats(self) -> dict:
        """统计信息。"""
        with self._lock:
            total = len(self._requests)
            by_status = {}
            for req in self._requests.values():
                s = req.status.value
                by_status[s] = by_status.get(s, 0) + 1
            return {"total": total, "by_status": by_status}
