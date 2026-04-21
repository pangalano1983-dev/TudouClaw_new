# Tool description standard — the 5-element format

Applies to:
- Every entry in `app/tools.py` `TOOL_DEFINITIONS`
- Every MCP tool description authored in this codebase
- The `description:` field in a skill's `manifest.yaml` / SKILL.md frontmatter

## Why it matters

Description is a **routing signal**, not a summary. The LLM sees the
description when deciding "should I call this tool / load this skill?".
A weak description = skill/tool never gets triggered = the capability
might as well not exist.

## The format (non-negotiable)

```
{one-line capability}.
Use when: {trigger scenarios / user phrasings}.
Not for: {exclusions + distinction from similar tools}.
Output: {what the tool produces + side effects}.
GOTCHA: {common pitfalls / easy-to-confuse behaviors}.
```

## Why each element

| Element | Purpose | Failure mode if omitted |
|---|---|---|
| **Capability** | One sentence so the LLM knows what the tool does at a glance | Agent never picks the tool because it is unclear what it does |
| **Use when** | Concrete trigger phrases the user says / scenarios to match | Tool is semantically correct but never invoked for the right user intent |
| **Not for** | Negative space — what this tool is **not**, vs similar tools | Agent wrong-routes (calls web_fetch for JSON APIs, etc.) |
| **Output** | What the agent receives + what the user sees (side effects) | Agent doesn't know if the tool is "best-effort" or has a visible artifact |
| **GOTCHA** | The ONE thing that breaks agents most often with this tool | Agent repeats the same mistake across runs; debt compounds |

## Good vs bad examples

### Bad (routing-blind)

```
Fetch the text content of a web page URL. Returns plain text.
```

Problems: no distinction from `http_request`; no guidance on when to call vs `web_search`; no hint about the length cap (agents blow up context).

### Good

```
Fetch a specific URL and extract plain text (strips script/style,
decodes HTML entities).
Use when: reading a documentation page, article, or API reference
after finding it via web_search or when the user gives an explicit URL.
Not for: discovering new URLs (use web_search). Not for JSON API
calls (use http_request — it preserves status codes and headers).
Not for PDF/binary URLs.
Output: `[Content from URL]` header + extracted plain text,
truncated to max_length (default 5000 chars).
GOTCHA: default 5000-char cap is deliberate — research sessions
that ran 10000+ chars/fetch burned 25k+ tokens of context. Raise
max_length only when one URL genuinely needs full capture.
```

## Authoring checklist

Before committing a new tool / skill description, verify:

- [ ] One-line capability is actually ONE line (no "Useful for X, Y, Z..." filler)
- [ ] `Use when:` has at least 2 concrete phrasings, not abstract descriptions
- [ ] `Not for:` names at least 1 similar tool/skill and when to use it instead
- [ ] `Output:` names the return shape AND any side effects (files written, messages sent)
- [ ] `GOTCHA:` distills a real pitfall — not a generic warning. "Don't pass invalid input" is NOT a gotcha; "timeout is clamped to 600s, longer tasks must be split" IS.

## What changes over time

The capability / Use when / Not for / Output parts should rarely change.
The GOTCHA section should grow — every time the tool trips up an agent
in a new way, add the lesson here. See `refs/skill-template.md` §Common
Mistakes for the skill-level analogue.
