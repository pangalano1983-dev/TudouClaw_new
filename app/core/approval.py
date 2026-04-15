"""
ApprovalGate — 多级审批门控系统。

扩展原有的 ToolPolicy（仅工具级审批）为全面的审批框架：

审批类型：
  1. tool_execution    — 危险工具调用（现有，与 ToolPolicy 兼容）
  2. delegation        — Agent 间委派
  3. workflow_step     — Workflow 步骤执行
  4. task_completion   — 任务完成确认
  5. resource_access   — 资源访问（文件/API/数据库）

审批策略：
  - auto        — 自动通过
  - human       — 需要人工审批
  - agent       — 由上级 Agent 审批
  - conditional — 条件审批（满足条件自动通过，否则人工）

审批流程：
  发起方 → ApprovalGate.request() → 根据策略路由
    → auto: 立即通过
    → human: 创建 PendingApproval，等待管理员操作
    → agent: 委派给审批 Agent，等待响应
    → conditional: 评估条件，决定 auto 还是 human
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger("tudou.approval")


# ─────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────

class ApprovalType(str, Enum):
    TOOL_EXECUTION = "tool_execution"
    DELEGATION = "delegation"
    WORKFLOW_STEP = "workflow_step"
    TASK_COMPLETION = "task_completion"
    RESOURCE_ACCESS = "resource_access"


class ApprovalStrategy(str, Enum):
    AUTO = "auto"
    HUMAN = "human"
    AGENT = "agent"
    CONDITIONAL = "conditional"


class ApprovalDecision(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"


# ─────────────────────────────────────────────────────────────
# 审批请求
# ─────────────────────────────────────────────────────────────

@dataclass
class ApprovalRequest:
    """一个审批请求。"""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    approval_type: ApprovalType = ApprovalType.TOOL_EXECUTION
    requester_id: str = ""                # 发起方 (agent_id)
    target_id: str = ""                   # 目标 (agent_id, workflow_step_id, etc.)
    action: str = ""                      # 请求的操作描述
    details: dict[str, Any] = field(default_factory=dict)
    # 附加信息
    decision: ApprovalDecision = ApprovalDecision.PENDING
    decided_by: str = ""                  # 审批者 (admin_user, agent_id)
    decision_reason: str = ""
    strategy: ApprovalStrategy = ApprovalStrategy.HUMAN
    # 时间
    created_at: float = field(default_factory=time.time)
    decided_at: float = 0
    expires_at: float = 0                 # 过期时间 (0=不过期)
    # 等待机制
    _event: threading.Event = field(default_factory=threading.Event, repr=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "approval_type": self.approval_type.value,
            "requester_id": self.requester_id,
            "target_id": self.target_id,
            "action": self.action,
            "details": self.details,
            "decision": self.decision.value,
            "decided_by": self.decided_by,
            "decision_reason": self.decision_reason,
            "strategy": self.strategy.value,
            "created_at": self.created_at,
            "decided_at": self.decided_at,
            "expires_at": self.expires_at,
        }

    @staticmethod
    def from_dict(d: dict) -> ApprovalRequest:
        return ApprovalRequest(
            id=d.get("id", uuid.uuid4().hex[:12]),
            approval_type=ApprovalType(d.get("approval_type", "tool_execution")),
            requester_id=d.get("requester_id", ""),
            target_id=d.get("target_id", ""),
            action=d.get("action", ""),
            details=d.get("details", {}),
            decision=ApprovalDecision(d.get("decision", "pending")),
            decided_by=d.get("decided_by", ""),
            decision_reason=d.get("decision_reason", ""),
            strategy=ApprovalStrategy(d.get("strategy", "human")),
            created_at=d.get("created_at", time.time()),
            decided_at=d.get("decided_at", 0),
            expires_at=d.get("expires_at", 0),
        )


# ─────────────────────────────────────────────────────────────
# 审批策略规则
# ─────────────────────────────────────────────────────────────

@dataclass
class ApprovalRule:
    """定义某种操作的审批策略。"""
    approval_type: ApprovalType = ApprovalType.TOOL_EXECUTION
    pattern: str = "*"                    # 匹配模式 (工具名、步骤名等)
    strategy: ApprovalStrategy = ApprovalStrategy.AUTO
    agent_approver: str = ""              # 如果 strategy=agent，指定审批 Agent
    condition_fn: Callable[[dict], bool] | None = None
    # 如果 strategy=conditional, 返回 True=auto, False=human
    timeout: int = 300                    # 等待超时 (秒)

    def to_dict(self) -> dict:
        return {
            "approval_type": self.approval_type.value,
            "pattern": self.pattern,
            "strategy": self.strategy.value,
            "agent_approver": self.agent_approver,
            "timeout": self.timeout,
        }


# ─────────────────────────────────────────────────────────────
# ApprovalGate
# ─────────────────────────────────────────────────────────────

class ApprovalGate:
    """
    多级审批门控。

    支持为不同类型的操作配置不同的审批策略。
    与 EventBus 集成，审批事件自动发布。
    """

    def __init__(self, event_bus=None):
        self._bus = event_bus
        self._rules: list[ApprovalRule] = []
        self._pending: dict[str, ApprovalRequest] = {}
        self._history: list[ApprovalRequest] = []
        self._lock = threading.RLock()
        # 默认规则
        self._init_default_rules()

    def _init_default_rules(self):
        """初始化默认审批规则。"""
        import fnmatch as _fm
        # 工具审批：危险工具需人工
        self._rules.extend([
            ApprovalRule(
                approval_type=ApprovalType.TOOL_EXECUTION,
                pattern="bash",
                strategy=ApprovalStrategy.HUMAN,
                timeout=300,
            ),
            ApprovalRule(
                approval_type=ApprovalType.TOOL_EXECUTION,
                pattern="write_file",
                strategy=ApprovalStrategy.HUMAN,
                timeout=300,
            ),
            ApprovalRule(
                approval_type=ApprovalType.TOOL_EXECUTION,
                pattern="edit_file",
                strategy=ApprovalStrategy.HUMAN,
                timeout=300,
            ),
            # 委派：默认自动通过
            ApprovalRule(
                approval_type=ApprovalType.DELEGATION,
                pattern="*",
                strategy=ApprovalStrategy.AUTO,
            ),
            # Workflow 步骤：默认自动
            ApprovalRule(
                approval_type=ApprovalType.WORKFLOW_STEP,
                pattern="*",
                strategy=ApprovalStrategy.AUTO,
            ),
            # 任务完成：默认自动
            ApprovalRule(
                approval_type=ApprovalType.TASK_COMPLETION,
                pattern="*",
                strategy=ApprovalStrategy.AUTO,
            ),
            # 资源访问：默认自动
            ApprovalRule(
                approval_type=ApprovalType.RESOURCE_ACCESS,
                pattern="*",
                strategy=ApprovalStrategy.AUTO,
            ),
        ])

    def add_rule(self, rule: ApprovalRule):
        """添加审批规则（优先级高于默认规则，先匹配先生效）。"""
        with self._lock:
            # 插入到列表前面，优先匹配
            self._rules.insert(0, rule)

    def remove_rule(self, approval_type: ApprovalType, pattern: str) -> bool:
        """移除特定规则。"""
        with self._lock:
            before = len(self._rules)
            self._rules = [
                r for r in self._rules
                if not (r.approval_type == approval_type and r.pattern == pattern)
            ]
            return len(self._rules) < before

    def get_rules(self) -> list[dict]:
        """列出所有规则。"""
        with self._lock:
            return [r.to_dict() for r in self._rules]

    def request(self, approval_type: ApprovalType, requester_id: str,
                action: str, details: dict = None,
                target_id: str = "", blocking: bool = True) -> ApprovalRequest:
        """
        发起审批请求。

        根据规则自动路由到正确的审批策略。

        Returns:
            ApprovalRequest，decision 字段包含结果。
        """
        import fnmatch

        # 查找匹配的规则
        rule = None
        with self._lock:
            for r in self._rules:
                if r.approval_type == approval_type:
                    if fnmatch.fnmatch(action, r.pattern):
                        rule = r
                        break

        if not rule:
            # 无匹配规则 → 默认自动通过
            req = ApprovalRequest(
                approval_type=approval_type,
                requester_id=requester_id,
                target_id=target_id,
                action=action,
                details=details or {},
                decision=ApprovalDecision.APPROVED,
                decided_by="system",
                decision_reason="No matching rule (auto-approved)",
                strategy=ApprovalStrategy.AUTO,
            )
            return req

        # 创建请求
        req = ApprovalRequest(
            approval_type=approval_type,
            requester_id=requester_id,
            target_id=target_id,
            action=action,
            details=details or {},
            strategy=rule.strategy,
            expires_at=time.time() + rule.timeout if rule.timeout > 0 else 0,
        )

        # 根据策略路由
        if rule.strategy == ApprovalStrategy.AUTO:
            req.decision = ApprovalDecision.APPROVED
            req.decided_by = "system"
            req.decided_at = time.time()
            req.decision_reason = "Auto-approved by rule"
            return req

        elif rule.strategy == ApprovalStrategy.CONDITIONAL:
            if rule.condition_fn and rule.condition_fn(details or {}):
                req.decision = ApprovalDecision.APPROVED
                req.decided_by = "system"
                req.decided_at = time.time()
                req.decision_reason = "Condition met (auto-approved)"
                return req
            # 条件不满足 → 降级为人工审批

        # 需要等待（human 或 agent 或 conditional 降级）
        with self._lock:
            self._pending[req.id] = req

        if self._bus:
            self._bus.publish("approval.requested", req.to_dict(), source=requester_id)

        if rule.strategy == ApprovalStrategy.AGENT and rule.agent_approver:
            # 发起 Agent 审批（异步）
            self._request_agent_approval(req, rule.agent_approver)

        if blocking:
            timeout = rule.timeout if rule.timeout > 0 else 300
            decided = req._event.wait(timeout=timeout)
            if not decided:
                req.decision = ApprovalDecision.EXPIRED
                req.decided_at = time.time()
                req.decision_reason = f"Timed out after {timeout}s"
                with self._lock:
                    self._pending.pop(req.id, None)
                    self._history.append(req)

        return req

    def decide(self, approval_id: str, approved: bool,
               decided_by: str = "admin", reason: str = "") -> bool:
        """
        对挂起的审批请求做出决定。

        Args:
            approval_id: 审批请求 ID
            approved:    True=通过, False=拒绝
            decided_by:  决定者标识
            reason:      决定原因
        """
        with self._lock:
            req = self._pending.pop(approval_id, None)
            if not req:
                return False

            req.decision = ApprovalDecision.APPROVED if approved else ApprovalDecision.DENIED
            req.decided_by = decided_by
            req.decided_at = time.time()
            req.decision_reason = reason or ("Approved" if approved else "Denied")
            self._history.append(req)

        req._event.set()

        if self._bus:
            self._bus.publish("approval.decided", {
                "approval_id": approval_id,
                "approval_type": req.approval_type.value,
                "decision": req.decision.value,
                "decided_by": decided_by,
            }, source=decided_by)

        return True

    def _request_agent_approval(self, req: ApprovalRequest, approver_agent_id: str):
        """委托给 Agent 进行审批。"""
        # 这里只是发事件，实际的 Agent 审批逻辑由 Hub 监听 EventBus 处理
        if self._bus:
            self._bus.publish("approval.agent_review", {
                "approval_id": req.id,
                "approver_agent_id": approver_agent_id,
                "action": req.action,
                "details": req.details,
            }, source="approval_gate")

    # ── 查询 ──

    def list_pending(self, approval_type: str = "") -> list[dict]:
        """列出所有挂起的审批。"""
        with self._lock:
            results = []
            for req in self._pending.values():
                if approval_type and req.approval_type.value != approval_type:
                    continue
                results.append(req.to_dict())
            return results

    def list_history(self, limit: int = 100) -> list[dict]:
        """列出审批历史。"""
        with self._lock:
            return [r.to_dict() for r in self._history[-limit:]]

    def get_stats(self) -> dict:
        """审批统计。"""
        with self._lock:
            pending = len(self._pending)
            history_total = len(self._history)
            approved = sum(1 for r in self._history
                           if r.decision == ApprovalDecision.APPROVED)
            denied = sum(1 for r in self._history
                          if r.decision == ApprovalDecision.DENIED)
            expired = sum(1 for r in self._history
                           if r.decision == ApprovalDecision.EXPIRED)
            return {
                "pending": pending,
                "total_decided": history_total,
                "approved": approved,
                "denied": denied,
                "expired": expired,
            }
