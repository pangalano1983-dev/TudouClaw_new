"""
Web chat interface — pure stdlib http.server with SSE streaming.
"""
import html
import json
import os
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import llm, tools

# ---------------------------------------------------------------------------
# In-memory conversation store (per-session, single-user)
# ---------------------------------------------------------------------------

_conversations: dict[str, list[dict]] = {}
_lock = threading.Lock()


def _get_system_prompt() -> str:
    parts = [
        "You are Claw, an AI programming assistant.",
        "You have access to tools for reading/writing files, running shell commands, and searching code.",
        "Always use tools when the user asks you to interact with files or run commands.",
        "Be concise and helpful. Use markdown formatting for code.",
    ]
    cwd = Path.cwd()
    for name in ("TUDOU_CLAW.md", "CLAW.md", "README.md"):
        ctx_file = cwd / name
        if ctx_file.exists():
            try:
                content = ctx_file.read_text(encoding="utf-8", errors="replace")[:4000]
                parts.append(f"<project_context file=\"{name}\">\n{content}\n</project_context>")
            except OSError:
                pass
    parts.append(f"Current working directory: {cwd}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Inline HTML page
# ---------------------------------------------------------------------------

_HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Tudou Claws — AI Assistant</title>
<style>
  :root {
    --bg: #1a1b26; --surface: #24283b; --border: #414868;
    --text: #c0caf5; --text-dim: #565f89; --accent: #7aa2f7;
    --green: #9ece6a; --yellow: #e0af68; --red: #f7768e;
    --magenta: #bb9af7; --cyan: #7dcfff;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: 'SF Mono', 'Cascadia Code', 'Fira Code', monospace;
    background: var(--bg); color: var(--text); height: 100vh;
    display: flex; flex-direction: column;
  }
  header {
    padding: 12px 20px; background: var(--surface);
    border-bottom: 1px solid var(--border);
    display: flex; align-items: center; gap: 12px;
  }
  header h1 { font-size: 16px; color: var(--accent); }
  header span { font-size: 12px; color: var(--text-dim); }
  #chat {
    flex: 1; overflow-y: auto; padding: 16px 20px;
    display: flex; flex-direction: column; gap: 12px;
  }
  .msg {
    max-width: 85%; padding: 10px 14px; border-radius: 10px;
    font-size: 14px; line-height: 1.6; white-space: pre-wrap;
    word-wrap: break-word;
  }
  .msg.user {
    align-self: flex-end; background: var(--accent); color: #1a1b26;
    border-bottom-right-radius: 2px;
  }
  .msg.assistant {
    align-self: flex-start; background: var(--surface);
    border: 1px solid var(--border); border-bottom-left-radius: 2px;
  }
  .msg.tool {
    align-self: flex-start; background: #1e2030;
    border: 1px solid var(--yellow); border-radius: 6px;
    font-size: 12px; color: var(--yellow); opacity: 0.85;
  }
  .msg code, .msg pre {
    background: rgba(0,0,0,0.3); padding: 2px 5px; border-radius: 3px;
    font-size: 13px;
  }
  .msg pre { padding: 8px 10px; overflow-x: auto; display: block; margin: 6px 0; }
  #input-area {
    padding: 12px 20px; background: var(--surface);
    border-top: 1px solid var(--border);
    display: flex; gap: 10px;
  }
  #input-area textarea {
    flex: 1; background: var(--bg); color: var(--text);
    border: 1px solid var(--border); border-radius: 8px;
    padding: 10px 14px; font-family: inherit; font-size: 14px;
    resize: none; outline: none; min-height: 44px; max-height: 120px;
  }
  #input-area textarea:focus { border-color: var(--accent); }
  #input-area button {
    background: var(--accent); color: #1a1b26; border: none;
    border-radius: 8px; padding: 10px 20px; font-weight: bold;
    cursor: pointer; font-family: inherit; font-size: 14px;
  }
  #input-area button:hover { opacity: 0.9; }
  #input-area button:disabled { opacity: 0.4; cursor: not-allowed; }
  .spinner { display: inline-block; animation: spin 1s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>
<header>
  <h1>🥔 Tudou Claws</h1>
  <span id="status">Ready</span>
</header>
<div id="chat"></div>
<div id="input-area">
  <textarea id="input" rows="1" placeholder="Ask anything... (Enter to send, Shift+Enter for newline)" autofocus></textarea>
  <button id="send" onclick="sendMessage()">Send</button>
</div>
<script>
const chatEl = document.getElementById('chat');
const inputEl = document.getElementById('input');
const sendBtn = document.getElementById('send');
const statusEl = document.getElementById('status');
let sessionId = 'default';

function addMsg(role, text) {
  const div = document.createElement('div');
  div.className = 'msg ' + role;
  div.textContent = text;
  chatEl.appendChild(div);
  chatEl.scrollTop = chatEl.scrollHeight;
  return div;
}

function setStatus(s) { statusEl.textContent = s; }

async function sendMessage() {
  const text = inputEl.value.trim();
  if (!text) return;
  inputEl.value = '';
  sendBtn.disabled = true;
  addMsg('user', text);
  setStatus('Thinking...');

  const msgDiv = addMsg('assistant', '');
  let fullText = '';

  try {
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({session: sessionId, message: text})
    });

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, {stream: true});
      const lines = buffer.split('\n');
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const data = line.slice(6);
        if (data === '[DONE]') continue;
        try {
          const evt = JSON.parse(data);
          if (evt.type === 'text') {
            fullText += evt.content;
            msgDiv.textContent = fullText;
            chatEl.scrollTop = chatEl.scrollHeight;
          } else if (evt.type === 'tool_call') {
            addMsg('tool', '⚡ ' + evt.name + ': ' + evt.args);
          } else if (evt.type === 'tool_result') {
            const preview = evt.content.length > 200
              ? evt.content.slice(0, 200) + '...' : evt.content;
            addMsg('tool', '→ ' + preview);
          } else if (evt.type === 'error') {
            msgDiv.textContent = '✗ Error: ' + evt.content;
            msgDiv.style.color = '#f7768e';
          }
        } catch(e) {}
      }
    }
  } catch(e) {
    msgDiv.textContent = '✗ Connection error: ' + e.message;
    msgDiv.style.color = '#f7768e';
  }

  setStatus('Ready');
  sendBtn.disabled = false;
  inputEl.focus();
}

