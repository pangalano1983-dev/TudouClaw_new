"""
Canvas workflow execution engine (HANDOFF [D]).

Consumes the schema authored in :mod:`app.canvas_workflows`. One
``WorkflowRun`` per execution; the engine drives the run by walking the
DAG, invoking per-node-type executors, and persisting state + an
append-only event log.

MVP boundaries (HANDOFF [D]):
  * **Implemented node types**: start, end, agent, tool.
  * **Skipped (clear error)**: decision, parallel — the run fails with
    a structured "node type not yet supported" error so the author
    knows what to remove. Will land in a follow-up.
  * **No retries** — first failure terminates the run.
  * **No human-in-the-loop pause nodes**.
  * **Variable substitution** (``{{node_id.key}}``) is implemented here
    in the executor — HANDOFF [H] is now just the UI affordance.

Persistence layout (under ``<data_dir>/canvas_runs/``):

  * ``<run_id>.json`` — run state snapshot (overwritten on each
    transition; tiny, ~1KB).
  * ``<run_id>.events.jsonl`` — append-only event log, one JSON object
    per line. Drives the SSE event stream that the canvas UI ([E])
    consumes for live highlighting.

Concurrency: each run executes on its own daemon thread; multiple runs
of the same workflow can race in the engine, but each run owns its own
state file. The engine itself is thread-safe (lock around the run
registry).
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("tudou.canvas_executor")


# ── State enums ─────────────────────────────────────────────────────────


class RunState(str, Enum):
    PENDING = "pending"      # created, not yet started
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ABORTED = "aborted"


class NodeState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


TERMINAL_RUN_STATES = {RunState.SUCCEEDED, RunState.FAILED, RunState.ABORTED}
TERMINAL_NODE_STATES = {NodeState.SUCCEEDED, NodeState.FAILED,
                        NodeState.SKIPPED}


# ── Variable substitution ───────────────────────────────────────────────


_VAR_PATTERN = re.compile(r"\{\{\s*([A-Za-z0-9_.\-]+)\s*\}\}")


def _substitute_vars(template: Any, vars_dict: dict[str, Any]) -> Any:
    """Replace ``{{node_id.key}}`` references in any string field.

    Recurses into dicts and lists. Non-string scalars (int, bool, None)
    pass through unchanged. Missing variables raise ``KeyError`` with a
    clear message — silently substituting empty string would mask bugs.
    """
    if isinstance(template, str):
        def _repl(m: re.Match) -> str:
            key = m.group(1)
            if key not in vars_dict:
                raise KeyError(
                    f"workflow variable not defined: {{{{{key}}}}} "
                    f"(available: {sorted(vars_dict.keys())[:5]}...)"
                )
            return str(vars_dict[key])
        return _VAR_PATTERN.sub(_repl, template)
    if isinstance(template, dict):
        return {k: _substitute_vars(v, vars_dict) for k, v in template.items()}
    if isinstance(template, list):
        return [_substitute_vars(v, vars_dict) for v in template]
    return template


# ── Run model ───────────────────────────────────────────────────────────


@dataclass
class WorkflowRun:
    """One execution instance of a canvas workflow."""
    id: str = field(default_factory=lambda: f"run-{uuid.uuid4().hex[:12]}")
    workflow_id: str = ""
    workflow_name: str = ""
    started_by: str = ""
    state: RunState = RunState.PENDING
    started_at: float = 0.0
    finished_at: float = 0.0
    error: str = ""
    # Per-node state — keyed by node id from the workflow definition.
    node_states: dict[str, NodeState] = field(default_factory=dict)
    node_started: dict[str, float] = field(default_factory=dict)
    node_finished: dict[str, float] = field(default_factory=dict)
    node_errors: dict[str, str] = field(default_factory=dict)
    # Variable store — populated as nodes complete. Keys are
    # ``{node_id}.{output_key}`` strings.
    vars: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "workflow_name": self.workflow_name,
            "started_by": self.started_by,
            "state": self.state.value,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "node_states": {k: v.value for k, v in self.node_states.items()},
            "node_started": dict(self.node_started),
            "node_finished": dict(self.node_finished),
            "node_errors": dict(self.node_errors),
            "vars": dict(self.vars),
        }


# ── Persistence ─────────────────────────────────────────────────────────


class RunStore:
    """Persists run state + append-only event log to disk."""

    def __init__(self, root_dir: str | Path):
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, threading.Lock] = {}
        self._registry_lock = threading.Lock()

    def _lock_for(self, run_id: str) -> threading.Lock:
        with self._registry_lock:
            lk = self._locks.get(run_id)
            if lk is None:
                lk = threading.Lock()
                self._locks[run_id] = lk
            return lk

    def _state_path(self, run_id: str) -> Path:
        return self.root_dir / f"{run_id}.json"

    def _events_path(self, run_id: str) -> Path:
        return self.root_dir / f"{run_id}.events.jsonl"

    def save_state(self, run: WorkflowRun) -> None:
        path = self._state_path(run.id)
        tmp = path.with_suffix(".json.tmp")
        with self._lock_for(run.id):
            tmp.write_text(json.dumps(run.to_dict(), ensure_ascii=False,
                                      indent=2), encoding="utf-8")
            os.replace(tmp, path)

    def load_state(self, run_id: str) -> dict | None:
        path = self._state_path(run_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error("failed to read run %s: %s", run_id, e)
            return None

    def append_event(self, run_id: str, event: dict) -> None:
        """Append one event to the run's JSONL log. Each event must
        already contain ``ts`` (unix epoch seconds) and ``type``."""
        path = self._events_path(run_id)
        line = json.dumps(event, ensure_ascii=False)
        with self._lock_for(run_id):
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")

    def read_events(self, run_id: str, since_offset: int = 0
                    ) -> tuple[list[dict], int]:
        """Read events from byte offset ``since_offset``.

        Returns ``(events, new_offset)``. Used by the SSE endpoint to
        stream incremental progress without re-sending older events.
        """
        path = self._events_path(run_id)
        if not path.exists():
            return [], 0
        with self._lock_for(run_id):
            try:
                with open(path, "rb") as f:
                    f.seek(since_offset)
                    raw = f.read()
                    new_offset = since_offset + len(raw)
            except OSError as e:
                logger.warning("read_events %s failed: %s", run_id, e)
                return [], since_offset
        events = []
        for line in raw.decode("utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events, new_offset

    def list_runs_for_workflow(self, workflow_id: str) -> list[dict]:
        """Return run summaries for one workflow, newest first."""
        out = []
        for f in self.root_dir.glob("run-*.json"):
            if f.name.endswith(".events.jsonl"):
                continue
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                if d.get("workflow_id") == workflow_id:
                    out.append({
                        "id": d.get("id"),
                        "state": d.get("state"),
                        "started_at": d.get("started_at"),
                        "finished_at": d.get("finished_at"),
                        "error": d.get("error", "")[:200],
                    })
            except Exception:
                continue
        out.sort(key=lambda r: -(r.get("started_at") or 0))
        return out


# ── Engine ──────────────────────────────────────────────────────────────


class WorkflowEngine:
    """Drives one or more ``WorkflowRun`` instances to completion.

    The engine holds no per-workflow scheduling state — runs are
    triggered by an external caller (typically the canvas API). Each
    triggered run gets its own daemon thread.
    """

    def __init__(self, store: RunStore, hub: Any = None):
        self.store = store
        self.hub = hub
        self._runs: dict[str, WorkflowRun] = {}
        self._lock = threading.RLock()

    # ── Triggering / lookup ──

    def trigger(self, workflow: dict, started_by: str = "") -> WorkflowRun:
        """Kick off a new run of ``workflow``.

        ``workflow`` is the full dict from
        :meth:`canvas_workflows.WorkflowStore.get`. The engine does NOT
        re-check ``executable_status == "ready"`` here — that's the
        caller's job (the API layer does it).

        Returns the ``WorkflowRun`` so the caller can poll / surface
        its id.
        """
        # Pre-flight validation: the same checks the store does on
        # status transition. Catches the "marked ready then someone
        # deleted a referenced agent" case.
        from .canvas_workflows import WorkflowStore
        issues = WorkflowStore.validate_for_execution(workflow)
        if issues:
            raise ValueError(
                "workflow failed pre-flight validation:\n  • "
                + "\n  • ".join(issues)
            )

        run = WorkflowRun(
            workflow_id=str(workflow.get("id", "")),
            workflow_name=str(workflow.get("name", "")),
            started_by=started_by,
            state=RunState.PENDING,
            started_at=time.time(),
        )
        # Initialize per-node state
        for n in workflow.get("nodes") or []:
            run.node_states[n["id"]] = NodeState.PENDING

        with self._lock:
            self._runs[run.id] = run
        self.store.save_state(run)
        self._emit(run, "run_created", {})

        t = threading.Thread(
            target=self._drive,
            args=(run, workflow),
            name=f"canvas-run-{run.id[:8]}",
            daemon=True,
        )
        t.start()
        return run

    def get_run(self, run_id: str) -> WorkflowRun | None:
        with self._lock:
            return self._runs.get(run_id)

    # ── Event emission ──

    def _emit(self, run: WorkflowRun, event_type: str,
              payload: dict | None = None) -> None:
        evt = {
            "ts": time.time(),
            "run_id": run.id,
            "type": event_type,
            "data": payload or {},
        }
        try:
            self.store.append_event(run.id, evt)
        except Exception as e:
            logger.warning("append_event failed for %s: %s", run.id, e)

    # ── Run driver ──

    def _drive(self, run: WorkflowRun, workflow: dict) -> None:
        """Walk the DAG and execute nodes in topological order.

        MVP scheduling: pick any node whose deps are all SUCCEEDED, run
        it, repeat. Single-threaded execution — parallel fan-out is
        deferred (when the parallel node type lands, this driver will
        spawn children and wait).
        """
        run.state = RunState.RUNNING
        run.started_at = time.time()
        self.store.save_state(run)
        self._emit(run, "run_started", {
            "workflow_id": run.workflow_id,
            "workflow_name": run.workflow_name,
        })

        nodes_by_id = {n["id"]: n for n in workflow.get("nodes") or []}
        edges = workflow.get("edges") or []

        # Build deps map — node N depends on every node that has an
        # outgoing edge into N.
        deps: dict[str, list[str]] = {nid: [] for nid in nodes_by_id}
        for e in edges:
            src, dst = e.get("from"), e.get("to")
            if src in nodes_by_id and dst in nodes_by_id:
                deps[dst].append(src)

        try:
            while True:
                ready = self._pick_ready(run, nodes_by_id, deps)
                if ready is None:
                    # Nothing ready — either we're done, or we've stalled.
                    if all(s in TERMINAL_NODE_STATES
                           for s in run.node_states.values()):
                        # All nodes terminal → run done.
                        any_failed = any(
                            s == NodeState.FAILED
                            for s in run.node_states.values()
                        )
                        if any_failed:
                            self._finish(run, RunState.FAILED,
                                         "one or more nodes failed")
                        else:
                            self._finish(run, RunState.SUCCEEDED, "")
                        return
                    # Stalled — some nodes pending but no deps satisfied.
                    # Means a cycle (validate should've caught this) or a
                    # disconnected subgraph. Bail.
                    pending = [nid for nid, s in run.node_states.items()
                               if s == NodeState.PENDING]
                    self._finish(run, RunState.FAILED,
                                 f"stalled — pending nodes have unsatisfied "
                                 f"deps: {pending[:5]}")
                    return

                node = nodes_by_id[ready]
                self._execute_node(run, node)

        except Exception as e:
            logger.exception("run %s crashed", run.id)
            self._finish(run, RunState.FAILED,
                         f"engine crashed: {type(e).__name__}: {e}")

    def _pick_ready(self, run: WorkflowRun,
                    nodes_by_id: dict[str, dict],
                    deps: dict[str, list[str]]) -> str | None:
        """Return the id of one node that's ready to run, or None."""
        for nid, node in nodes_by_id.items():
            if run.node_states.get(nid) != NodeState.PENDING:
                continue
            # All deps must be SUCCEEDED to proceed. If any dep is
            # FAILED or SKIPPED, we mark this node SKIPPED (not FAILED
            # — its inputs never landed, so it never had a chance).
            dep_states = [run.node_states.get(d, NodeState.PENDING)
                          for d in deps.get(nid, [])]
            if any(s in (NodeState.FAILED, NodeState.SKIPPED)
                   for s in dep_states):
                # Skip this node — upstream is broken
                run.node_states[nid] = NodeState.SKIPPED
                run.node_finished[nid] = time.time()
                self.store.save_state(run)
                self._emit(run, "node_skipped", {
                    "node_id": nid, "node_type": node.get("type"),
                    "reason": "upstream failed or skipped",
                })
                # Loop again to pick the next one
                continue
            if all(s == NodeState.SUCCEEDED for s in dep_states):
                return nid
        return None

    def _execute_node(self, run: WorkflowRun, node: dict) -> None:
        """Execute one node end-to-end: state transitions + dispatch +
        event emission + variable capture.

        Failure of an individual node does NOT raise — it's recorded
        as NodeState.FAILED so the driver can decide whether to skip
        downstream or stop.
        """
        nid = node["id"]
        ntype = node.get("type", "")
        run.node_states[nid] = NodeState.RUNNING
        run.node_started[nid] = time.time()
        self.store.save_state(run)
        self._emit(run, "node_started", {
            "node_id": nid, "node_type": ntype,
            "label": node.get("label", ""),
        })

        try:
            executor = _NODE_EXECUTORS.get(ntype)
            if executor is None:
                raise NotImplementedError(
                    f"node type {ntype!r} not supported in MVP "
                    f"(decision/parallel are deferred — see canvas_executor.py)"
                )

            # Variable substitution on the config bag before dispatch.
            raw_config = node.get("config") or {}
            try:
                config = _substitute_vars(raw_config, run.vars)
            except KeyError as ke:
                raise RuntimeError(f"variable substitution failed: {ke}")

            outputs = executor(self, run, node, config)
            # Capture outputs as variables {node_id.key}
            if isinstance(outputs, dict):
                for k, v in outputs.items():
                    run.vars[f"{nid}.{k}"] = v
            run.node_states[nid] = NodeState.SUCCEEDED
            run.node_finished[nid] = time.time()
            self.store.save_state(run)
            self._emit(run, "node_succeeded", {
                "node_id": nid, "node_type": ntype,
                "outputs": outputs if isinstance(outputs, dict) else {},
            })
        except Exception as e:
            run.node_states[nid] = NodeState.FAILED
            run.node_finished[nid] = time.time()
            run.node_errors[nid] = f"{type(e).__name__}: {e}"
            self.store.save_state(run)
            self._emit(run, "node_failed", {
                "node_id": nid, "node_type": ntype,
                "error": run.node_errors[nid],
            })

    def _finish(self, run: WorkflowRun, state: RunState, error: str) -> None:
        run.state = state
        run.finished_at = time.time()
        run.error = error
        self.store.save_state(run)
        self._emit(run, f"run_{state.value}", {
            "duration_s": run.finished_at - run.started_at,
            "error": error,
        })


