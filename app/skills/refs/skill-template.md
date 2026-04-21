# SKILL.md template standard

Every auto-generated skill (`_skill_forge.export_package`) and every
hand-authored skill (`submit_skill`) must follow this structure. The
test `tests/test_skill_forge_template.py` enforces it for generated
skills; code review enforces it for hand-authored.

## Why a rigid structure

Skills are read two ways:
1. **By the LLM** on load — it scans sections in order to decide if
   the skill is relevant to the current task.
2. **By humans** during review — maintainers scan for Common Mistakes
   and Next Steps when triaging skill-chain issues.

Free-form skills fail both: the LLM cannot find the "distinguishing"
section, and maintainers cannot spot-check quality without reading the
whole file.

## The 7 required sections

```markdown
---
name: your-skill-name
description: >
  {one-line capability}.
  Use when: {trigger scenarios / user phrasings}.
  Not for: {exclusions + distinction from similar skills}.
  Output: {what the skill produces + side effects}.
  GOTCHA: {pitfalls from observed mistakes}.
category: workflow
tags: [tag1, tag2]
---

# Skill Name

## Core Knowledge
One to two sentences stating WHAT the skill knows and why it is reusable.

## Workflow
Numbered steps (≤7). Each step imperative and verifiable.
1. …
2. …

## Quick Reference
Table or bullet list — scan-optimized cheatsheet for common cases.

## Common Mistakes
The HIGHEST-VALUE section. Populate from real failures.

| Error | Consequence | Fix |
|-------|-------------|-----|
| …     | …           | …   |

## Distinguishing from Other Skills
- vs `other-skill-a`: when to use this instead
- vs `other-skill-b`: when to use this instead

## Next Steps
After this skill completes:
- Invoke `follow-up-skill` when X
- Check Y before marking the task done
```

## Section authoring notes

### Frontmatter description

Follow `refs/tool-description-standard.md` — the same 5-element format.

### Core Knowledge

Resist the urge to write a tutorial. This section answers "what does
this skill know that justifies it existing as a skill?". One paragraph.

### Workflow

≤7 numbered steps. If you need more, split the skill or defer detail
into ancillary files (see Progressive Disclosure below). Every step
should be something the LLM can tell it has completed.

### Quick Reference

This is the "peek while running" section. Prefer a small table over
prose. Examples of good content:
- Tool / argument pairs with meanings
- Error codes and their remediations
- File paths + what lives there

### Common Mistakes

The reason skills exist is to SHIP THE LESSONS. Format:

| Error | Consequence | Fix |
|---|---|---|
| Invoked create_pptx with layout.type="overview" | Silent downgrade to cards; layout loses intent | Use one of the registered types (cover/toc/section/cards/...) |

Add entries every time this skill trips up an agent — the skill gets
smarter over time.

### Distinguishing from Other Skills

Prevent wrong-routing. Format: `- vs SKILL_NAME: when to use this instead`.
One bullet per skill that looks adjacent in purpose.

### Next Steps

The SKILL CHAIN link. Reference skills by their exact `name` from the
MANIFEST.yaml. Validated implicitly — if you reference a nonexistent
name, the bootstrap table shows "(unknown)" and you know something is
wrong.

## Progressive disclosure (for complex skills)

Long skills overflow the LLM's context budget. When a skill exceeds ~200
lines, split ancillary material into files alongside SKILL.md:

```
my-skill/
  SKILL.md           — the 7 required sections, <=200 lines
  scripts/
    run.py           — referenced from Workflow, read via read_file
  refs/
    advanced.md      — heavy docs, referenced via relative link
  templates/
    manifest.j2      — stamped into outputs
```

SKILL.md lists them in the "Quick Reference" section with relative paths.
Agents read them via `read_file` on demand — the LLM never pays the
cost of these files until a step needs them.

## What NOT to include

- **Motivation / history** — why you wrote the skill. Not useful at
  runtime.
- **Alternatives considered** — live in design docs, not the skill.
- **Acknowledgements** — zero runtime value.

If you need to document design decisions, put them in an ADR under
`docs/adr/`, not the skill itself.
