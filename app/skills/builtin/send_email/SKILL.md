# send_email

Send an email through a bound email MCP (`agentmail` preferred, falls back to `smtp-server`). The skill wraps the MCP call so you don't juggle `mcp_call` parameters yourself.

## Prerequisites

The agent must have at least one of these MCPs bound:
- `agentmail` (recommended — supports HTML, CC/BCC, attachments)
- `smtp-server` (fallback — plain SMTP)

If neither is bound, the skill errors with `No email MCP available`.

## Canonical call

```python
skill(send_email, {
    "to":      ["alice@example.com"],
    "subject": "Project update — Q2",
    "body":    "Hi Alice,\n\nHere is the latest status...\n\n— Bot"
})
```

That's the minimum. `to` / `subject` / `body` are the only required fields.

## Full shape

```python
skill(send_email, {
    "to":          ["a@example.com", "b@example.com"],   # string OR array
    "subject":     "…",
    "body":        "…",                                   # plain text
    "cc":          ["c@example.com"],                     # optional, same shape as `to`
    "bcc":         ["d@example.com"],                     # optional
    "attachments": ["report.pdf", "/abs/path/chart.png"]  # optional, see below
})
```

## Field notes

- **to / cc / bcc**: a single string is accepted and auto-wrapped into a list. Prefer passing arrays.
- **body**: plain text. HTML is NOT supported by this skill yet — if you need HTML, call the `agentmail` MCP directly via `mcp_call`.
- **from**: do NOT pass. The MCP uses the sender address from its own configuration. Passing `from` here does nothing.
- **attachments**:
  - Relative paths resolve against the agent's sandbox (`workspace/` searched first, then sandbox root).
  - Absolute paths pass through unchanged.
  - Missing files are sent as-is to the MCP, which will return a clear error.

## Returns

```python
{
    "message_id": "abc-123-…",   # set when the MCP returns one
    "sent_count": 2               # len(to)
}
```

## Failure modes

| Symptom | Meaning | Fix |
|---|---|---|
| `No email MCP available` | No `agentmail` or `smtp-server` bound to this agent | Bind one in the admin UI, or ask the user to bind it |
| `Invalid recipient` / `550 …` | MCP rejected an address | Check the `to` list; no typos; no trailing spaces |
| Attachment-related error from MCP | Resolved path didn't exist on disk | Either pass an absolute path, or put the file in `workspace/` first |

## Related paths

- Raw MCP call when you need HTML / per-message sender override:
  ```python
  mcp_call(mcp_id="agentmail", tool="send_email", arguments={...})
  ```
- Skill source: `app/skills/builtin/send_email/main.py`
