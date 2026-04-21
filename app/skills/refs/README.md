# Shared skill reference documents

These are cross-skill reference docs. Individual SKILL.md files link here
rather than duplicating content inline — keeps each skill lean and
prevents "the rule changed in skill A but skill B still has the old
copy" drift.

Call-out rule: every SKILL.md file that depends on content here MUST
link with a relative path (`[see refs/foo.md](../refs/foo.md)`) so the
link survives when the skill is symlinked into `~/.claude/skills/`.

## Inventory

| Reference | What it is | Who references it |
|---|---|---|
| `shared-rules.md` | Agent-common behavioral rules (sandbox / logging / secrets / defensive programming) | Any skill that touches files, runs bash, or talks to services |
| `tool-description-standard.md` | The 5-element description format for `TOOL_DEFINITIONS` and MCP tools | `writing-skills` / MCP authors |
| `skill-template.md` | The 7-section SKILL.md structure enforced by `_skill_forge` | `writing-skills`; read after you are told to author a new skill |

## How to add a new reference

1. Drop a `.md` file in this directory. File name is kebab-case, no
   leading numbers.
2. Update the table above in **this** README — do not bury the index in
   another file.
3. If the reference encodes a standard that skills must follow, update
   `app/skills/_skill_forge.py` to mention it in the LLM prompt so new
   drafts pick up the rule.
