"""
MessageBus — inter-agent message routing, delivery, and broadcast.

Migrated from ``Hub._core`` into its own manager module.

Target methods (from Hub):
    send_message, route_message, broadcast,
    get_messages, _deliver_local, _deliver_remote,
    _load_messages, _save_message, _update_message_status
"""
from __future__ import annotations

import logging
import threading

from .manager_base import ManagerBase
from .types import AgentMessage

logger = logging.getLogger("tudou.hub.message_bus")


class MessageBus(ManagerBase):
    """Routes and delivers messages between agents (local and remote)."""

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _load_messages(self):
        """Load inter-agent messages from SQLite on startup."""
        if self._db:
            try:
                rows = self._db.load_messages(limit=3000)
                for d in rows:
                    msg = AgentMessage(
                        id=d.get("id", ""),
                        from_agent=d.get("from_agent", ""),
                        to_agent=d.get("to_agent", ""),
                        from_agent_name=d.get("from_agent_name", ""),
                        to_agent_name=d.get("to_agent_name", ""),
                        content=d.get("content", ""),
                        msg_type=d.get("msg_type", "task"),
                        timestamp=d.get("timestamp", 0),
                        status=d.get("status", "pending"),
                    )
                    self._hub.messages.append(msg)
                # Reverse so oldest first (DB returns newest first)
                self._hub.messages.reverse()
                logger.info("Loaded %d agent messages from SQLite",
                            len(self._hub.messages))
            except Exception as e:
                logger.warning("Failed to load agent messages: %s", e)

    def _save_message(self, msg: AgentMessage):
        """Persist a single message to SQLite."""
        if self._db:
            try:
                self._db.save_message(msg.to_dict())
            except Exception as e:
                logger.warning("Failed to save message %s: %s", msg.id, e)

    def _update_message_status(self, msg: AgentMessage):
        """Update message status in SQLite."""
        if self._db:
            try:
                self._db.update_message_status(msg.id, msg.status)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Send / Route
    # ------------------------------------------------------------------

    def send_message(self, from_agent: str, to_agent: str, content: str,
                     msg_type: str = "task") -> AgentMessage:
        # Resolve display names from agent registry
        _from_a = self.agents.get(from_agent)
        _to_a = self.agents.get(to_agent)
        _from_name = f"{_from_a.role}-{_from_a.name}" if _from_a else from_agent
        _to_name = f"{_to_a.role}-{_to_a.name}" if _to_a else to_agent
        msg = AgentMessage(
            from_agent=from_agent, to_agent=to_agent,
            from_agent_name=_from_name, to_agent_name=_to_name,
            content=content, msg_type=msg_type,
        )
        with self._lock:
            self._hub.messages.append(msg)
            if len(self._hub.messages) > 5000:
                self._hub.messages = self._hub.messages[-3000:]
        # Persist to DB
        self._save_message(msg)

        # ---- Central audit: every cross-agent message is logged ----
        try:
            from ..auth import get_auth as _get_auth
            _auth = _get_auth()
            if _auth is not None:
                _auth.audit(
                    action="agent_message",
                    actor=from_agent or "system",
                    target=to_agent or "broadcast",
                    detail=f"[{msg_type}] {content[:300]}",
                )
        except Exception as _aud_err:
            logger.debug("audit skipped for send_message: %s", _aud_err)

        if to_agent in self.agents:
            self._deliver_local(msg)
        else:
            threading.Thread(target=self._deliver_remote, args=(msg,),
                             daemon=True).start()
        return msg

    def route_message(self, from_agent: str, to_agent: str, content: str,
                      msg_type: str = "task", source: str = "api",
                      metadata: dict | None = None) -> AgentMessage | None:
        """Canonical entry point for all inter-agent messages.

        Phase-1 responsibilities:
        1. Validate that the sender/target exist (if not 'user'/'system').
        2. Audit the routing request with explicit `source` + `metadata`.
        3. Delegate actual delivery to `send_message`, which persists and
           fires local or remote dispatch.

        All new code paths that need to send an agent-to-agent message should
        go through this method instead of `send_message` or direct
        `agent.delegate()` invocations.
        """
        # Basic validation -- allow "user"/"system"/"admin" pseudo-senders.
        _pseudo = {"user", "system", "admin", "hub", "orchestrator", "workflow"}
        if from_agent and from_agent not in _pseudo and from_agent not in self.agents:
            logger.warning("route_message: unknown sender %s", from_agent)
        if to_agent and to_agent not in self.agents and not self._hub.find_agent_node(to_agent):
            logger.warning("route_message: unknown target %s", to_agent)
            try:
                from ..auth import get_auth as _get_auth
                _a = _get_auth()
                if _a is not None:
                    _a.audit(
                        action="agent_message_rejected",
                        actor=from_agent or "system",
                        target=to_agent or "",
                        detail=f"unknown_target source={source}",
                        success=False,
                    )
            except Exception:
                pass
            return None

        # Structured routing audit (distinct from send_message's audit)
        try:
            from ..auth import get_auth as _get_auth
            _a = _get_auth()
            if _a is not None:
                _detail = f"source={source} type={msg_type} len={len(content)}"
                if metadata:
                    try:
                        import json as _json
                        _detail += " meta=" + _json.dumps(metadata, ensure_ascii=False)[:200]
                    except Exception:
                        pass
                _a.audit(
                    action="agent_route",
                    actor=from_agent or "system",
                    target=to_agent or "",
                    detail=_detail,
                )
        except Exception as _e:
            logger.debug("route_message audit skipped: %s", _e)

        return self.send_message(from_agent, to_agent, content, msg_type=msg_type)

    # ------------------------------------------------------------------
    # Delivery (local / remote)
    # ------------------------------------------------------------------

    def _deliver_local(self, msg: AgentMessage):
        agent = self.agents.get(msg.to_agent)
        if not agent:
            msg.status = "error"
            self._update_message_status(msg)
            return
        msg.status = "delivered"
        self._update_message_status(msg)

        def _run():
            result = agent.delegate(msg.content, from_agent=msg.from_agent)
            msg.status = "completed"
            self._update_message_status(msg)
            if msg.from_agent:
                self.send_message(msg.to_agent, msg.from_agent, result,
                                  msg_type="result")

        threading.Thread(target=_run, daemon=True).start()

    def _deliver_remote(self, msg: AgentMessage):
        import requests as http_requests

        node = self._hub.find_agent_node(msg.to_agent)
        if not node or not node.url:
            msg.status = "error"
            self._update_message_status(msg)
            return
        try:
            headers = {"Content-Type": "application/json"}
            if node.secret:
                headers["X-Claw-Secret"] = node.secret
            http_requests.post(
                f"{node.url}/api/hub/deliver",
                headers=headers,
                json=msg.to_dict(),
                timeout=30,
            )
            msg.status = "delivered"
        except Exception:
            msg.status = "error"
        self._update_message_status(msg)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_messages(self, agent_id: str = "", limit: int = 50) -> list[dict]:
        with self._lock:
            entries = self._hub.messages
            if agent_id:
                entries = [m for m in entries
                           if m.from_agent == agent_id or m.to_agent == agent_id]
            return [m.to_dict() for m in entries[-limit:]]

    # ------------------------------------------------------------------
    # Broadcast
    # ------------------------------------------------------------------

    def broadcast(self, content: str, from_agent: str = "hub") -> list[AgentMessage]:
        msgs = []
        for aid in list(self.agents.keys()):
            if aid != from_agent:
                msgs.append(self.send_message(from_agent, aid, content,
                                              msg_type="broadcast"))
        return msgs