# ── Per-type node executors ─────────────────────────────────────────────
#
# Signature: ``executor(engine, run, node, resolved_config) -> dict``
# where the returned dict's keys become variables under ``{node_id.key}``.
# Raise an exception to mark the node failed; the message goes into the
# event stream as the failure reason.


def _exec_start(engine: WorkflowEngine, run: WorkflowRun,
                node: dict, config: dict) -> dict:
    """Start node: no-op success. Marks the run as actively executing."""
    return {"started_at": time.time()}


def _exec_end(engine: WorkflowEngine, run: WorkflowRun,
              node: dict, config: dict) -> dict:
    """End node: no-op success. The driver detects all-terminal-states
    and finalizes the run; this just lets the end node show as succeeded
    in the UI."""
    return {"finished_at": time.time()}


def _exec_agent(engine: WorkflowEngine, run: WorkflowRun,
                node: dict, config: dict) -> dict:
    """Agent node: posts a chat turn to the configured agent and waits
    for completion.

    Required config:
      * ``agent_id`` — which agent to talk to
      * ``prompt``  — the user-message-equivalent text to send

    Optional config:
      * ``timeout`` — seconds to wait for completion (default 300)
    """
    if engine.hub is None:
        raise RuntimeError(
            "agent node requires hub to be wired into the engine"
        )

    agent_id = config.get("agent_id", "")
    prompt = config.get("prompt", "")
    timeout = float(config.get("timeout", 300))
    if not agent_id:
        raise ValueError("agent node missing config.agent_id")
    if not prompt or not str(prompt).strip():
        raise ValueError("agent node missing config.prompt")

    agent = engine.hub.get_agent(agent_id) if hasattr(
        engine.hub, "get_agent") else None
    if agent is None:
        raise RuntimeError(f"agent {agent_id!r} not found in hub")

    # Submit chat turn — chat_async returns a ChatTask we can poll.
    task = agent.chat_async(str(prompt),
                            source=f"canvas:{run.workflow_id}:{node['id']}")

    # Poll until terminal. ChatTaskStatus enum has terminal members
    # COMPLETED / FAILED / ABORTED.
    from .chat_task import ChatTaskStatus
    deadline = time.time() + timeout
    while time.time() < deadline:
        if task.status in (ChatTaskStatus.COMPLETED,
                           ChatTaskStatus.FAILED,
                           ChatTaskStatus.ABORTED):
            break
        time.sleep(0.5)
    else:
        # Timeout — try to abort the task so we don't leave it running
        try:
            task.abort()
        except Exception:
            pass
        raise TimeoutError(
            f"agent node timed out after {timeout}s "
            f"(task {task.id}, status {task.status.value})"
        )

    if task.status != ChatTaskStatus.COMPLETED:
        raise RuntimeError(
            f"agent task {task.id} ended in {task.status.value}: "
            f"{(task.error or task.result or '')[:200]}"
        )

    return {
        "output": task.result or "",
        "task_id": task.id,
        "duration_s": task.updated_at - task.created_at,
    }


