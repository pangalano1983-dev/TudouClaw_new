"""Guardrail trip-wire protocol (borrowed from openai-agents-python).

Why this exists
===============
TudouClaw already has several independent "is this safe?" checks:

  * ``app.security.full_leak_check`` — scans content for API keys / PII
    / hardcoded env values before wiki ingest (see
    ``app.tools_split.knowledge._tool_wiki_ingest``).
  * ``app.auth.ToolPolicy.check_tool`` — rule-chain that decides
    allow / deny / needs_approval for every tool call.
  * ``app.auth.ToolPolicy.check_skill_call`` — skill-level escalation
    gate.

Each one returns a different shape (``{found, leaks}`` / ``(verdict,
reason)`` / ``(verdict, reason)``) and each call site re-implements
its own branching on top. This module gives them a uniform interface
so future call sites can compose multiple checks the same way:

    output = guardrail.run(payload)
    if output.tripwire_triggered:
        raise GuardrailTripwireTriggered(...)

The protocol is borrowed from openai-agents-python's
``src/agents/guardrail.py`` (``GuardrailFunctionOutput`` with
``output_info`` + ``tripwire_triggered``). We deliberately keep this
module synchronous — TudouClaw's checks are CPU-bound regex scans, not
LLM calls, so the async machinery from the upstream library would be
dead weight.

This module is **additive**: existing call sites (wiki_ingest,
ToolPolicy.check_tool) keep working unchanged. New code that wants the
unified interface imports from here; legacy code can migrate page by
page.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# ─────────────────────────────────────────────────────────────────────
# Protocol types
# ─────────────────────────────────────────────────────────────────────


@dataclass
class GuardrailFunctionOutput:
    """Result of a single guardrail check.

    ``output_info`` carries diagnostic detail (matched leaks, rule that
    fired, …) so callers can format a useful message. ``tripwire_triggered``
    is the boolean decision: True means STOP, raise the exception.
    """

    output_info: Any = None
    tripwire_triggered: bool = False


class GuardrailTripwireTriggered(Exception):
    """Raised when a guardrail trips. Caller should halt execution."""

    def __init__(self, guardrail_name: str, output: GuardrailFunctionOutput):
        self.guardrail_name = guardrail_name
        self.output = output
        super().__init__(
            f"guardrail {guardrail_name!r} tripped: {output.output_info!r}"
        )


@dataclass
class Guardrail:
    """A named callable that returns ``GuardrailFunctionOutput``.

    ``function`` may take any number of positional args — the runner
    forwards whatever the caller passes. We don't pin the signature
    (unlike upstream's typed Generic) because TudouClaw's checks have
    heterogeneous inputs (str blob vs. tool_name+arguments+agent_ctx).
    """

    name: str
    function: Callable[..., GuardrailFunctionOutput]

    def run(self, *args, **kwargs) -> GuardrailFunctionOutput:
        out = self.function(*args, **kwargs)
        if not isinstance(out, GuardrailFunctionOutput):
            # Defensive: a misbehaving check returned the wrong shape.
            # Treat as non-trip rather than blowing up callers.
            return GuardrailFunctionOutput(
                output_info={"raw": out, "warning": "non-conformant return"},
                tripwire_triggered=False,
            )
        return out


def guardrail(name: str = "") -> Callable[
    [Callable[..., GuardrailFunctionOutput]], Guardrail
]:
    """Decorator: turn a function into a ``Guardrail``.

        @guardrail("wiki_leak")
        def check(text: str) -> GuardrailFunctionOutput:
            ...
    """
    def _wrap(fn: Callable[..., GuardrailFunctionOutput]) -> Guardrail:
        return Guardrail(name=name or fn.__name__, function=fn)
    return _wrap


# ─────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────


@dataclass
class GuardrailRunResult:
    """Combined result of running a list of guardrails."""

    results: list[tuple[str, GuardrailFunctionOutput]] = field(
        default_factory=list
    )
    tripped: Optional[tuple[str, GuardrailFunctionOutput]] = None


def run_guardrails(
    guardrails: list[Guardrail],
    *args,
    raise_on_trip: bool = False,
    **kwargs,
) -> GuardrailRunResult:
    """Run guardrails in order; stop at the first that trips.

    Returns the full result (so non-tripping diagnostics are still
    available). If ``raise_on_trip`` and a wire trips, raises
    ``GuardrailTripwireTriggered`` after recording the result.
    """
    res = GuardrailRunResult()
    for g in guardrails:
        out = g.run(*args, **kwargs)
        res.results.append((g.name, out))
        if out.tripwire_triggered:
            res.tripped = (g.name, out)
            if raise_on_trip:
                raise GuardrailTripwireTriggered(g.name, out)
            break
    return res


# ─────────────────────────────────────────────────────────────────────
# Built-in adapters around existing TudouClaw checks
# ─────────────────────────────────────────────────────────────────────


@guardrail("wiki_leak_check")
def wiki_leak_guardrail(text: str) -> GuardrailFunctionOutput:
    """Wrap ``app.security.full_leak_check`` as a guardrail.

    Trips when the scan finds any API key / PII / env-value leak in
    the provided text. ``output_info`` carries the full leak list so
    the caller can compose a useful error message.
    """
    try:
        from ...security import full_leak_check
    except ImportError:
        # Defensive: if security module is unavailable, don't block.
        return GuardrailFunctionOutput(
            output_info={"error": "security module unavailable"},
            tripwire_triggered=False,
        )
    report = full_leak_check(text or "")
    return GuardrailFunctionOutput(
        output_info=report,
        tripwire_triggered=bool(report.get("found")),
    )


def tool_policy_guardrail(policy) -> Guardrail:
    """Build a guardrail wrapping ``ToolPolicy.check_tool``.

    Usage:

        g = tool_policy_guardrail(policy)
        out = g.run(tool_name="bash", arguments={"command": "rm -rf /"},
                    agent_id="...", agent_name="...", agent_priority=3)
        if out.tripwire_triggered: raise ...

    Trips on verdict ``"deny"``. Verdicts ``needs_approval`` /
    ``agent_approvable`` are NOT trip-wires — they need human-in-the-loop
    handling, which is Borrow 4's territory.
    """
    def _check(tool_name: str, arguments: dict, agent_id: str = "",
               agent_name: str = "", agent_priority: int = 3
               ) -> GuardrailFunctionOutput:
        verdict, reason = policy.check_tool(
            tool_name, arguments,
            agent_id=agent_id, agent_name=agent_name,
            agent_priority=agent_priority,
        )
        return GuardrailFunctionOutput(
            output_info={"verdict": verdict, "reason": reason,
                         "tool": tool_name},
            tripwire_triggered=(verdict == "deny"),
        )
    return Guardrail(name="tool_policy", function=_check)


__all__ = [
    "GuardrailFunctionOutput",
    "GuardrailTripwireTriggered",
    "Guardrail",
    "GuardrailRunResult",
    "guardrail",
    "run_guardrails",
    "wiki_leak_guardrail",
    "tool_policy_guardrail",
]
