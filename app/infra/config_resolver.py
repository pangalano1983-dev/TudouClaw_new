"""
ConfigResolver — 统一配置优先级链。

优先级：Agent > Node > Global
用途：LLM provider/model、MCP 环境变量、工具策略、超时等配置项。

使用方式：
    resolver = ConfigResolver(global_cfg, node_configs, agent_configs)
    value = resolver.resolve("llm.provider", agent_id="xxx", node_id="yyy")
    # 先查 Agent 级 → 再查 Node 级 → 最后查 Global 级

设计原则：
    - 不可变查询：resolve() 不修改任何配置
    - 支持点分路径：如 "llm.provider", "mcp.env.API_KEY"
    - 支持默认值：未找到时返回 default
    - 线程安全
"""
from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger("tudou.config")


class ConfigResolver:
    """
    统一配置解析器。

    三层配置优先级：Agent > Node > Global。
    每层配置用 dict 存储，key 为点分路径（如 "llm.provider"）。
    """

    def __init__(self):
        self._global: dict[str, Any] = {}
        self._node: dict[str, dict[str, Any]] = {}   # node_id -> config dict
        self._agent: dict[str, dict[str, Any]] = {}   # agent_id -> config dict
        self._lock = threading.RLock()

    # ── 配置设置 ──

    def set_global(self, key: str, value: Any):
        """设置全局配置。"""
        with self._lock:
            self._global[key] = value

    def set_global_batch(self, config: dict[str, Any]):
        """批量设置全局配置。"""
        with self._lock:
            self._global.update(config)

    def set_node(self, node_id: str, key: str, value: Any):
        """设置 Node 级配置。"""
        with self._lock:
            if node_id not in self._node:
                self._node[node_id] = {}
            self._node[node_id][key] = value

    def set_node_batch(self, node_id: str, config: dict[str, Any]):
        """批量设置 Node 级配置。"""
        with self._lock:
            if node_id not in self._node:
                self._node[node_id] = {}
            self._node[node_id].update(config)

    def set_agent(self, agent_id: str, key: str, value: Any):
        """设置 Agent 级配置。"""
        with self._lock:
            if agent_id not in self._agent:
                self._agent[agent_id] = {}
            self._agent[agent_id][key] = value

    def set_agent_batch(self, agent_id: str, config: dict[str, Any]):
        """批量设置 Agent 级配置。"""
        with self._lock:
            if agent_id not in self._agent:
                self._agent[agent_id] = {}
            self._agent[agent_id].update(config)

    # ── 配置查询 ──

    def resolve(self, key: str, agent_id: str = "", node_id: str = "",
                default: Any = None) -> Any:
        """
        按 Agent > Node > Global 优先级解析配置值。

        Args:
            key:      配置键（如 "llm.provider", "tool.approval_timeout"）
            agent_id: Agent ID（可选）
            node_id:  Node ID（可选）
            default:  所有层都没找到时的默认值

        Returns:
            解析后的值，或 default。
        """
        with self._lock:
            # 1. Agent 级
            if agent_id and agent_id in self._agent:
                val = self._agent[agent_id].get(key)
                if val is not None:
                    return val

            # 2. Node 级
            if node_id and node_id in self._node:
                val = self._node[node_id].get(key)
                if val is not None:
                    return val

            # 3. Global 级
            val = self._global.get(key)
            if val is not None:
                return val

            return default

    def resolve_all(self, prefix: str, agent_id: str = "",
                    node_id: str = "") -> dict[str, Any]:
        """
        解析所有以 prefix 开头的配置，合并后返回。

        合并顺序：Global → Node → Agent（后面覆盖前面）。
        """
        result = {}
        with self._lock:
            # Global
            for k, v in self._global.items():
                if k.startswith(prefix):
                    result[k] = v

            # Node (覆盖 Global)
            if node_id and node_id in self._node:
                for k, v in self._node[node_id].items():
                    if k.startswith(prefix):
                        result[k] = v

            # Agent (覆盖 Node)
            if agent_id and agent_id in self._agent:
                for k, v in self._agent[agent_id].items():
                    if k.startswith(prefix):
                        result[k] = v

        return result

    def resolve_llm(self, agent_id: str = "", node_id: str = "") -> tuple[str, str]:
        """
        快捷方法：解析 LLM provider 和 model。

        Returns: (provider, model)
        """
        provider = self.resolve("llm.provider", agent_id, node_id, "")
        model = self.resolve("llm.model", agent_id, node_id, "")
        return provider, model

    def resolve_mcp_env(self, mcp_id: str, agent_id: str = "",
                         node_id: str = "") -> dict[str, str]:
        """
        快捷方法：解析 MCP 服务的环境变量。

        从三层配置中合并 mcp.{mcp_id}.env.* 的值。
        """
        prefix = f"mcp.{mcp_id}.env."
        all_cfg = self.resolve_all(prefix, agent_id, node_id)
        # 去掉 prefix，返回纯 env 键值对
        return {k[len(prefix):]: v for k, v in all_cfg.items()}

    # ── 配置导出 ──

    def get_effective_config(self, agent_id: str = "",
                              node_id: str = "") -> dict[str, Any]:
        """导出指定 Agent/Node 的完整有效配置（三层合并后）。"""
        result = {}
        with self._lock:
            result.update(self._global)
            if node_id and node_id in self._node:
                result.update(self._node[node_id])
            if agent_id and agent_id in self._agent:
                result.update(self._agent[agent_id])
        return result

    def get_agent_overrides(self, agent_id: str) -> dict[str, Any]:
        """获取 Agent 级的所有覆盖配置。"""
        with self._lock:
            return dict(self._agent.get(agent_id, {}))

    def get_node_overrides(self, node_id: str) -> dict[str, Any]:
        """获取 Node 级的所有覆盖配置。"""
        with self._lock:
            return dict(self._node.get(node_id, {}))

    def clear_agent(self, agent_id: str):
        """清除 Agent 级配置。"""
        with self._lock:
            self._agent.pop(agent_id, None)

    def clear_node(self, node_id: str):
        """清除 Node 级配置。"""
        with self._lock:
            self._node.pop(node_id, None)

    # ── 序列化 ──

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "global": dict(self._global),
                "node": {k: dict(v) for k, v in self._node.items()},
                "agent": {k: dict(v) for k, v in self._agent.items()},
            }

    @staticmethod
    def from_dict(d: dict) -> ConfigResolver:
        r = ConfigResolver()
        r._global = d.get("global", {})
        r._node = d.get("node", {})
        r._agent = d.get("agent", {})
        return r


# ─────────────────────────────────────────────────────────────
# 全局单例
# ─────────────────────────────────────────────────────────────

_resolver: ConfigResolver | None = None


def get_resolver() -> ConfigResolver:
    """获取全局 ConfigResolver 单例。"""
    global _resolver
    if _resolver is None:
        _resolver = ConfigResolver()
    return _resolver


def init_resolver(global_cfg: dict = None) -> ConfigResolver:
    """初始化全局 ConfigResolver，并加载全局配置。"""
    global _resolver
    _resolver = ConfigResolver()
    if global_cfg:
        _resolver.set_global_batch(global_cfg)
    return _resolver
