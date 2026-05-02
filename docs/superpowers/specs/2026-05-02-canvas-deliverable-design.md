# Canvas Agent Node Deliverable — Design Spec

**Date:** 2026-05-02
**Author:** brainstormed with @pangalano1983-dev
**Status:** Approved (pending review of this spec)
**Skill:** superpowers/brainstorming

---

## Goal

Make agent-to-agent file passing in canvas workflows **explicit, isolated, and reliable**. Today every agent shares the run's `shared/` root; outputs collide, drafts pollute downstream view, and there's no first-class variable for "what this node produced".

This spec replaces the implicit shared-root model with **per-node subdirectories** plus a single `{{nid.deliverable}}` variable that points to that subdir.

## Background — what we're keeping vs replacing

### Keeping
- Existing artifact-store machinery (`canvas_artifacts.py`): index, audit log, `diff_and_register`. Only the SCOPE of scans changes.
- `success_when.file_glob` early-termination. It's a separate concept from "deliverable" (run-control vs output) and the user has prior workflows that depend on it.
- DAG cascade-skip semantics: a FAILED node automatically marks descendant nodes SKIPPED.

### Replacing
- `agent.working_dir = shared_dir(run_id)` → `shared_dir(run_id) / node_id`
- Snapshot/diff cover the whole shared tree → scoped to the node's own subdir
- (Implementation detail from prior commit `d2a14a6`) the half-merged `deliverable_cfg` parsing in `_exec_agent` — collapses to "always subdir, no config"

## Architecture

### Filesystem Layout

```
~/.tudou_claw/canvas_runs/<run_id>/
├── state.json                 ← unchanged
├── events.jsonl               ← unchanged
├── artifacts.json             ← rel_paths now carry "<node_id>/" prefix
├── audit.jsonl                ← unchanged
└── shared/                    ← run-scoped sandbox root (whole tree readable to agents)
    ├── _run/                  ← (future) run-level inputs (user uploads, cron payload)
    ├── n_search/              ← agent node "n_search" private write zone
    │   ├── _meta.json
    │   ├── AI热点新闻TOP10.md
    │   └── source_links.csv
    ├── n_analyze/             ← agent node "n_analyze"
    │   ├── _meta.json
    │   ├── monetization_plan.md
    │   └── email_log.txt
    └── n_dev/                 ← supports nested deliverables
        ├── _meta.json
        └── app/
            ├── backend/server.py
            └── frontend/index.jsx
```

**Naming**: subdir name = `node_id` (e.g., `n_monwm3sl`). Server-generated, unique within a workflow, stable across retries — no collisions even when the same agent runs in two parallel branches.

**Sanitization**: `_sanitize_node_id` strips `/`, `\`, `..` defensively. Node ids are hex today, but stays robust if future label-derived ids are introduced.

### `_meta.json` per subdir

```json
{
  "node_id": "n_search",
  "node_label": "搜索 AI 热点",
  "agent_id": "3ea6b18d4de5",
  "agent_name": "小土",
  "task_id": "1fc6b32eee50",
  "started_at": 1777730000.0,
  "finished_at": 1777730912.0,
  "deliverable": {
    "abs_path": "/Users/.../shared/n_search",
    "rel_path": "n_search/"
  },
  "artifact_count": 2
}
```

Written atomically (tmp + rename) twice per run: once at agent start (with `started_at` only) so a debugger can identify in-flight runs, and again after artifact post-scan (with `finished_at` and resolved `deliverable`).

Excluded from `snapshot_dir` and `diff_and_register` walks — meta is metadata, not a deliverable.

### Variable Layer (downstream-facing)

```
{{nid.deliverable}}            = "/abs/.../shared/<nid>"   ← always subdir abs path
{{nid.deliverable_relative}}   = "<nid>/"                   ← relative for display
{{nid.output}}                 = task.result               ← LLM text reply (existing)
{{nid.task_id}}                = task.id                   ← existing
{{nid.duration_s}}             = wall-clock seconds         ← existing
{{nid.artifact_count}}         = N                         ← existing
{{nid.artifact_ids}}           = [...]                     ← existing
{{nid.file_<sanitized_name>}}  = abs path of one artifact  ← existing per-file
```

`deliverable_type` and `success_marker_file` from earlier prototype are removed — distinguishing file vs directory at the variable layer is YAGNI per the user's "不用管是文件还是目录" feedback.

### Early Termination — `success_when.file_glob`

Independent feature. When configured on an agent node:

```jsonc
"config": {
  "success_when": { "file_glob": "AI热点新闻TOP10_*.md" }
}
```

The executor polls `shared/<node_id>/` (NOT the whole shared tree) for files matching the glob that didn't exist before the agent started. First match → `task.abort()` + treat node as SUCCEEDED.

The deliverable variable is **unaffected** — it still points to the subdir, regardless of which specific file triggered early stop. Downstream LLM finds the file via `ls` or `read_file`.

### Empty-Deliverable Handling

After the agent completes (LLM-COMPLETED OR success_when triggered OR retry resume), executor checks the subdir contents:

```python
non_meta_files = [
    f for f in subdir.rglob("*")
    if f.is_file() and f.name != "_meta.json"
]
if not non_meta_files:
    raise RuntimeError(
        f"agent {agent_id} produced no deliverable in shared/{node_id}/ "
        f"(error_code: EMPTY_DELIVERABLE)"
    )
