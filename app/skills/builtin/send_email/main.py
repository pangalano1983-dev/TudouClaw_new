"""
send_email skill — 通过 MCP 发送邮件。

支持两种后端（按优先级自动选择）:
  1. agentmail  — AgentMail API（推荐，支持附件/HTML/CC/BCC）
  2. smtp-server — 传统 SMTP (mcp-email-server)

附件路径会自动解析到 agent sandbox 下的绝对路径。
"""

import os


def _resolve_attachment_paths(paths, agent_id):
    """将相对路径解析为 sandbox 下的绝对路径。"""
    if not paths:
        return []
    data_dir = os.environ.get("TUDOU_CLAW_DATA_DIR") or os.path.join(
        os.path.expanduser("~"), ".tudou_claw"
    )
    sandbox_root = os.path.join(data_dir, "workspaces", agent_id, "sandbox")
    resolved = []
    for p in paths:
        if not p:
            continue
        p = str(p)
        if os.path.isabs(p):
            resolved.append(p)
        else:
            # 在 sandbox root 和 sandbox/workspace 下搜索
            for base in (sandbox_root, os.path.join(sandbox_root, "workspace")):
                candidate = os.path.normpath(os.path.join(base, p))
                if os.path.isfile(candidate):
                    resolved.append(candidate)
                    break
            else:
                # 找不到就用 sandbox_root 拼接，让 MCP 报错
                resolved.append(os.path.normpath(os.path.join(sandbox_root, p)))
    return resolved


def _get_mcp(ctx):
    """按优先级选择可用的邮件 MCP: agentmail > smtp-server。"""
    for mcp_id in ("agentmail", "smtp-server"):
        try:
            proxy = ctx.mcp(mcp_id)
            return mcp_id, proxy
        except (PermissionError, KeyError):
            continue
    raise RuntimeError("No email MCP available. Please bind 'agentmail' or 'smtp-server' MCP to this agent.")


def run(ctx, to, subject, body, cc=None, bcc=None, attachments=None):
    if isinstance(to, str):
        to = [to]

    mcp_id, mcp = _get_mcp(ctx)
    ctx.log(f"Using email MCP: {mcp_id}")

    # 构建 MCP 调用参数
    kwargs = dict(to=to, subject=subject, body=body)

    if cc:
        if isinstance(cc, str):
            cc = [cc]
        kwargs["cc"] = cc

    if bcc:
        if isinstance(bcc, str):
            bcc = [bcc]
        kwargs["bcc"] = bcc

    if attachments:
        if isinstance(attachments, str):
            attachments = [attachments]
        resolved = _resolve_attachment_paths(attachments, ctx.agent_id)
        if resolved:
            if mcp_id == "agentmail":
                # AgentMail: attachments = [{path: "..."}, ...]
                kwargs["attachments"] = [{"path": p} for p in resolved]
            else:
                # smtp-server: attachments = ["path1", "path2", ...]
                kwargs["attachments"] = resolved
            ctx.log(f"attachments resolved: {resolved}")

    ctx.log(f"sending email to {len(to)} recipients: subject={subject!r}"
            + (f", {len(resolved)} attachments" if attachments and resolved else ""))

    result = mcp.send_email(**kwargs)
    return {
        "message_id": result.get("message_id", "") if isinstance(result, dict) else "",
        "sent_count": len(to),
    }
