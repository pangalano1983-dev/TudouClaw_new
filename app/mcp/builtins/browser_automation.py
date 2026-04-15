"""
TudouClaw Browser Automation MCP Server — Web page automation via Playwright.

Runs as a stdio-based MCP server (JSON-RPC 2.0 over stdin/stdout).
Provides browser_navigate, browser_screenshot, browser_get_text,
browser_fill, browser_click, browser_evaluate, browser_close tools.

Usage:
    python -m app.mcp.builtins.browser_automation

Environment variables:
    BROWSER_HEADLESS  — "true" (default) or "false" for visible browser
"""
from __future__ import annotations

import base64
import json
import logging
import os
import sys
from typing import Any

logger = logging.getLogger("tudou.browser_automation_mcp")

# ---------------------------------------------------------------------------
# Playwright lazy initialization — browser persists across tool calls
# ---------------------------------------------------------------------------

_playwright = None
_browser = None
_page = None


def _ensure_browser():
    """Lazily launch Playwright Chromium. Reuse across calls."""
    global _playwright, _browser, _page
    if _page is not None and not _page.is_closed():
        return _page

    from playwright.sync_api import sync_playwright

    if _playwright is None:
        _playwright = sync_playwright().start()

    headless = os.environ.get("BROWSER_HEADLESS", "true").lower() == "true"
    _browser = _playwright.chromium.launch(headless=headless)
    _page = _browser.new_page()
    _page.set_default_timeout(30_000)  # 30s default timeout
    logger.info("Playwright Chromium launched (headless=%s)", headless)
    return _page


def _cleanup():
    """Close browser and stop Playwright."""
    global _playwright, _browser, _page
    try:
        if _page and not _page.is_closed():
            _page.close()
    except Exception:
        pass
    try:
        if _browser:
            _browser.close()
    except Exception:
        pass
    try:
        if _playwright:
            _playwright.stop()
    except Exception:
        pass
    _page = _browser = _playwright = None


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def tool_navigate(url: str, wait_until: str = "domcontentloaded") -> dict:
    """Navigate to a URL.

    Args:
        url: Target URL (must include protocol, e.g. https://)
        wait_until: Wait strategy — "domcontentloaded", "load", "networkidle"
    Returns:
        {url, title, status}
    """
    page = _ensure_browser()
    resp = page.goto(url, wait_until=wait_until)
    status = resp.status if resp else 0
    return {"url": page.url, "title": page.title(), "status": status}


def tool_screenshot(full_page: bool = True, selector: str = "") -> dict:
    """Capture screenshot of current page.

    Args:
        full_page: Capture full scrollable page (default True)
        selector: If provided, screenshot only this element
    Returns:
        {image_base64, width, height, url}
    """
    page = _ensure_browser()
    if selector:
        el = page.query_selector(selector)
        if not el:
            return {"error": f"Element not found: {selector}"}
        img_bytes = el.screenshot()
    else:
        img_bytes = page.screenshot(full_page=full_page)

    viewport = page.viewport_size or {}
    return {
        "image_base64": base64.b64encode(img_bytes).decode("ascii"),
        "width": viewport.get("width", 0),
        "height": viewport.get("height", 0),
        "url": page.url,
    }


def tool_get_text(selector: str = "body") -> dict:
    """Extract visible text from page or element.

    Args:
        selector: CSS selector (default "body" for full page text)
    Returns:
        {text, url, selector}
    """
    page = _ensure_browser()
    el = page.query_selector(selector)
    if not el:
        return {"error": f"Element not found: {selector}", "url": page.url}
    text = el.inner_text()
    # Truncate very long text to avoid overwhelming LLM context
    if len(text) > 10000:
        text = text[:10000] + "\n... (truncated, total " + str(len(text)) + " chars)"
    return {"text": text, "url": page.url, "selector": selector}


def tool_fill(selector: str, value: str) -> dict:
    """Fill an input field.

    Args:
        selector: CSS selector for the input element (e.g. "#email", "input[name=password]")
        value: Value to fill
    Returns:
        {ok, selector}
    """
    page = _ensure_browser()
    page.fill(selector, value)
    return {"ok": True, "selector": selector}


