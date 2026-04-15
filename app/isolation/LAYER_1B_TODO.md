# Layer 1b — Multi-Node Isolation (Pending)

This file records work deferred from Layer 1a. Layer 1a shipped
single-node physical isolation (local subprocess workers with jail +
sandbox + capability gatekeeping). Layer 1b extends the same design
to multi-node / cross-machine deployments.

**Status**: design agreed, implementation deferred until Layer 1a has
been integrated with Agent/Hub and validated end-to-end in Portal.

## Agreed design decisions

| # | Decision | Choice |
|---|----------|--------|
| 1 | Topology | Both A (main → node) and B (node → main reverse register) |
| 2 | NodeAgent shape | Thin first (byte relay + chan_id routing), fat later if needed |
| 3 | `chan_id` in protocol wire format | **Done in Layer 1a** — 4-byte chan_id is already part of every frame |
| 4 | `shared_workspace` across nodes | Assume NFS / NAS mount points with identical paths on each node; no built-in replication |
| 5 | Rollout | Layer 1a (local, abstractions in place) → Layer 1b (network + node agent + scheduler) |

## Already in place from Layer 1a

- `app/isolation/protocol.py` — frame protocol already carries `chan_id`. No wire format changes needed for 1b.
- `app/isolation/transport.py` — `Transport` base class + `StdioTransport`. **`SocketTransport` is a stub** awaiting Layer 1b implementation.
- `app/isolation/worker_pool.py` — split into `WorkerChannel` (transport-agnostic), `LocalWorkerLauncher`, `WorkerProcess` facade, `WorkerPool`. Adding a `RemoteWorkerLauncher` alongside `LocalWorkerLauncher` slots in with no changes to `WorkerChannel` or `WorkerProcess`.
- `app/agent_worker.py` — already writes frames with `chan_id=0` and ignores inbound chan_id, so it works unchanged whether the transport is stdio or (future) a NodeAgent relay.

## Layer 1b implementation checklist

### 1. `app/isolation/transport.py` — real `SocketTransport`

- [ ] TCP connect + TLS handshake (`ssl.SSLContext`, cert-based mTLS preferred)
- [ ] `send(frame, chan_id)` / `recv() -> (chan_id, Frame)` using the existing protocol.py helpers (they're stream-agnostic)
- [ ] Write lock for thread safety
- [ ] Close on EOF / reset → raise `TransportError`
- [ ] Reconnect-on-drop policy (at the WorkerChannel level, not transport)

### 2. `app/isolation/node_agent.py` — NodeAgent daemon (thin)

Runs as `python -m app.isolation.node_agent --listen 0.0.0.0:7631 --token-file ...` on each worker machine. Responsibilities:

- [ ] Listen on TLS TCP for incoming main-process connections
- [ ] First frame must be an auth frame with shared-secret token; reject on mismatch
- [ ] Receive `spawn_worker` control frame with boot_config → spawn `python -m app.agent_worker` locally with the same flow as `LocalWorkerLauncher`
- [ ] Bidirectional byte relay between TCP socket and worker stdin/stdout, **stamping chan_id on the way up (worker writes 0, relay rewrites to the worker's assigned id) and stripping it on the way down**
- [ ] Worker stderr → multiplexed into the main TCP stream as EVENT frames (`kind2="stderr"`)
- [ ] Graceful shutdown: receive `shutdown` control frame → kill all local workers → close
- [ ] Worker lifecycle tracking: reap dead workers, propagate exit via TransportError upstream

### 3. `app/isolation/remote_launcher.py` — `RemoteWorkerLauncher`

Satisfies the same duck-type as `LocalWorkerLauncher.launch(...)` but talks to a NodeAgent:

- [ ] Take a pre-established `SocketTransport` (one per TCP connection, shared across multiple workers via chan_id multiplexing)
- [ ] Allocate a new chan_id, send `spawn_worker` control frame with boot_config
- [ ] Wait for the worker's `ready` event (same handshake as local)
- [ ] Return a `WorkerProcess` with `subprocess=None` and a WorkerChannel bound to the socket + chan_id

### 4. `app/isolation/node_registry.py` — node discovery

Two config-driven paths (supports both topology A and B):

- [ ] **Topology A** (main → node): read `~/.tudou_claw/cluster/nodes.yaml`, connect to each on startup, track alive/dead
- [ ] **Topology B** (node → main): listen on a registration port, accept incoming NodeAgent registrations (auth with shared secret), add to registry
- [ ] Heartbeat protocol: NodeAgent periodically sends `heartbeat` events with `capabilities` + `current_workers` / `max_workers` + load metrics
- [ ] Node state: `online` / `degraded` / `offline` / `draining`
- [ ] Expose `list_nodes()` / `get_node(id)` / subscribe to changes

### 5. `app/isolation/scheduler.py` — placement

- [ ] Consistent-hash ring: `agent_id → node`, persists placement
- [ ] `~/.tudou_claw/cluster/placements.json` for per-agent stickiness across restarts
- [ ] On node offline: mark all its workers as dead, future `get_or_spawn` picks a new node (work_dir has to be replicated via shared_workspace NAS or recreated fresh; doc this caveat)
- [ ] `required_node_labels` on agent profile → filter candidate nodes
- [ ] Load balancing: avoid nodes at >= `max_workers`
- [ ] Fallback: if all remote nodes are offline, fall back to local launcher

### 6. `WorkerPool` upgrade

- [ ] Inject `Scheduler` into the pool
- [ ] `get_or_spawn(agent_id, ...)` → `scheduler.pick_node(agent_id)` → picks `LocalWorkerLauncher` (node is "local") or `RemoteWorkerLauncher` (node is remote)
- [ ] Notify routing: `notify_agent(agent_id, ...)` must know which node holds the worker and route via that node's channel

### 7. Security / secrets

- [ ] Generate private CA + per-node certificate script (`scripts/gen_cluster_certs.sh`)
- [ ] `~/.tudou_claw/cluster/ca.pem` / `node.pem` / `node.key`
- [ ] `~/.tudou_claw/cluster/node_token` — shared secret for first-frame auth
- [ ] Rotate token / cert instructions

### 8. Portal integration

- [ ] `portal_routes_get.py` — new `/api/cluster/nodes` endpoint listing nodes + status + current workers
- [ ] Portal UI: "Cluster" tab showing node registry, live worker count per node, scheduling events
- [ ] Per-agent view: show which node the worker is on, last placement timestamp

### 9. Tests

- [ ] Multi-node E2E: spawn one NodeAgent on localhost port X, connect main to it, spawn a worker there, run the same 9 tool-call smoke tests through the TCP path
- [ ] Node failure: kill NodeAgent mid-call, confirm `WorkerCrashedError` + respawn on another node
- [ ] Scheduler stickiness: same agent_id always lands on same node when node is alive
- [ ] Consistent hash rebalancing: adding a new node only reshuffles `1/N` of placements
- [ ] Auth rejection: wrong token drops connection
- [ ] chan_id multiplexing: two workers on one TCP connection, verify frames don't cross-talk

### 10. Documentation

- [ ] `docs/ISOLATION.md` — single-node and multi-node architecture, threat model, config reference
- [ ] `docs/ISOLATION_DEPLOYMENT.md` — how to set up a cluster, cert rotation, NFS requirements for shared_workspace

## Out of scope for Layer 1b

- Resource quotas (CPU / memory / fd limits) — Layer 2
- Network egress filtering — Layer 2
- SCM_RIGHTS fd passing for shared-dir zero-copy — optimization for later
- Object-storage-backed shared workspace — future, after NAS proves insufficient
- Multi-region clusters, WAN latency handling — future