```

The exception bubbles up and the engine marks the node FAILED with that error attached. Existing `_drive_loop` cascade-skip propagates: descendant nodes go to SKIPPED, run state = FAILED. The user can use the existing **retry from this node** UI to relaunch the failed agent.

This protects against the "LLM said it wrote a file but actually didn't" silent failure mode that's been observed in practice.

### Backward Compatibility

| Old | New behavior |
|-----|--------------|
| Existing canvas runs (pre-this-spec) — flat `shared/` | Untouched on disk. Replays load fine. |
| Workflows configured with `success_when.file_glob` | Still works. Same field name. |
| Workflows with no `success_when` | LLM-COMPLETED path unchanged. Empty-deliverable check is the only new failure mode. |
| Workflows with old `success_marker_file` output references | The variable is removed; users referencing it will get a `KeyError: workflow variable not defined`. The error message includes the available variables list so they can switch to `{{nid.deliverable}}`. |

`success_marker_file` was added in commit `d2a14a6` (today) and never propagated to any persisted workflow — safe to drop without migration.

### Non-Agent Nodes

`start`, `end`, `decision`, `parallel` — no subdir, no `_meta.json`, no `{{nid.deliverable}}`. They have no producer agent; the variable is only meaningful for `agent` type.

---

## Implementation Status

Already merged in this branch (uncommitted, on top of `d2a14a6`):

- [x] `ArtifactStore.node_dir(run_id, node_id, fresh=False)` — creates subdir, optional rmtree on retry
- [x] `ArtifactStore.write_node_meta(run_id, node_id, meta_dict)` — atomic _meta.json
- [x] `ArtifactStore.snapshot_dir(run_id, subdir="")` and `diff_and_register(..., subdir="")` — both excludes _meta.json
- [x] `_exec_agent` sets `agent.working_dir = node_dir(...)` (with `fresh=True`)
- [x] `_exec_agent` writes _meta.json before chat + after chat
- [x] `_exec_agent` outputs `deliverable` / `deliverable_relative` / drops `deliverable_type`
- [x] `_exec_agent` snapshots/diffs scoped to subdir
- [x] `success_when.file_glob` legacy alias preserved (also accepted as `deliverable.file_glob` for one release; will be removed after spec approval)

Still to do (gated on this spec being approved):

- [ ] Empty-deliverable check after artifact post-scan
- [ ] Drop `deliverable_type` and `success_marker_file` from outputs (left over from `d2a14a6`)
- [ ] Drop `deliverable.file_glob` legacy alias path (was a misstep — `success_when.file_glob` is the canonical name)
- [ ] Validator: `success_when` schema (already in place from `d2a14a6`); double-check the spec accepts what we want
- [ ] Frontend: keep "完成条件 — 文件名" input as-is, but rename label to "成功条件 — 交付文件名 (可选)" and update the help text to mention the deliverable concept
- [ ] Documentation in `docs/`: add a "writing canvas workflows" section pointing here

---

## Self-Review

**Spec coverage** — every decision from the brainstorming dialog is in the doc:
- Per-node subdir (✓ Filesystem Layout)
- Always-subdir deliverable, no file/dir distinction (✓ Variable Layer)
- success_when retained (✓ Early Termination)
- Empty-deliverable → FAILED + cascade (✓ Empty-Deliverable Handling)
- _meta.json visible (✓ noted)
- No downstream filter / YAGNI (✓ noted in Variable Layer)
- Non-agent nodes excluded (✓ section)

**Placeholder scan** — no TBDs, no "implement later", every code block / signature is concrete. ✓

**Type consistency** — `node_id`, `subdir`, `rel_path` named consistently throughout. `deliverable` is always a string (abs path); `deliverable_relative` always ends in `/` for directories. ✓

**Scope** — single subsystem (canvas executor + artifact store + frontend node config panel). Not multi-project, no further decomposition needed. ✓

---

## Handoff

Once user approves this spec, transition to **superpowers/writing-plans** to produce a checklist-style implementation plan in `docs/superpowers/plans/2026-05-02-canvas-deliverable-implementation.md` covering:

1. Empty-deliverable check (backend)
2. Cleanup of leftover `deliverable_type` / `success_marker_file` / `deliverable.file_glob` alias
3. Frontend label/help-text update
4. Documentation in `docs/`
5. Verification (rerun the AI 热点 workflow + try empty-deliverable case)
6. Commit per task