def tool_click(selector: str = "", text: str = "") -> dict:
    """Click an element by CSS selector or visible text.

    Args:
        selector: CSS selector (e.g. "button[type=submit]", "#login-btn")
        text: Visible text to match (e.g. "Log In", "提交"). Used if selector is empty.
    Returns:
        {ok, method, target}
    """
    page = _ensure_browser()
    if selector:
        page.click(selector)
        return {"ok": True, "method": "selector", "target": selector}
    elif text:
        page.get_by_text(text, exact=False).first.click()
        return {"ok": True, "method": "text", "target": text}
    else:
        return {"error": "Either 'selector' or 'text' must be provided"}


def tool_download(selector: str = "", text: str = "", url: str = "",
                  save_dir: str = "") -> dict:
    """Download a file by clicking a link/button or navigating to a URL.

    Args:
        selector: CSS selector of the download link/button
        text: Visible text of the download link (used if selector is empty)
        url: Direct download URL (used if both selector and text are empty)
        save_dir: Directory to save the file (default: /tmp/tudou_downloads)
    Returns:
        {ok, path, filename, size}
    """
    import shutil

    page = _ensure_browser()
    download_dir = save_dir or os.path.join("/tmp", "tudou_downloads")
    os.makedirs(download_dir, exist_ok=True)

    if url:
        # Direct download via new page navigation
        with page.expect_download(timeout=60_000) as dl_info:
            page.evaluate(f"() => {{ const a = document.createElement('a'); a.href = '{url}'; a.download = ''; document.body.appendChild(a); a.click(); }}")
        download = dl_info.value
    elif selector or text:
        # Click to trigger download
        with page.expect_download(timeout=60_000) as dl_info:
            if selector:
                page.click(selector)
            else:
                page.get_by_text(text, exact=False).first.click()
        download = dl_info.value
    else:
        return {"error": "Provide 'selector', 'text', or 'url' to trigger download"}

    # Save downloaded file
    filename = download.suggested_filename
    save_path = os.path.join(download_dir, filename)
    download.save_as(save_path)
    file_size = os.path.getsize(save_path)

    return {
        "ok": True,
        "path": save_path,
        "filename": filename,
        "size": file_size,
        "size_human": f"{file_size / 1024:.1f} KB" if file_size < 1048576 else f"{file_size / 1048576:.1f} MB",
    }


def tool_evaluate(expression: str) -> dict:
    """Execute JavaScript expression in the page context.

    Args:
        expression: JS expression to evaluate (e.g. "document.title", "location.href")
    Returns:
        {result, type}
    """
    page = _ensure_browser()
    result = page.evaluate(expression)
    return {"result": result, "type": type(result).__name__}


def tool_close() -> dict:
    """Close browser session and release resources."""
    _cleanup()
    return {"ok": True, "message": "Browser closed"}


# ---------------------------------------------------------------------------
# MCP protocol — tool schemas
# ---------------------------------------------------------------------------

