"""
Canvas workflow artifact store.

Per-run shared workspace + automatic artifact tracking. Closes the
"agent A's deliverable can't reach agent B" gap (HANDOFF 2026-05-02).

Storage layout:

  <data_dir>/canvas_runs/<run_id>/
    state.json            # run state (canvas_executor)
    events.jsonl          # event stream (canvas_executor)
    shared/               # ★ per-run shared workspace
      topology.png        # files agents wrote here
      deck.pptx
    artifacts.json        # ★ artifact metadata index
    audit.jsonl           # ★ append-only access log

Design choices:
* Storage backend = local filesystem on the hub host. Multi-host
  workers reach this via the existing SharedFileRouter IPC gate
  (supervisor.py:_gate_shared_write) — no separate replication layer.
* Discovery = engine-driven post-scan (Plan A). After each agent node
  completes, the engine diffs the shared dir against a pre-snapshot
  and registers any new files as artifacts.
* Marking = agent-driven (Plan C). Agents that know about the system
  can call ``mark_artifact(filename, ...)`` to flag a file as an
  official deliverable + add description/tags. Files without a mark
  are still registered (for closed-loop discoverability) but UI
  presents them as "auto-detected" vs "marked deliverable".
* Audit = every register / read / mark / delete appends one JSONL row
  with actor, action, timestamp, file hash, sizes.
"""
from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("tudou.canvas_artifacts")


# ── Filename safety ─────────────────────────────────────────────────────


_VAR_KEY_RE = re.compile(r"[^a-zA-Z0-9_]")


def _sanitize_for_var(name: str) -> str:
    """Turn a filename into a safe variable suffix.

    'topology.png' → 'topology_png'   (used as ``{node_id}.file_topology_png``)
    """
    # Strip any leading dots / slashes; replace anything non-alphanumeric
    base = (name or "").lstrip("./")
    return _VAR_KEY_RE.sub("_", base)


# ── Data model ──────────────────────────────────────────────────────────


@dataclass
class ArtifactMetadata:
    """One registered artifact in a workflow run."""
    id: str = field(default_factory=lambda: f"art-{uuid.uuid4().hex[:12]}")
    run_id: str = ""
    name: str = ""              # human-readable filename ('topology.png')
    rel_path: str = ""          # path relative to <run>/shared/
    size_bytes: int = 0
    sha256: str = ""
    mime: str = ""
    producer_node_id: str = ""  # workflow node that produced it
    producer_agent_id: str = ""
    created_at: float = 0.0
    vars_key: str = ""          # full dotted key in run.vars (e.g. "n_drawio.file_topology_png")
    # Plan C — agent-marked metadata. None = auto-detected;
    # truthy = explicitly marked as deliverable by the producer agent.
    marked: bool = False
    description: str = ""
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "run_id": self.run_id, "name": self.name,
            "rel_path": self.rel_path, "size_bytes": self.size_bytes,
            "sha256": self.sha256, "mime": self.mime,
            "producer_node_id": self.producer_node_id,
            "producer_agent_id": self.producer_agent_id,
            "created_at": self.created_at, "vars_key": self.vars_key,
            "marked": self.marked, "description": self.description,
            "tags": list(self.tags),
        }


# ── Store ───────────────────────────────────────────────────────────────