inputEl.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});
// Auto-resize textarea
inputEl.addEventListener('input', () => {
  inputEl.style.height = 'auto';
  inputEl.style.height = Math.min(inputEl.scrollHeight, 120) + 'px';
});
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# HTTP Handler
# ---------------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Quieter logging
        sys.stderr.write(f"[web] {fmt % args}\n")

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html_content: str):
        body = html_content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            self._send_html(_HTML_PAGE)
        elif parsed.path == "/api/health":
            self._send_json({"status": "ok", "config": llm.get_config()})
        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/chat":
            self._handle_chat()
        else:
            self.send_error(404)

    def _handle_chat(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._send_json({"error": "Invalid JSON"}, 400)
            return

        session_id = data.get("session", "default")
        user_message = data.get("message", "").strip()
        if not user_message:
            self._send_json({"error": "Empty message"}, 400)
            return

        # Set up SSE response
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        def send_sse(event_data: dict):
            line = f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"
            try:
                self.wfile.write(line.encode("utf-8"))
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

        # Get or create conversation
        with _lock:
            if session_id not in _conversations:
                _conversations[session_id] = [
                    {"role": "system", "content": _get_system_prompt()}
                ]
            messages = _conversations[session_id]

        messages.append({"role": "user", "content": user_message})

        tool_defs = tools.get_tool_definitions()

        try:
            max_iterations = 15
            iteration = 0
            while iteration < max_iterations:
                iteration += 1
                response = llm.chat_no_stream(messages, tools=tool_defs)
                msg = response.get("message", {})
                content = msg.get("content", "")
                tool_calls = msg.get("tool_calls", [])

                if content:
                    send_sse({"type": "text", "content": content})

                if not tool_calls:
                    messages.append({"role": "assistant", "content": content})
                    break

                # Process tool calls
                assistant_msg: dict = {"role": "assistant", "content": content}
                assistant_msg["tool_calls"] = tool_calls
                messages.append(assistant_msg)

                for tc in tool_calls:
                    func_info = tc.get("function", {})
                    name = func_info.get("name", "unknown")
                    arguments = func_info.get("arguments", {})
                    if isinstance(arguments, str):
                        try:
                            arguments = json.loads(arguments)
                        except json.JSONDecodeError:
                            arguments = {}

                    send_sse({
                        "type": "tool_call",
                        "name": name,
                        "args": json.dumps(arguments, ensure_ascii=False)[:200],
                    })

                    result = tools.execute_tool(name, arguments)
                    send_sse({"type": "tool_result", "content": result[:500]})
                    messages.append({"role": "tool", "content": result})

        except Exception as e:
            send_sse({"type": "error", "content": str(e)})

        send_sse({"type": "done"})
        try:
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass


# ---------------------------------------------------------------------------
# Server launcher
# ---------------------------------------------------------------------------

def run_web(port: int = 8080):
    """Start the web server."""
    server = HTTPServer(("0.0.0.0", port), _Handler)
    cfg = llm.get_config()
    print(f"\n🥔 Tudou Claws Web — http://localhost:{port}")
    print(f"   Provider: {cfg['provider']}  Model: {cfg['model']}")
    print(f"   Press Ctrl+C to stop\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()
