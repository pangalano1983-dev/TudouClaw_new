#!/usr/bin/env bash
# ============================================================
# Tudou Claw — 局域网快速部署脚本
#
# 本脚本帮助你在局域网内快速搭建 Portal 主控 + Agent 工作节点
#
# 用法:
#   主控机:  bash deploy.sh portal
#   工作机:  bash deploy.sh agent <portal-ip>
# ============================================================

set -e

# ---------- 配色 ----------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[1;34m'; CYAN='\033[0;36m'; NC='\033[0m'

# ---------- 自动获取本机局域网 IP ----------
get_lan_ip() {
    python3 -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    s.connect(('8.8.8.8', 80))
    print(s.getsockname()[0])
finally:
    s.close()
" 2>/dev/null || echo "127.0.0.1"
}

# ---------- 检查依赖 ----------
check_deps() {
    echo -e "${CYAN}检查依赖...${NC}"
    python3 --version >/dev/null 2>&1 || { echo -e "${RED}需要 Python 3.10+${NC}"; exit 1; }

    python3 -c "import requests" 2>/dev/null || {
        echo -e "${YELLOW}安装 requests...${NC}"
        pip3 install requests --break-system-packages 2>/dev/null || pip3 install requests
    }
    python3 -c "import yaml" 2>/dev/null || {
        echo -e "${YELLOW}安装 pyyaml...${NC}"
        pip3 install pyyaml --break-system-packages 2>/dev/null || pip3 install pyyaml
    }
    echo -e "${GREEN}依赖就绪${NC}"
}

# ---------- 生成随机 secret ----------
gen_secret() {
    python3 -c "import secrets; print(secrets.token_hex(16))"
}

# ============================================================
# Portal 模式 (主控机)
# ============================================================
start_portal() {
    local PORT=${1:-9090}
    local SECRET=${2:-$(gen_secret)}
    local LAN_IP=$(get_lan_ip)

    check_deps

    echo ""
    echo -e "${BLUE}╔══════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║     🐾 Tudou Claw Portal — 局域网主控        ║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  本机 IP:    ${GREEN}${LAN_IP}${NC}"
    echo -e "  端口:       ${GREEN}${PORT}${NC}"
    echo -e "  Secret:     ${YELLOW}${SECRET}${NC}"
    echo ""
    echo -e "  ${CYAN}其他机器启动 Agent 的命令:${NC}"
    echo ""
    echo -e "  ${GREEN}# 1. 先把项目复制到目标机器, 然后运行:${NC}"
    echo -e "  ${GREEN}bash deploy.sh agent ${LAN_IP}${NC}"
    echo ""
    echo -e "  ${GREEN}# 或者手动指定参数:${NC}"
    echo -e "  ${GREEN}python -m app agent \\${NC}"
    echo -e "  ${GREEN}    --name MyCoder --role coder \\${NC}"
    echo -e "  ${GREEN}    --hub http://${LAN_IP}:${PORT} \\${NC}"
    echo -e "  ${GREEN}    --secret ${SECRET}${NC}"
    echo ""
    echo -e "  ${CYAN}打开 Dashboard:${NC}  http://${LAN_IP}:${PORT}"
    echo ""

    # 保存 secret 到文件供 agent 使用
    echo "${SECRET}" > .tudou_secret
    echo "${LAN_IP}" > .tudou_portal_ip
    echo "${PORT}" > .tudou_portal_port

    python3 -m app portal \
        --port "${PORT}" \
        --secret "${SECRET}" \
        --node-name "$(hostname)"
}

# ============================================================
# Agent 模式 (工作机)
# ============================================================
start_agent() {
    local PORTAL_IP=${1:?"用法: bash deploy.sh agent <portal-ip> [portal-port] [agent-port] [role] [name]"}
    local PORTAL_PORT=${2:-9090}
    local AGENT_PORT=${3:-8081}
    local ROLE=${4:-general}
    local NAME=${5:-"Agent-$(hostname)"}

    check_deps

    # 尝试从同步的文件读 secret
    local SECRET=""
    if [ -f .tudou_secret ]; then
        SECRET=$(cat .tudou_secret)
    else
        echo -e "${YELLOW}未找到 .tudou_secret 文件${NC}"
        echo -n "请输入 Portal 的 Secret: "
        read -r SECRET
    fi

    local LAN_IP=$(get_lan_ip)

    echo ""
    echo -e "${BLUE}╔══════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║     🤖 Tudou Claw Agent — 工作节点            ║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  本机 IP:    ${GREEN}${LAN_IP}${NC}"
    echo -e "  Agent:      ${GREEN}${NAME}${NC} (${ROLE})"
    echo -e "  Agent 端口: ${GREEN}${AGENT_PORT}${NC}"
    echo -e "  Portal:     ${GREEN}http://${PORTAL_IP}:${PORTAL_PORT}${NC}"
    echo ""
    echo -e "  模型由 Portal 统一管理，在 Dashboard 中切换"
    echo ""

    python3 -m app agent \
        --name "${NAME}" \
        --role "${ROLE}" \
        --port "${AGENT_PORT}" \
        --hub "http://${PORTAL_IP}:${PORTAL_PORT}" \
        --secret "${SECRET}"
}

# ============================================================
# 入口
# ============================================================
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "${SCRIPT_DIR}"

case "${1:-help}" in
    portal)
        start_portal "${2}" "${3}"
        ;;
    agent)
        start_agent "${2}" "${3}" "${4}" "${5}" "${6}"
        ;;
    *)
        echo ""
        echo -e "${BLUE}Tudou Claw — 局域网多机部署${NC}"
        echo ""
        echo "用法:"
        echo "  bash deploy.sh portal [port] [secret]    # 启动主控 Portal"
        echo "  bash deploy.sh agent <portal-ip>         # 启动工作 Agent"
        echo ""
        echo "示例:"
        echo "  # 主控机 (例如 192.168.1.100)"
        echo "  bash deploy.sh portal 9090"
        echo ""
        echo "  # 工作机1 — 启动 coder agent"
        echo "  bash deploy.sh agent 192.168.1.100 9090 8081 coder MyCoder"
        echo ""
        echo "  # 工作机2 — 启动 reviewer agent"
        echo "  bash deploy.sh agent 192.168.1.100 9090 8081 reviewer MyReviewer"
        echo ""
        echo "参数说明:"
        echo "  portal [port] [secret]"
        echo "    port    — Portal 端口 (默认 9090)"
        echo "    secret  — 共享密钥 (默认自动生成)"
        echo ""
        echo "  agent <portal-ip> [portal-port] [agent-port] [role] [name]"
        echo "    portal-ip   — 主控机 IP (必填)"
        echo "    portal-port — 主控端口 (默认 9090)"
        echo "    agent-port  — 本机 agent 端口 (默认 8081)"
        echo "    role        — 角色: general/coder/reviewer/researcher/architect/devops"
        echo "    name        — Agent 名称 (默认 Agent-主机名)"
        echo ""
        ;;
esac