class ArtifactStore:
    """Per-run artifact index + audit log on top of the shared dir.

    Thread-safe via per-run lock. Lock protects both ``artifacts.json``
    and ``audit.jsonl`` writes; concurrent reads of the index file are
    safe because ``json.load`` is atomic w.r.t. file replacement.
    """

    # File extensions that count as "noise" — temp files, locks, OS
    # crud. Auto-detected files with these extensions are registered
    # but ``marked=False`` (UI hides by default). Agent can still
    # ``mark_artifact()`` one of these explicitly.
    NOISE_EXTENSIONS = frozenset({
        ".tmp", ".temp", ".log", ".lock", ".swp", ".swo", ".bak",
        ".pyc", ".pyo", ".cache", ".DS_Store",
    })

    def __init__(self, runs_root: str | Path):
        self.runs_root = Path(runs_root)
        # Reentrant: ``diff_and_register`` holds the per-run lock while
        # iterating files AND while calling ``record_audit`` — which
        # acquires the same lock for its own append. A plain Lock would
        # deadlock here.
        self._locks: dict[str, threading.RLock] = {}
        self._registry_lock = threading.Lock()

    # ── Path resolution ──

    def shared_dir(self, run_id: str) -> Path:
        d = self.runs_root / run_id / "shared"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @staticmethod
    def _sanitize_node_id(node_id: str) -> str:
        """Defensive — node_ids are server-generated hex, but rejecting
        path separators here makes us robust to ever auto-generating
        from labels in the future."""
        s = (node_id or "").replace("/", "_").replace("\\", "_").replace("..", "_")
        return s or "unknown_node"

    def node_dir(self, run_id: str, node_id: str, *, fresh: bool = False) -> Path:
        """Return ``shared/<node_id>/`` for this run, creating if absent.

        Each agent node owns a private subdirectory under shared/. Write
        isolation: the agent's working_dir is set to this path so its
        produced files can't collide with sibling nodes' files. Read
        isolation is intentionally NOT enforced — sandbox still allows
        the whole shared/ tree, so downstream nodes can reach any
        upstream node's outputs via {{nid.deliverable}}.

        ``fresh=True`` (used on retry per the user's "直接覆盖" choice
        2026-05-02): rmtree the existing dir first, then recreate empty.
        Audit log preserves what was lost.
        """
        nid = self._sanitize_node_id(node_id)
        d = self.shared_dir(run_id) / nid
        if fresh and d.exists():
            import shutil
            shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def write_node_meta(self, run_id: str, node_id: str, meta: dict) -> None:
        """Drop _meta.json into the node's subdir. Captures who-produced-
        what at the filesystem level so a debugger can reconstruct the
        run by walking the tree. Atomic write via tmp+replace."""
        d = self.node_dir(run_id, node_id)
        path = d / "_meta.json"
        tmp = path.with_suffix(".json.tmp")
        try:
            tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                           encoding="utf-8")
            os.replace(tmp, path)
        except OSError as e:
            logger.warning("write_node_meta failed for %s/%s: %s", run_id, node_id, e)

    def _index_path(self, run_id: str) -> Path:
        return self.runs_root / run_id / "artifacts.json"

    def _audit_path(self, run_id: str) -> Path:
        return self.runs_root / run_id / "audit.jsonl"

    def _lock_for(self, run_id: str) -> "threading.RLock":
        with self._registry_lock:
            lk = self._locks.get(run_id)
            if lk is None:
                lk = threading.RLock()
                self._locks[run_id] = lk
            return lk

    # ── Index I/O ──

    def _load_index(self, run_id: str) -> list[ArtifactMetadata]:
        path = self._index_path(run_id)
        if not path.exists():
            return []
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            items = d.get("items") if isinstance(d, dict) else d
            return [
                ArtifactMetadata(
                    id=it.get("id", ""),
                    run_id=it.get("run_id", run_id),
                    name=it.get("name", ""),
                    rel_path=it.get("rel_path", ""),
                    size_bytes=int(it.get("size_bytes", 0) or 0),
                    sha256=it.get("sha256", ""),
                    mime=it.get("mime", ""),
                    producer_node_id=it.get("producer_node_id", ""),
                    producer_agent_id=it.get("producer_agent_id", ""),
                    created_at=float(it.get("created_at", 0) or 0),
                    vars_key=it.get("vars_key", ""),
                    marked=bool(it.get("marked", False)),
                    description=it.get("description", ""),
                    tags=list(it.get("tags") or []),
                )
                for it in (items or [])
                if isinstance(it, dict)
            ]
        except Exception as e:
            logger.warning("artifact index read failed for %s: %s", run_id, e)
            return []

    def _save_index(self, run_id: str, items: list[ArtifactMetadata]) -> None:
        path = self._index_path(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        payload = {
            "version": 1,
            "run_id": run_id,
            "items": [it.to_dict() for it in items],
        }
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        os.replace(tmp, path)

    # ── Audit ──

    def record_audit(self, run_id: str, *,
                     actor_agent_id: str = "",
                     actor_node_id: str = "",
                     action: str = "",
                     artifact_id: str = "",
                     name: str = "",
                     extra: dict | None = None) -> None:
        """Append one audit row. action in {register, mark, read,
        delete, scan_start, scan_end}."""
        row = {
            "ts": time.time(),
            "run_id": run_id,
            "actor_agent_id": actor_agent_id,
            "actor_node_id": actor_node_id,
            "action": action,
            "artifact_id": artifact_id,
            "name": name,
        }
        if extra:
            row.update(extra)
        path = self._audit_path(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock_for(run_id):
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def read_audit(self, run_id: str, since_offset: int = 0
                   ) -> tuple[list[dict], int]:
        path = self._audit_path(run_id)
        if not path.exists():
            return [], 0
        with self._lock_for(run_id):
            with open(path, "rb") as f:
                f.seek(since_offset)
                raw = f.read()
                new_offset = since_offset + len(raw)
        rows = []
        for line in raw.decode("utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows, new_offset

    # ── Scan + register ──

    def snapshot_dir(self, run_id: str, *, subdir: str = "") -> dict[str, float]:
        """Return {rel_path: mtime_ns} for everything in ``shared/<subdir>/``.

        Empty subdir → snapshots the whole shared tree (legacy behavior).
        Pass ``subdir=node_id`` to scope the snapshot to a single node's
        private dir — keeps rel_paths relative to ``shared/`` so the
        ``<node_id>/`` prefix is preserved in artifact rel_path.

        Used as a pre-snapshot before invoking a node; diff against a
        post-snapshot tells the engine which files the node produced.
        """
        d = self.shared_dir(run_id)
        target = (d / subdir) if subdir else d
        snap: dict[str, float] = {}
        if not target.exists():
            return snap
        for root, _dirs, files in os.walk(target):
            for f in files:
                if f == "_meta.json":
                    continue   # not a deliverable; skip from snapshots
                full = Path(root) / f
                try:
                    rel = str(full.relative_to(d))
                    snap[rel] = full.stat().st_mtime_ns
                except OSError:
                    continue
        return snap

    def diff_and_register(self, run_id: str, *,
                          pre_snapshot: dict[str, float],
                          producer_node_id: str,
                          producer_agent_id: str,
                          subdir: str = "",
                          ) -> list[ArtifactMetadata]:
        """Compare current state of ``shared/<subdir>/`` to
        ``pre_snapshot`` and register every NEW or MODIFIED file as an
        artifact.

        Returns the list of newly-registered artifacts (one per file).
        Idempotent: if a file at the same rel_path already exists in
        the index AND its sha256 matches, no new artifact is created.

        ``subdir=""`` walks the whole shared tree (legacy behavior); pass
        ``subdir=node_id`` to limit registration to one node's private
        directory — important now that each node owns a subdir, so
        diffing the whole tree would re-register sibling nodes' files
        on every run.
        """
        d = self.shared_dir(run_id)
        target = (d / subdir) if subdir else d
        new_items: list[ArtifactMetadata] = []
        with self._lock_for(run_id):
            existing = self._load_index(run_id)
            existing_by_rel = {it.rel_path: it for it in existing}

            if not target.exists():
                return new_items
            for root, _dirs, files in os.walk(target):
                for f in files:
                    if f == "_meta.json":
                        continue
                    full = Path(root) / f
                    try:
                        rel = str(full.relative_to(d))
                        st = full.stat()
                    except OSError:
                        continue
                    # Skip if file was already there and unchanged.
                    pre_mtime = pre_snapshot.get(rel)
                    if pre_mtime is not None and pre_mtime == st.st_mtime_ns:
                        continue
                    # Compute hash for dedup against same-rel-path
                    # existing artifact.
                    try:
                        sha = _sha256_of_file(full)
                    except OSError:
                        continue
                    prev = existing_by_rel.get(rel)
                    if prev is not None and prev.sha256 == sha:
                        # No content change — skip without polluting.
                        continue
                    name = Path(rel).name
                    suffix = Path(rel).suffix.lower()
                    mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
                    is_noise = suffix in self.NOISE_EXTENSIONS
                    art = ArtifactMetadata(
                        run_id=run_id,
                        name=name,
                        rel_path=rel,
                        size_bytes=int(st.st_size),
                        sha256=sha,
                        mime=mime,
                        producer_node_id=producer_node_id,
                        producer_agent_id=producer_agent_id,
                        created_at=time.time(),
                        vars_key=f"{producer_node_id}.file_{_sanitize_for_var(rel)}",
                        marked=False,   # auto-detected; agent can mark explicitly later
                        description="" if not is_noise else "(auto-detected, likely temporary)",
                    )
                    existing.append(art)
                    existing_by_rel[rel] = art
                    new_items.append(art)
                    self.record_audit(
                        run_id,
                        actor_agent_id=producer_agent_id,
                        actor_node_id=producer_node_id,
                        action="register",
                        artifact_id=art.id,
                        name=name,
                        extra={"sha256": sha, "size_bytes": art.size_bytes,
                               "mime": mime, "noise": is_noise},
                    )
            if new_items:
                self._save_index(run_id, existing)
        return new_items

    # ── Agent-side mark ──

    def mark_artifact(self, run_id: str, *,
                      name_or_id: str,
                      actor_agent_id: str,
                      actor_node_id: str,
                      description: str = "",
                      tags: list[str] | None = None,
                      ) -> ArtifactMetadata | None:
        """Promote an auto-detected artifact to a "marked deliverable".

        Match by exact id or by name (last-write-wins if multiple files
        share a name — caller should pass id to disambiguate).
        Returns updated metadata or None if not found.
        """
        with self._lock_for(run_id):
            items = self._load_index(run_id)
            target = None
            for it in items:
                if it.id == name_or_id or it.name == name_or_id:
                    target = it
                    break
            if target is None:
                return None
            target.marked = True
            if description:
                target.description = description
            if tags:
                # de-dup, preserve order
                seen = set(target.tags)
                for t in tags:
                    if t not in seen:
                        target.tags.append(t)
                        seen.add(t)
            self._save_index(run_id, items)
            self.record_audit(
                run_id,
                actor_agent_id=actor_agent_id,
                actor_node_id=actor_node_id,
                action="mark",
                artifact_id=target.id,
                name=target.name,
                extra={"description": description, "tags": list(tags or [])},
            )
            return target

    # ── Read API ──

    def list_artifacts(self, run_id: str) -> list[ArtifactMetadata]:
        return self._load_index(run_id)

    def get_artifact(self, run_id: str, artifact_id: str
                     ) -> ArtifactMetadata | None:
        for it in self._load_index(run_id):
            if it.id == artifact_id:
                return it
        return None

    def open_for_read(self, run_id: str, artifact_id: str, *,
                      actor_agent_id: str = "",
                      actor_node_id: str = "") -> tuple[ArtifactMetadata, Path] | None:
        """Resolve to (metadata, absolute_path) and audit the read.
        Caller opens / streams the file."""
        art = self.get_artifact(run_id, artifact_id)
        if art is None:
            return None
        full = self.shared_dir(run_id) / art.rel_path
        if not full.is_file():
            return None
        self.record_audit(
            run_id,
            actor_agent_id=actor_agent_id,
            actor_node_id=actor_node_id,
            action="read",
            artifact_id=art.id,
            name=art.name,
        )
        return art, full

    def delete_artifact(self, run_id: str, artifact_id: str, *,
                        actor_agent_id: str = "",
                        actor_node_id: str = "") -> bool:
        with self._lock_for(run_id):
            items = self._load_index(run_id)
            art = next((it for it in items if it.id == artifact_id), None)
            if art is None:
                return False
            full = self.shared_dir(run_id) / art.rel_path
            try:
                if full.is_file():
                    full.unlink()
            except OSError as e:
                logger.warning("artifact unlink failed for %s: %s",
                               full, e)
            items = [it for it in items if it.id != artifact_id]
            self._save_index(run_id, items)
            self.record_audit(
                run_id,
                actor_agent_id=actor_agent_id,
                actor_node_id=actor_node_id,
                action="delete",
                artifact_id=art.id,
                name=art.name,
            )
            return True


# ── Helpers ─────────────────────────────────────────────────────────────


def _sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(64 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


# ── Module-level singleton (matches canvas_executor pattern) ────────────


_STORE: ArtifactStore | None = None
_STORE_LOCK = threading.Lock()


def init_store(runs_root: str | Path) -> ArtifactStore:
    """Idempotent init. Pass the same runs_root the executor uses."""
    global _STORE
    with _STORE_LOCK:
        if _STORE is None:
            _STORE = ArtifactStore(runs_root)
    return _STORE


def get_store() -> ArtifactStore | None:
    return _STORE
