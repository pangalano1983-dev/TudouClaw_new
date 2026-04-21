# Shared rules — the behavioral floor every skill must respect

Single source of truth for rules that apply to ALL skills, regardless
of runtime. Individual SKILL.md files may ADD rules but cannot override
or soften these.

## Rule 0 — rules are the floor, not the ceiling

These rules mark the BOUNDARY. Inside the boundary, exercise judgment:
run the minimum necessary steps, ask when uncertain, surface tradeoffs.
Do not robot through a checklist.

## Rule 1 — sandbox is absolute

Every file path passed to a tool is validated against the agent's
sandbox policy (`app.sandbox.get_current_policy().safe_path`). Consequences:

- Deliverables MUST live under `${AGENT_WORKSPACE}` (typically
  `~/.tudou_claw/workspaces/<agent_id>/` or a project's shared dir).
  Paths outside — `~/.agent-browser/tmp/`, `/tmp/`, `~/Downloads/` — are
  rejected by the deliverable registration endpoint.
- If an external tool (CLI, Playwright, `screencapture`) writes to a
  fixed path outside the workspace, IMMEDIATELY copy it into the
  workspace before reporting the path to the user. Never symlink.
- Do not try to circumvent the sandbox with `..` segments or absolute
  paths to system directories — `safe_path` blocks them.

## Rule 2 — log, don't print (runtime)

In runtime code paths (tool handlers, hooks, background workers), use
the module `logger` not `print()`. Exceptions: CLI entry points
(`__main__.py`, REPL), first-launch credential reveal, user-facing
startup banners — those keep `print` for visibility.

Rule of thumb: "will this show up in a production log aggregator?"
If yes, `logger`.

## Rule 3 — no silent exception swallowing

`except Exception: pass` is banned everywhere. Prefer:
- `except Exception as e: logger.warning("X failed: %s", e)` when the
  failure is non-fatal
- Narrow the `except` clause to the specific exception type you expect

A test-only shortcut (`except Exception: pass` in conftest fixtures)
is acceptable only with an inline comment explaining why.

## Rule 4 — no magic values in new code

Named constants at module level. `timeout = 30` inline is fine for
one-off scripts, but inside a handler that ships with the codebase,
`_HANDLER_TIMEOUT_S = 30` is what you want. Rule of thumb: if you would
grep for the literal later, promote it.

## Rule 5 — defensive programming at trust boundaries

User-supplied or LLM-generated inputs (tool call arguments, chat
content, file paths) must be validated before use:
- Cast numbers: `int(x)`, `float(x)` inside `try/except`
- Clamp ranges: `max(MIN, min(int(x), MAX))`
- Check membership: `if action not in {...}: return error`

Never trust `kwargs.get("field", default)` to have the type you want.

## Rule 6 — tests as the acceptance criterion

Every new handler / tool / skill gets a regression test. "It ran once
on my machine" is not evidence. The pytest suite is the contract between
past-you and future-you.

Rule of thumb: if you change a handler body, a test should fail first
(or you are missing a test).

## Rule 7 — surface, don't hide

If a tool call fails, return the error to the LLM rather than swallowing
and returning success. The LLM can recover from "FileNotFoundError: X";
it cannot recover from a successful-looking response with nothing in it.

Good error strings:
- `Error: File not found: <path>` — the LLM can correct path
- `Error: 'query' required for action=search` — the LLM can retry
- `Error: MCP 'slack' not bound. Available: ['email','github']`

Bad error strings:
- `Error: failed`
- `Error: see logs` (LLM cannot see logs)