def _exec_tool(engine: WorkflowEngine, run: WorkflowRun,
               node: dict, config: dict) -> dict:
    """Tool node: invokes a granted skill via the registry.

    Required config:
      * ``tool_name`` — the skill id (validated by the canvas store)

    Optional config:
      * ``agent_id`` — which agent's grant context to invoke under
                       (the registry tracks per-agent grants).
      * ``inputs``   — dict of inputs forwarded to the skill.
    """
    if engine.hub is None:
        raise RuntimeError(
            "tool node requires hub to be wired into the engine"
        )

    tool_name = config.get("tool_name", "")
    agent_id = config.get("agent_id", "")
    inputs = config.get("inputs") or {}
    if not tool_name:
        raise ValueError("tool node missing config.tool_name")
    if not isinstance(inputs, dict):
        raise ValueError("tool node config.inputs must be a dict")

    reg = getattr(engine.hub, "skill_registry", None)
    if reg is None:
        raise RuntimeError("hub.skill_registry not available")

    result = reg.invoke(tool_name, agent_id, inputs)
    # Skills can return arbitrary shapes — wrap scalar/list returns
    # into a dict so downstream {{node.output}} substitution always
    # finds something.
    if isinstance(result, dict):
        out = dict(result)
        out.setdefault("output", result)
        return out
    return {"output": result}


_NODE_EXECUTORS: dict[str, Callable] = {
    "start": _exec_start,
    "end":   _exec_end,
    "agent": _exec_agent,
    "tool":  _exec_tool,
}


# ── Module-level singleton ──────────────────────────────────────────────


_ENGINE: WorkflowEngine | None = None
_ENGINE_LOCK = threading.Lock()


def init_engine(store_root: str | Path, hub: Any = None) -> WorkflowEngine:
    """Initialize and stash the singleton engine. Idempotent."""
    global _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is None:
            store = RunStore(store_root)
            _ENGINE = WorkflowEngine(store, hub=hub)
        elif hub is not None and _ENGINE.hub is None:
            _ENGINE.hub = hub
    return _ENGINE


def get_engine() -> WorkflowEngine | None:
    return _ENGINE