TOOLS_SCHEMA = [
    {
        "name": "browser_navigate",
        "description": "打开指定 URL 页面。Navigate to a URL and wait for page load.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Target URL (e.g. https://example.com/login)",
                },
                "wait_until": {
                    "type": "string",
                    "description": "Wait strategy: domcontentloaded (default), load, networkidle",
                    "default": "domcontentloaded",
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "browser_screenshot",
        "description": "截取当前页面截图，返回 base64 PNG。用于观察页面状态。"
                       "Capture screenshot of current page as base64 PNG.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "full_page": {
                    "type": "boolean",
                    "description": "Capture full scrollable page (default true)",
                    "default": True,
                },
                "selector": {
                    "type": "string",
                    "description": "CSS selector to screenshot specific element (optional)",
                },
            },
        },
    },
    {
        "name": "browser_get_text",
        "description": "提取页面可见文本，用于分析页面内容和查找元素。"
                       "Extract visible text from page or specific element.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector (default 'body' for full page)",
                    "default": "body",
                },
            },
        },
    },
    {
        "name": "browser_fill",
        "description": "填写输入框。适用于用户名、密码、搜索框等。"
                       "Fill an input field with a value.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector for the input (e.g. '#email', 'input[name=password]')",
                },
                "value": {
                    "type": "string",
                    "description": "Value to fill in the input field",
                },
            },
            "required": ["selector", "value"],
        },
    },
    {
        "name": "browser_click",
        "description": "点击页面元素，支持 CSS 选择器或可见文本匹配。"
                       "Click an element by CSS selector or visible text.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector (e.g. 'button[type=submit]', '#login-btn')",
                },
                "text": {
                    "type": "string",
                    "description": "Visible text to click (e.g. 'Log In', '提交'). Used if selector is empty.",
                },
            },
        },
    },
    {
        "name": "browser_download",
        "description": "下载文件。点击下载链接或直接通过 URL 下载，保存到本地。"
                       "Download a file by clicking a link/button or via direct URL.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector of the download link/button",
                },
                "text": {
                    "type": "string",
                    "description": "Visible text of the download link (e.g. 'Download Report')",
                },
                "url": {
                    "type": "string",
                    "description": "Direct download URL (if no link to click)",
                },
                "save_dir": {
                    "type": "string",
                    "description": "Save directory (default /tmp/tudou_downloads)",
                },
            },
        },
    },
    {
        "name": "browser_evaluate",
        "description": "在页面中执行 JavaScript 表达式。"
                       "Execute a JavaScript expression in the page context.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "JS expression (e.g. 'document.title', 'location.href')",
                },
            },
            "required": ["expression"],
        },
    },
    {
        "name": "browser_close",
        "description": "关闭浏览器会话，释放资源。Close browser session.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]

SERVER_INFO = {
    "name": "tudou-browser-automation",
    "version": "1.0.0",
    "description": "TudouClaw Browser Automation MCP Server (Playwright)",
}


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 request handler
# ---------------------------------------------------------------------------

def _handle_request(req: dict) -> dict | None:
    """Handle a single JSON-RPC 2.0 request."""
    method = req.get("method", "")
    params = req.get("params", {})
    req_id = req.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            },
        }

    elif method == "notifications/initialized":
        return None

    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": TOOLS_SCHEMA},
        }

    elif method == "tools/call":
        tool_name = params.get("name", "")
        args = params.get("arguments", {})
        try:
            if tool_name == "browser_navigate":
                result = tool_navigate(
                    url=args["url"],
                    wait_until=args.get("wait_until", "domcontentloaded"),
                )
            elif tool_name == "browser_screenshot":
                result = tool_screenshot(
                    full_page=args.get("full_page", True),
                    selector=args.get("selector", ""),
                )
            elif tool_name == "browser_get_text":
                result = tool_get_text(
                    selector=args.get("selector", "body"),
                )
            elif tool_name == "browser_fill":
                result = tool_fill(
                    selector=args["selector"],
                    value=args["value"],
                )
            elif tool_name == "browser_click":
                result = tool_click(
                    selector=args.get("selector", ""),
                    text=args.get("text", ""),
                )
            elif tool_name == "browser_download":
                result = tool_download(
                    selector=args.get("selector", ""),
                    text=args.get("text", ""),
                    url=args.get("url", ""),
                    save_dir=args.get("save_dir", ""),
                )
            elif tool_name == "browser_evaluate":
                result = tool_evaluate(
                    expression=args["expression"],
                )
            elif tool_name == "browser_close":
                result = tool_close()
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
                }

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, default=str)}],
                },
            }
        except Exception as e:
            logger.exception("Tool %s failed", tool_name)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps({"error": str(e)})}],
                    "isError": True,
                },
            }

    elif method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    else:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Unknown method: {method}"},
        }


# ---------------------------------------------------------------------------
# Main — stdio JSON-RPC server
# ---------------------------------------------------------------------------

def main():
    """Run MCP server on stdin/stdout."""
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)-5s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )
    logger.info("TudouClaw Browser Automation MCP Server starting...")

    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError:
                resp = {"jsonrpc": "2.0", "id": None,
                        "error": {"code": -32700, "message": "Parse error"}}
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
                continue

            resp = _handle_request(req)
            if resp is not None:
                sys.stdout.write(json.dumps(resp, ensure_ascii=False, default=str) + "\n")
                sys.stdout.flush()
    finally:
        _cleanup()


if __name__ == "__main__":
    main()
