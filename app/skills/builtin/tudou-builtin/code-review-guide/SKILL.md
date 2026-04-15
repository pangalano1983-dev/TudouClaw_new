---
name: code-review-guide
description: >
  Use this skill whenever you are asked to review code changes, a diff, or a
  pull request. Produces structured, actionable review comments focused on
  correctness, security, readability, and test coverage — not stylistic nits.
metadata:
  source: maintainer
  tags: "code-review, quality, pull-request"
  languages: "python, javascript, typescript, go, rust"
  versions: "1.0.0"
  updated-on: "2026-04-11"
---

# Code Review Guide

This skill gives the agent a consistent rubric to follow when reviewing code.
It is a *guidance-only* skill (runtime: markdown) — no executable side effects.

## When this skill activates

Trigger keywords: "review this PR", "check my diff", "审核代码", "帮我看看这段代码".

## Review rubric

Go through the code in this order. For each category, only call out real
problems — do not pad the review with generic advice.

1. **Correctness** — Does the code do what the PR description says it does?
   Walk through the critical path with concrete inputs. Point out edge cases
   (null, empty, boundary) the author forgot.

2. **Security** — Untrusted input validation, SQL/shell injection, secret
   handling, authZ checks around new endpoints, CSRF/XSS for web code.

3. **Concurrency & resource safety** — Race conditions, unreleased locks,
   connections, or file handles. Long-running work on request threads.

4. **Readability** — Names that lie, dead code, magic numbers, functions
   doing three things at once. Skip purely cosmetic preferences.

5. **Test coverage** — Are the new branches tested? Does the test actually
   assert behavior, or does it just call the code without checking output?

## Output format

Produce comments grouped by severity:

- **BLOCKING** — must fix before merge
- **SUGGESTION** — should fix, not blocking
- **NIT** — minor, optional

Each comment: file + line, the issue in one sentence, the fix in one sentence.
Do not say "LGTM" unless you actually walked through all five categories above.

## Anti-patterns to avoid in your own review

- Do not ask the author to add comments or docstrings unless the code is
  genuinely unclear.
- Do not nitpick formatting that a linter already catches.
- Do not propose large refactors inside an unrelated PR.
