"""
NodeManager — remote node registration, proxy, refresh, and config sync.

Migrated from ``Hub._core`` into a standalone manager that inherits
:class:`ManagerBase` for shared-state access.

Target methods (from Hub):
    register_node, unregister_node, update_node_agents, list_nodes,
    refresh_node, refresh_all_nodes, find_agent_node, is_local_agent,
    proxy_remote_agent_get, proxy_remote_agent_post,
    proxy_chat, proxy_chat_sync, proxy_clear, proxy_events,
    proxy_approvals, proxy_approve, proxy_update_model,
    apply_config_to_local_agent, dispatch_config, confirm_config_applied,
    batch_dispatch_config, get_deployment_status, get_node_config_status,
    set_node_config_item, get_node_config, get_node_config_item,
    delete_node_config_item, list_all_node_configs,
    sync_node_config, apply_received_node_config
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, TYPE_CHECKING

import requests as http_requests

from .manager_base import ManagerBase
from .types import (
    RemoteNode,
    AgentConfigPayload,
    ConfigDeployment,
)

if TYPE_CHECKING:
    from ._core import Hub

logger = logging.getLogger("tudou.hub.node_manager")


class NodeManager(ManagerBase):
    """Manages remote node registration, proxy calls, and config deployment."""

    # ------------------------------------------------------------------
    # Find which node owns an agent
    # ------------------------------------------------------------------

    def find_agent_node(self, agent_id: str) -> RemoteNode | None:
        """Find the remote node that hosts a given agent."""
        for node in self.remote_nodes.values():
            for ra in node.agents:
                if ra.get("id") == agent_id:
                    return node
        return None

    def is_local_agent(self, agent_id: str) -> bool:
        return agent_id in self.agents

    # ------------------------------------------------------------------
    # Remote node management
    # ------------------------------------------------------------------

    def register_node(self, node_id: str, name: str, url: str,
                      agents: list[dict] = None,
                      secret: str = "") -> RemoteNode:
        logger.info("HUB register_node: id=%s name=%s url=%s agents=%d has_secret=%s",
                     node_id, name, url, len(agents or []), bool(secret))
        node = RemoteNode(
            node_id=node_id, name=name, url=url.rstrip("/") if url else "",
            agents=agents or [], last_seen=time.time(),
            secret=secret,
        )
        with self._lock:
            self.remote_nodes[node_id] = node
        self._hub._save_remote_nodes()
        logger.info("HUB register_node OK: %s now has %d remote nodes",
                     node_id, len(self.remote_nodes))
        return node

    def unregister_node(self, node_id: str):
        with self._lock:
            self.remote_nodes.pop(node_id, None)
        self._hub._save_remote_nodes()

    def update_node_agents(self, node_id: str, agents: list[dict]):
        with self._lock:
            if node_id in self.remote_nodes:
                self.remote_nodes[node_id].agents = agents
                self.remote_nodes[node_id].last_seen = time.time()
                self.remote_nodes[node_id].status = "online"
        self._hub._save_remote_nodes()

    def list_nodes(self) -> list[dict]:
        result = [{
            "node_id": self._hub.node_id,
            "name": self._hub.node_name,
            "url": "local",
            "agent_count": len(self.agents),
            "status": "online",
            "is_self": True,
        }]
        for n in self.remote_nodes.values():
            d = n.to_dict()
            d["is_self"] = False
            result.append(d)
        return result

    # ------------------------------------------------------------------
    # Remote node health check
    # ------------------------------------------------------------------

    def refresh_node(self, node_id: str) -> bool:
        node = self.remote_nodes.get(node_id)
        if not node or not node.url:
            logger.warning("HUB refresh_node: node %s not found or no url", node_id)
            return False
        try:
            headers = {}
            if node.secret:
                headers["X-Claw-Secret"] = node.secret
            url = f"{node.url}/api/hub/agents"
            logger.debug("HUB refresh_node: GET %s", url)
            resp = http_requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            node.agents = data.get("agents", [])
            node.last_seen = time.time()
            node.status = "online"
            logger.info("HUB refresh_node OK: %s agents=%d", node_id, len(node.agents))
            return True
        except Exception as e:
            node.status = "error"
            logger.error("HUB refresh_node FAIL: %s error=%s", node_id, e)
            return False

    def refresh_all_nodes(self):
        for nid in list(self.remote_nodes.keys()):
            self.refresh_node(nid)

    # ------------------------------------------------------------------
    # Proxy GET / POST for remote agents
    # ------------------------------------------------------------------

    def proxy_remote_agent_get(self, agent_id: str, sub_path: str) -> dict | None:
        """Proxy a GET request for a remote agent to its host node.
        sub_path e.g. '/events', '/tasks', '/cost'"""
        node = self.find_agent_node(agent_id)
        if not node:
            return None
        try:
            headers = {}
            if node.secret:
                headers["X-Claw-Secret"] = node.secret
            url = f"{node.url}/api/portal/agent/{agent_id}{sub_path}"
            logger.debug("PROXY GET %s", url)
            resp = http_requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                return resp.json()
            logger.warning("PROXY GET %s -> %s", url, resp.status_code)
            return None
        except Exception as e:
            logger.error("PROXY GET failed: %s -> %s", agent_id, e)
            return None

    def proxy_remote_agent_post(self, agent_id: str, sub_path: str, body: dict) -> dict | None:
        """Proxy a POST request for a remote agent to its host node."""
        node = self.find_agent_node(agent_id)
        if not node:
            return None
        try:
            headers = {"Content-Type": "application/json"}
            if node.secret:
                headers["X-Claw-Secret"] = node.secret
            url = f"{node.url}/api/portal/agent/{agent_id}{sub_path}"
            logger.debug("PROXY POST %s", url)
            resp = http_requests.post(url, headers=headers, json=body, timeout=15)
            if resp.status_code == 200:
                return resp.json()
            logger.warning("PROXY POST %s -> %s: %s", url, resp.status_code, resp.text[:200])
            return None
        except Exception as e:
            logger.error("PROXY POST failed: %s -> %s", agent_id, e)
            return None

    # ------------------------------------------------------------------
    # Config deployment (Hub -> Node -> Agent)
    # ------------------------------------------------------------------

    def apply_config_to_local_agent(self, agent_id: str,
                                     config: AgentConfigPayload) -> bool:
        """Apply a config payload to a local agent. Returns True if applied."""
        agent = self.agents.get(agent_id)
        if not agent:
            return False
        if config.name:
            agent.name = config.name
        if config.role:
            agent.role = config.role
        if config.model:
            agent.model = config.model
        if config.provider:
            agent.provider = config.provider
        if config.system_prompt:
            agent.system_prompt = config.system_prompt
        if config.working_dir:
            agent.working_dir = config.working_dir
        if config.profile:
            from ..agent import AgentProfile
            if config.partial:
                # Merge: only overwrite non-empty fields
                current = agent.profile.to_dict()
                for k, v in config.profile.items():
                    if v or v == 0 or v is False:
                        current[k] = v
                agent.profile = AgentProfile.from_dict(current)
            else:
                agent.profile = AgentProfile.from_dict(config.profile)
        # Reset system message so it rebuilds on next chat
        if agent.messages and agent.messages[0].get("role") == "system":
            agent.messages[0] = {"role": "system",
                                  "content": agent._build_system_prompt()}
        agent.history_log.add("config_applied",
                              f"fields: {','.join(k for k, v in config.to_dict().items() if v and k not in ('agent_id', 'partial'))}")
        self._hub._save_agents()
        return True

    def dispatch_config(self, node_id: str, agent_id: str,
                        config: AgentConfigPayload) -> ConfigDeployment:
        """
        Push config to an agent on any node.
        - Local node: apply immediately
        - Remote node: HTTP POST to node, track deployment status
        """
        logger.info("HUB dispatch_config: node=%s agent=%s", node_id, agent_id)
        deployment = ConfigDeployment(
            node_id=node_id,
            agent_id=agent_id,
            config=config.to_dict(),
        )
        config.agent_id = agent_id

        with self._lock:
            self._hub.config_deployments[deployment.deploy_id] = deployment

        # Local node -- apply immediately
        if node_id in ("local", self._hub.node_id, ""):
            deployment.status = "dispatched"
            deployment.dispatched_at = time.time()
            ok = self.apply_config_to_local_agent(agent_id, config)
            if ok:
                deployment.status = "applied"
                deployment.applied_at = time.time()
                logger.info("HUB dispatch_config local OK: deploy=%s", deployment.deploy_id)
            else:
                deployment.status = "failed"
                deployment.error = "Agent not found or apply failed"
                logger.error("HUB dispatch_config local FAIL: agent=%s", agent_id)
            return deployment

        # Remote node -- push via HTTP
        node = self.remote_nodes.get(node_id)
        if not node or not node.url:
            deployment.status = "failed"
            deployment.error = f"Node '{node_id}' not found or no URL"
            logger.error("HUB dispatch_config: node %s not found", node_id)
            return deployment

        deployment.status = "dispatched"
        deployment.dispatched_at = time.time()

        def _push():
            target_url = f"{node.url}/api/hub/apply-config"
            try:
                headers = {"Content-Type": "application/json"}
                if node.secret:
                    headers["X-Claw-Secret"] = node.secret
                logger.info("HUB dispatch_config -> POST %s", target_url)
                resp = http_requests.post(
                    target_url,
                    headers=headers,
                    json={
                        "deploy_id": deployment.deploy_id,
                        "agent_id": agent_id,
                        "config": config.to_dict(),
                    },
                    timeout=30,
                )
                logger.info("HUB dispatch_config <- status=%s body=%s",
                            resp.status_code, resp.text[:300])
                resp.raise_for_status()
                data = resp.json()
                if data.get("ok"):
                    deployment.status = "ack"
                    deployment.acked_at = time.time()
                    if data.get("applied"):
                        deployment.status = "applied"
                        deployment.applied_at = time.time()
                    logger.info("HUB dispatch_config remote OK: deploy=%s status=%s",
                                deployment.deploy_id, deployment.status)
                else:
                    deployment.status = "failed"
                    deployment.error = data.get("error", "Unknown error")
                    logger.error("HUB dispatch_config remote FAIL: %s", deployment.error)
            except Exception as e:
                deployment.status = "failed"
                deployment.error = str(e)
                logger.exception("HUB dispatch_config EXCEPTION: %s -> %s", target_url, e)

        threading.Thread(target=_push, daemon=True).start()
        return deployment

    def confirm_config_applied(self, deploy_id: str, success: bool = True,
                                error: str = "") -> bool:
        """Called by remote node to confirm config was loaded successfully."""
        dep = self._hub.config_deployments.get(deploy_id)
        if not dep:
            return False
        if success:
            dep.status = "applied"
            dep.applied_at = time.time()
        else:
            dep.status = "failed"
            dep.error = error
        return True

    def batch_dispatch_config(self, configs: list[dict]) -> list[ConfigDeployment]:
        """
        Deploy configs to multiple agents across multiple nodes.
        configs: [{"node_id": ..., "agent_id": ..., "config": {...}}, ...]
        """
        deployments = []
        for item in configs:
            node_id = item.get("node_id", "local")
            agent_id = item.get("agent_id", "")
            cfg = AgentConfigPayload.from_dict(item.get("config", {}))
            dep = self.dispatch_config(node_id, agent_id, cfg)
            deployments.append(dep)
        return deployments

    def get_deployment_status(self, deploy_id: str = "") -> dict | list:
        """Get deployment status. If deploy_id given, return one; else return all."""
        if deploy_id:
            dep = self._hub.config_deployments.get(deploy_id)
            return dep.to_dict() if dep else {}
        # Return all, sorted by created_at desc
        deps = sorted(self._hub.config_deployments.values(),
                       key=lambda d: d.created_at, reverse=True)
        return [d.to_dict() for d in deps[:100]]

    def get_node_config_status(self, node_id: str) -> dict:
        """Get all config deployments for a specific node, with summary."""
        deps = [d for d in self._hub.config_deployments.values()
                if d.node_id == node_id]
        deps.sort(key=lambda d: d.created_at, reverse=True)
        return {
            "node_id": node_id,
            "total": len(deps),
            "applied": sum(1 for d in deps if d.status == "applied"),
            "pending": sum(1 for d in deps if d.status in ("pending", "dispatched", "ack")),
            "failed": sum(1 for d in deps if d.status == "failed"),
            "deployments": [d.to_dict() for d in deps[:50]],
        }

    # ------------------------------------------------------------------
    # Proxy chat to remote agent
    # ------------------------------------------------------------------

    def proxy_chat(self, agent_id: str, message: str) -> Any:
        """
        Send a chat message to a remote agent.
        Returns a requests.Response (SSE stream) or None.
        """
        node = self.find_agent_node(agent_id)
        if not node or not node.url:
            return None
        try:
            headers = {"Content-Type": "application/json"}
            if node.secret:
                headers["X-Claw-Secret"] = node.secret
            resp = http_requests.post(
                f"{node.url}/api/agent/chat",
                headers=headers,
                json={"message": message},
                stream=True,
                timeout=300,
            )
            resp.raise_for_status()
            return resp
        except Exception:
            return None

    def proxy_chat_sync(self, agent_id: str, node: RemoteNode,
                         message: str) -> str:
        """同步调用远程 agent，收集完整文本结果（用于 workflow）。"""
        try:
            headers = {"Content-Type": "application/json"}
            if node.secret:
                headers["X-Claw-Secret"] = node.secret
            resp = http_requests.post(
                f"{node.url}/api/agent/chat",
                headers=headers,
                json={"message": message},
                stream=True,
                timeout=600,
            )
            resp.raise_for_status()
            # Collect SSE text events
            full_text = ""
            for line in resp.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    import json as _json
                    evt = _json.loads(data)
                    if evt.get("type") == "text_delta":
                        full_text += evt.get("content", "")
                    elif evt.get("type") == "text":
                        full_text = evt.get("content", "")
                except Exception:
                    pass
            return full_text or "(no response)"
        except Exception as e:
            raise ValueError(f"Remote chat failed: {e}")

    def proxy_clear(self, agent_id: str) -> bool:
        node = self.find_agent_node(agent_id)
        if not node or not node.url:
            return False
        try:
            headers = {}
            if node.secret:
                headers["X-Claw-Secret"] = node.secret
            http_requests.post(
                f"{node.url}/api/agent/clear",
                headers=headers, timeout=10,
            )
            return True
        except Exception:
            return False

    def proxy_events(self, agent_id: str) -> list[dict]:
        node = self.find_agent_node(agent_id)
        if not node or not node.url:
            return []
        try:
            headers = {}
            if node.secret:
                headers["X-Claw-Secret"] = node.secret
            resp = http_requests.get(
                f"{node.url}/api/agent/events",
                headers=headers, timeout=10,
            )
            resp.raise_for_status()
            return resp.json().get("events", [])
        except Exception:
            return []

    def proxy_approvals(self, agent_id: str) -> dict:
        """Get pending approvals from a remote agent."""
        node = self.find_agent_node(agent_id)
        if not node or not node.url:
            return {"pending": [], "history": []}
        try:
            headers = {}
            if node.secret:
                headers["X-Claw-Secret"] = node.secret
            resp = http_requests.get(
                f"{node.url}/api/agent/approvals",
                headers=headers, timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return {"pending": [], "history": []}

    def proxy_approve(self, agent_id: str, approval_id: str,
                      action: str = "approve") -> bool:
        """Approve/deny a tool execution on a remote agent."""
        node = self.find_agent_node(agent_id)
        if not node or not node.url:
            return False
        try:
            headers = {"Content-Type": "application/json"}
            if node.secret:
                headers["X-Claw-Secret"] = node.secret
            resp = http_requests.post(
                f"{node.url}/api/agent/approve",
                headers=headers,
                json={"approval_id": approval_id, "action": action},
                timeout=10,
            )
            return resp.json().get("ok", False)
        except Exception:
            return False

    def proxy_update_model(self, agent_id: str, node: RemoteNode,
                           provider: str = "", model: str = "") -> bool:
        """Update provider/model on a remote agent."""
        if not node or not node.url:
            return False
        try:
            headers = {"Content-Type": "application/json"}
            if node.secret:
                headers["X-Claw-Secret"] = node.secret
            resp = http_requests.post(
                f"{node.url}/api/agent/model",
                headers=headers,
                json={"provider": provider, "model": model},
                timeout=10,
            )
            return resp.json().get("ok", False)
        except Exception:
            return False
