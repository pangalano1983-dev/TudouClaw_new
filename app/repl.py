"""
Interactive REPL — colourful terminal chat with tool-calling loop.
"""
import json
import os
import sys
from pathlib import Path
from typing import Generator

from . import llm, tools

# ---------------------------------------------------------------------------
# ANSI helpers (no third-party deps)
# ---------------------------------------------------------------------------

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RED = "\033[31m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_BLUE = "\033[34m"
_MAGENTA = "\033[35m"
_CYAN = "\033[36m"
_WHITE = "\033[37m"
_BG_GRAY = "\033[48;5;236m"


def _c(text: str, *codes: str) -> str:
    return "".join(codes) + text + _RESET


# ---------------------------------------------------------------------------
# System prompt builder
# ---------------------------------------------------------------------------

def _build_system_prompt() -> str:
    parts = [
        "You are Claw, an AI programming assistant running in the terminal.",
        "You have access to tools for reading/writing files, running shell commands, and searching code.",
        "Always use tools when the user asks you to interact with files or run commands.",
        "Be concise and helpful. When showing code, use markdown code blocks.",
        "",
    ]

    # Auto-load project context files
    cwd = Path.cwd()
    for name in ("TUDOU_CLAW.md", "CLAW.md", "README.md"):
        ctx_file = cwd / name
        if ctx_file.exists():
            try:
                content = ctx_file.read_text(encoding="utf-8", errors="replace")[:4000]
                parts.append(f"<project_context file=\"{name}\">\n{content}\n</project_context>\n")
            except OSError:
                pass

    parts.append(f"Current working directory: {cwd}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Slash commands
# ---------------------------------------------------------------------------

def _handle_slash_command(cmd: str) -> bool | None:
    """Handle a slash command. Returns True to continue, None to quit, False if not a command."""
    parts = cmd.strip().split(maxsplit=1)
    command = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if command == "/help":
        print(_c("Available commands:", _BOLD, _CYAN))
        print(f"  {_c('/help', _GREEN)}       — Show this help")
        print(f"  {_c('/clear', _GREEN)}      — Clear conversation history")
        print(f"  {_c('/model <name>', _GREEN)} — Switch model (e.g. /model llama3:8b)")
        print(f"  {_c('/config', _GREEN)}     — Show current configuration")
        print(f"  {_c('/quit', _GREEN)}       — Exit")
        return True

    if command == "/clear":
        print(_c("Conversation cleared.", _YELLOW))
        return "clear"

    if command == "/model":
        if not arg:
            cfg = llm.get_config()
            print(_c(f"Current model: {cfg['model']}", _CYAN))
        else:
            llm.set_model(arg)
            print(_c(f"Model switched to: {arg}", _GREEN))
        return True

    if command == "/config":
        cfg = llm.get_config()
        print(_c("Current configuration:", _BOLD, _CYAN))
        for k, v in cfg.items():
            display_v = "***" if "key" in k and v else v
            print(f"  {_c(k, _GREEN)}: {display_v}")
        return True

    if command in ("/quit", "/exit", "/q"):
        return None

    return False


# ---------------------------------------------------------------------------
# Tool call processing
# ---------------------------------------------------------------------------

def _process_tool_calls(tool_calls: list[dict], messages: list[dict]) -> list[dict]:
    """Execute tool calls and append results to messages."""
    for tc in tool_calls:
        func_info = tc.get("function", {})
        name = func_info.get("name", "unknown")
        arguments = func_info.get("arguments", {})

        # arguments might be a JSON string
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}

        print(f"\n  {_c('⚡ Tool:', _BOLD, _YELLOW)} {_c(name, _CYAN)} ", end="")
        # Show brief args
        brief = json.dumps(arguments, ensure_ascii=False)
        if len(brief) > 120:
            brief = brief[:117] + "..."
        print(_c(brief, _DIM))

        result = tools.execute_tool(name, arguments)

        # Show truncated result
        preview = result[:300].replace("\n", "\\n")
        if len(result) > 300:
            preview += "..."
        print(f"  {_c('→ Result:', _GREEN)} {_c(preview, _DIM)}")

        messages.append({"role": "tool", "content": result})

    return messages


# ---------------------------------------------------------------------------
# Main REPL loop
# ---------------------------------------------------------------------------

def run_repl():
    """Start the interactive REPL."""
    cfg = llm.get_config()

    print()
    print(_c("╭─────────────────────────────────────╮", _BLUE))
    print(_c("│", _BLUE) + _c("  🥔 Tudou Claws — AI Assistant", _BOLD, _WHITE) + _c("│", _BLUE))
    print(_c("│", _BLUE) + _c(f"  Provider: {cfg['provider']:8s}  Model: {cfg['model'][:14]}", _DIM) + _c(" │", _BLUE))
    print(_c("╰─────────────────────────────────────╯", _BLUE))
    print(_c("  Type /help for commands, /quit to exit\n", _DIM))

    system_prompt = _build_system_prompt()
    messages: list[dict] = [{"role": "system", "content": system_prompt}]

    while True:
        try:
            user_input = input(_c("\n❯ ", _BOLD, _GREEN))
        except (EOFError, KeyboardInterrupt):
            print(_c("\nGoodbye! 👋", _YELLOW))
            break

        user_input = user_input.strip()
        if not user_input:
            continue

        # Slash commands
        if user_input.startswith("/"):
            result = _handle_slash_command(user_input)
            if result is None:
                print(_c("Goodbye! 👋", _YELLOW))
                break
            if result == "clear":
                messages = [{"role": "system", "content": system_prompt}]
                continue
            if result is True:
                continue
            # Not a recognized command, treat as normal input

        messages.append({"role": "user", "content": user_input})

        # First try streaming (if no tools needed, this is nice)
        # But we need to handle tool calls, so first do non-stream with tools
        tool_defs = tools.get_tool_definitions()

        print(f"\n{_c('Claw:', _BOLD, _MAGENTA)} ", end="", flush=True)

        try:
            # Non-streaming call with tool support
            response = llm.chat_no_stream(messages, tools=tool_defs)

            msg = response.get("message", {})
            content = msg.get("content", "")
            tool_calls = msg.get("tool_calls", [])

            if content:
                # Print content with streaming feel (character by character)
                for ch in content:
                    sys.stdout.write(ch)
                    sys.stdout.flush()
                print()

            # Tool call loop
            max_iterations = 15
            iteration = 0
            while tool_calls and iteration < max_iterations:
                iteration += 1
                # Add assistant message to history
                assistant_msg: dict = {"role": "assistant", "content": content}
                if tool_calls:
                    assistant_msg["tool_calls"] = tool_calls
                messages.append(assistant_msg)

                # Execute tools
                messages = _process_tool_calls(tool_calls, messages)

                # Call LLM again with tool results
                print(f"\n{_c('Claw:', _BOLD, _MAGENTA)} ", end="", flush=True)
                response = llm.chat_no_stream(messages, tools=tool_defs)
                msg = response.get("message", {})
                content = msg.get("content", "")
                tool_calls = msg.get("tool_calls", [])

                if content:
                    for ch in content:
                        sys.stdout.write(ch)
                        sys.stdout.flush()
                    print()

            if not tool_calls:
                # Final response, add to history
                messages.append({"role": "assistant", "content": content})

            if iteration >= max_iterations:
                print(_c("\n⚠ Tool call limit reached.", _YELLOW))

        except KeyboardInterrupt:
            print(_c("\n(interrupted)", _YELLOW))
            continue
        except Exception as e:
            print(_c(f"\n✗ Error: {e}", _RED))
            # Remove the user message on error so we don't corrupt history
            if messages and messages[-1]["role"] == "user":
                messages.pop()
