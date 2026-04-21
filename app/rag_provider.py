"""
RAG Provider Registry — pluggable vector search backends.

Supports:
  - local:    Built-in ChromaDB (default, zero-config)
  - remote:   HTTP endpoints on other TudouClaw nodes or third-party services
  - custom:   Any provider implementing the RAGProvider protocol

Each provider can host multiple *collections* (knowledge bases).
Agents reference a provider via `rag_provider_id` in their profile.
An empty provider ID means "use local ChromaDB".

Provider config is persisted in ~/.tudou_claw/rag_providers.json.

Remote API contract (POST /api/rag/search):
  Request:  {"query": "...", "collection": "...", "top_k": 5}
  Response: {"results": [{"id": "...", "title": "...", "content": "...",
                           "distance": 0.12, "metadata": {...}}]}

Remote API contract (POST /api/rag/ingest):
  Request:  {"collection": "...", "documents": [{"id": "...", "title": "...",
             "content": "...", "tags": [...]}]}
  Response: {"ok": true, "count": N}
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("tudou.rag")

_DATA_DIR = Path.home() / ".tudou_claw"
_PROVIDERS_FILE = _DATA_DIR / "rag_providers.json"
_DOMAIN_KB_FILE = _DATA_DIR / "domain_knowledge_bases.json"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class RAGResult:
    """Single search result from a RAG provider."""
    id: str = ""
    title: str = ""
    content: str = ""
    distance: float = 0.0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "title": self.title, "content": self.content,
            "distance": self.distance, "metadata": self.metadata,
        }


@dataclass
class RAGCollection:
    """Metadata for a knowledge collection."""
    id: str = ""
    name: str = ""
    description: str = ""
    provider_id: str = ""
    doc_count: int = 0
    created_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "description": self.description,
            "provider_id": self.provider_id, "doc_count": self.doc_count,
            "created_at": self.created_at,
        }


@dataclass
class RAGProviderEntry:
    """Registered RAG provider."""
    id: str = ""
    name: str = ""
    kind: str = "local"     # "local" | "remote" | "custom"
    base_url: str = ""      # For remote providers: http://node:port
    api_key: str = ""       # Optional auth
    enabled: bool = True
    config: dict = field(default_factory=dict)   # Provider-specific settings
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "kind": self.kind,
            "base_url": self.base_url, "api_key": self.api_key,
            "enabled": self.enabled, "config": self.config,
            "created_at": self.created_at,
        }

    @staticmethod
    def from_dict(d: dict) -> RAGProviderEntry:
        return RAGProviderEntry(
            id=d.get("id", ""),
            name=d.get("name", ""),
            kind=d.get("kind", "local"),
            base_url=d.get("base_url", ""),
            api_key=d.get("api_key", ""),
            enabled=d.get("enabled", True),
            config=d.get("config", {}),
            created_at=d.get("created_at", time.time()),
        )


@dataclass
class DomainKnowledgeBase:
    """A standalone domain knowledge base, decoupled from any specific agent.

    Domain KBs persist independently — deleting an agent that uses one does NOT
    remove the KB.  Multiple advisor agents can share the same domain KB.
    """
    id: str = ""
    name: str = ""                     # e.g. "法律知识库", "财务知识库"
    description: str = ""
    collection: str = ""               # RAG collection name (e.g. "domain_law")
    provider_id: str = ""              # empty = local ChromaDB
    tags: list[str] = field(default_factory=list)
    doc_count: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "description": self.description,
            "collection": self.collection, "provider_id": self.provider_id,
            "tags": self.tags, "doc_count": self.doc_count,
            "created_at": self.created_at, "updated_at": self.updated_at,
        }

    @staticmethod
    def from_dict(d: dict) -> DomainKnowledgeBase:
        return DomainKnowledgeBase(
            id=d.get("id", ""),
            name=d.get("name", ""),
            description=d.get("description", ""),
            collection=d.get("collection", ""),
            provider_id=d.get("provider_id", ""),
            tags=d.get("tags", []),
            doc_count=d.get("doc_count", 0),
            created_at=d.get("created_at", time.time()),
            updated_at=d.get("updated_at", time.time()),
        )


class DomainKBStore:
    """Persistent store for standalone domain knowledge bases."""

    def __init__(self, path: Path | str | None = None):
        self._path = Path(path) if path else _DOMAIN_KB_FILE
        self._kbs: dict[str, DomainKnowledgeBase] = {}
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                for d in data.get("knowledge_bases", []):
                    kb = DomainKnowledgeBase.from_dict(d)
                    if kb.id:
                        self._kbs[kb.id] = kb
                logger.info("Loaded %d domain knowledge bases", len(self._kbs))
            except Exception as e:
                logger.warning("Failed to load domain KBs: %s", e)

    def _save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {"knowledge_bases": [kb.to_dict() for kb in self._kbs.values()]}
        self._path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                              encoding="utf-8")

    def list_all(self) -> list[DomainKnowledgeBase]:
        return sorted(self._kbs.values(), key=lambda x: x.created_at, reverse=True)

    def get(self, kb_id: str) -> DomainKnowledgeBase | None:
        return self._kbs.get(kb_id)

    def create(self, name: str, description: str = "", provider_id: str = "",
               tags: list[str] | None = None) -> DomainKnowledgeBase:
        kb_id = f"dkb_{uuid.uuid4().hex[:10]}"
        collection = f"domain_{kb_id}"
        kb = DomainKnowledgeBase(
            id=kb_id, name=name, description=description,
            collection=collection, provider_id=provider_id,
            tags=tags or [],
        )
        self._kbs[kb_id] = kb
        # Create the underlying RAG collection
        try:
            get_rag_registry().create_collection(provider_id, collection)
        except Exception as e:
            logger.warning("Failed to create RAG collection for domain KB %s: %s", kb_id, e)
        self._save()
        return kb

    def update(self, kb_id: str, name: str | None = None,
               description: str | None = None,
               tags: list[str] | None = None) -> DomainKnowledgeBase | None:
        kb = self._kbs.get(kb_id)
        if not kb:
            return None
        if name is not None:
            kb.name = name
        if description is not None:
            kb.description = description
        if tags is not None:
            kb.tags = tags
        kb.updated_at = time.time()
        self._save()
        return kb

    def delete(self, kb_id: str) -> bool:
        kb = self._kbs.pop(kb_id, None)
        if kb is None:
            return False
        # Optionally delete the underlying collection
        try:
            get_rag_registry().delete_collection(kb.provider_id, kb.collection)
        except Exception as e:
            logger.warning("Failed to delete RAG collection for domain KB %s: %s", kb_id, e)
        self._save()
        return True

    def increment_doc_count(self, kb_id: str, delta: int = 1):
        kb = self._kbs.get(kb_id)
        if kb:
            kb.doc_count += delta
            kb.updated_at = time.time()
            self._save()


_domain_kb_store: DomainKBStore | None = None

def get_domain_kb_store() -> DomainKBStore:
    global _domain_kb_store
    if _domain_kb_store is None:
        _domain_kb_store = DomainKBStore()
    return _domain_kb_store


# ---------------------------------------------------------------------------
# Provider Registry (singleton)
# ---------------------------------------------------------------------------

class RAGProviderRegistry:
    """Manages registered RAG providers and routes queries."""

    def __init__(self):
        self._providers: dict[str, RAGProviderEntry] = {}
        self._loaded = False

    # A ghost entry has an id but no distinguishing fields. They are
    # produced when the REST handler persists a ``RAGProviderEntry()``
    # empty constructor (typically from a POST with an empty JSON body
    # or a form-submit that cleared every field). Filter them at both
    # load AND save time so we stop the bleeding AND never re-persist
    # a garbage row read from an older file.
    @staticmethod
    def _is_ghost(p: RAGProviderEntry) -> bool:
        return (not p.name.strip()
                and not p.base_url.strip()
                and p.kind == "remote"
                and not p.config)

    def _ensure_loaded(self):
        if self._loaded:
            return
        self._loaded = True
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        if _PROVIDERS_FILE.exists():
            try:
                with open(_PROVIDERS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                ghosts_skipped = 0
                for d in data:
                    p = RAGProviderEntry.from_dict(d)
                    if not p.id:
                        continue
                    if self._is_ghost(p):
                        ghosts_skipped += 1
                        continue
                    self._providers[p.id] = p
                if ghosts_skipped:
                    logger.warning(
                        "Skipped %d ghost RAG provider entries on load "
                        "(empty name+url+config). Consider running the "
                        "cleanup script.", ghosts_skipped,
                    )
            except Exception as e:
                logger.error("Failed to load RAG providers: %s", e)

    def _save(self):
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with open(_PROVIDERS_FILE, "w", encoding="utf-8") as f:
                json.dump([p.to_dict() for p in self._providers.values()],
                          f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("Failed to save RAG providers: %s", e)

    # ── CRUD ──

    def list_providers(self) -> list[RAGProviderEntry]:
        self._ensure_loaded()
        return list(self._providers.values())

    def get_provider(self, provider_id: str) -> Optional[RAGProviderEntry]:
        self._ensure_loaded()
        return self._providers.get(provider_id)

    def register(self, name: str, kind: str = "remote",
                 base_url: str = "", api_key: str = "",
                 config: dict = None) -> RAGProviderEntry:
        """Register a new RAG provider.

        Rejects ghost registrations (empty name + empty URL on a remote
        provider) — these were the source of the ~59 junk entries that
        accumulated previously. Callers that genuinely want a blank
        local-kind slot must pass kind='local' explicitly.
        """
        self._ensure_loaded()
        # Guard: reject obvious ghosts at the front door.
        if kind == "remote" and not name.strip() and not base_url.strip():
            raise ValueError(
                "RAG provider rejected: kind='remote' requires name or "
                "base_url. Pass kind='local' for a blank local provider."
            )
        entry = RAGProviderEntry(
            id=uuid.uuid4().hex[:10],
            name=name, kind=kind,
            base_url=base_url.rstrip("/") if base_url else "",
            api_key=api_key,
            config=config or {},
        )
        self._providers[entry.id] = entry
        self._save()
        logger.info("RAG provider registered: %s (%s, %s)", name, kind, entry.id)
        return entry

    def update(self, provider_id: str, **kwargs) -> Optional[RAGProviderEntry]:
        """Update provider fields."""
        self._ensure_loaded()
        p = self._providers.get(provider_id)
        if not p:
            return None
        for k, v in kwargs.items():
            if hasattr(p, k):
                setattr(p, k, v)
        self._save()
        return p

    def remove(self, provider_id: str) -> bool:
        self._ensure_loaded()
        if provider_id in self._providers:
            del self._providers[provider_id]
            self._save()
            return True
        return False

    # ── Search routing ──

    def search(self, provider_id: str, collection: str,
               query: str, top_k: int = 5) -> list[RAGResult]:
        """Route a search query to the correct provider backend."""
        self._ensure_loaded()

        if not provider_id or provider_id == "local":
            return self._search_local(collection, query, top_k)

        provider = self._providers.get(provider_id)
        if not provider:
            logger.warning("RAG provider not found: %s, falling back to local", provider_id)
            return self._search_local(collection, query, top_k)

        if not provider.enabled:
            logger.warning("RAG provider disabled: %s", provider_id)
            return []

        if provider.kind == "remote":
            return self._search_remote(provider, collection, query, top_k)
        elif provider.kind == "local":
            return self._search_local(collection, query, top_k)
        else:
            # Custom — extensibility point
            logger.warning("Custom RAG provider not implemented: %s", provider.kind)
            return []

    def ingest(self, provider_id: str, collection: str,
               documents: list[dict]) -> int:
        """Route document ingestion to the correct provider backend.

        Each document: {"id": "...", "title": "...", "content": "...", "tags": [...]}
        Returns: number of documents ingested.
        """
        self._ensure_loaded()

        if not provider_id or provider_id == "local":
            return self._ingest_local(collection, documents)

        provider = self._providers.get(provider_id)
        if not provider or not provider.enabled:
            logger.warning("RAG provider unavailable: %s, falling back to local", provider_id)
            return self._ingest_local(collection, documents)

        if provider.kind == "remote":
            return self._ingest_remote(provider, collection, documents)
        elif provider.kind == "local":
            return self._ingest_local(collection, documents)
        else:
            return 0

    # ── Collection management ──

    def create_collection(self, provider_id: str, collection_name: str,
                          description: str = "") -> RAGCollection:
        """Create a new collection on the specified provider."""
        if not provider_id or provider_id == "local":
            return self._create_local_collection(collection_name, description)
        provider = self._providers.get(provider_id)
        if provider and provider.kind == "remote":
            return self._create_remote_collection(provider, collection_name, description)
        return self._create_local_collection(collection_name, description)

    def list_collections(self, provider_id: str = "") -> list[RAGCollection]:
        """List collections on a provider."""
        if not provider_id or provider_id == "local":
            return self._list_local_collections()
        provider = self._providers.get(provider_id)
        if provider and provider.kind == "remote":
            return self._list_remote_collections(provider)
        return self._list_local_collections()

    def delete_collection(self, provider_id: str, collection_name: str) -> bool:
        if not provider_id or provider_id == "local":
            return self._delete_local_collection(collection_name)
        provider = self._providers.get(provider_id)
        if provider and provider.kind == "remote":
            return self._delete_remote_collection(provider, collection_name)
        return False

    # ── Local ChromaDB backend ──

    def _get_memory_manager(self):
        try:
            from .core.memory import get_memory_manager
            return get_memory_manager()
        except Exception:
            return None

    def _search_local(self, collection: str, query: str,
                      top_k: int = 5) -> list[RAGResult]:
        mm = self._get_memory_manager()
        if not mm:
            return []
        try:
            coll = mm._get_chroma_collection(collection)
            if coll.count() == 0:
                return []
            results = coll.query(query_texts=[query], n_results=min(top_k, 20))
            items = []
            if results and results.get("ids") and results["ids"][0]:
                for i, doc_id in enumerate(results["ids"][0]):
                    meta = results["metadatas"][0][i] if results.get("metadatas") else {}
                    doc = results["documents"][0][i] if results.get("documents") else ""
                    items.append(RAGResult(
                        id=doc_id,
                        title=meta.get("title", ""),
                        content=doc,
                        distance=results["distances"][0][i] if results.get("distances") else 0,
                        metadata=meta,
                    ))
            return items
        except Exception as e:
            logger.warning("Local RAG search failed (collection=%s): %s", collection, e)
            return []

    def _ingest_local(self, collection: str, documents: list[dict]) -> int:
        mm = self._get_memory_manager()
        if not mm:
            return 0
        count = 0
        try:
            coll = mm._get_chroma_collection(collection)
            for doc in documents:
                doc_id = doc.get("id") or uuid.uuid4().hex[:10]
                title = (doc.get("title") or "").strip()
                content = (doc.get("content") or "").strip()
                if not content:
                    continue
                text = f"{title}. {title}. {content}" if title else content
                metadata = {
                    "title": title,
                    "tags": ",".join(doc.get("tags", [])),
                    "source": doc.get("source", "import"),
                    "created_at": time.time(),
                }
                coll.upsert(ids=[doc_id], documents=[text], metadatas=[metadata])
                count += 1
        except Exception as e:
            logger.warning("Local RAG ingest failed (collection=%s): %s", collection, e)
        return count

    def _create_local_collection(self, name: str, description: str = "") -> RAGCollection:
        mm = self._get_memory_manager()
        if mm:
            try:
                mm._get_chroma_collection(name)  # creates if not exist
            except Exception as e:
                logger.warning("Create local collection failed: %s", e)
        return RAGCollection(id=name, name=name, description=description,
                             provider_id="local", created_at=time.time())

    def _list_local_collections(self) -> list[RAGCollection]:
        mm = self._get_memory_manager()
        if not mm:
            return []
        try:
            client = mm._get_chromadb_client()
            colls = client.list_collections()
            result = []
            for c in colls:
                name = c.name if hasattr(c, 'name') else str(c)
                result.append(RAGCollection(
                    id=name, name=name, provider_id="local",
                    doc_count=0,  # would need count() call per collection
                ))
            return result
        except Exception:
            return []

    def _delete_local_collection(self, name: str) -> bool:
        mm = self._get_memory_manager()
        if not mm:
            return False
        try:
            client = mm._get_chromadb_client()
            client.delete_collection(name)
            return True
        except Exception as e:
            logger.warning("Delete local collection failed: %s", e)
            return False

    # ── Remote HTTP backend ──

    def _remote_headers(self, provider: RAGProviderEntry) -> dict:
        headers = {"Content-Type": "application/json"}
        if provider.api_key:
            headers["Authorization"] = f"Bearer {provider.api_key}"
        # Support TudouClaw node secret
        secret = provider.config.get("node_secret")
        if secret:
            headers["X-Claw-Secret"] = secret
        return headers

    def _search_remote(self, provider: RAGProviderEntry, collection: str,
                       query: str, top_k: int = 5) -> list[RAGResult]:
        import requests
        url = f"{provider.base_url}/api/rag/search"
        try:
            resp = requests.post(url, json={
                "query": query, "collection": collection, "top_k": top_k,
            }, headers=self._remote_headers(provider), timeout=15)
            if resp.status_code != 200:
                logger.warning("Remote RAG search failed (%s): %d %s",
                               provider.name, resp.status_code, resp.text[:200])
                return []
            data = resp.json()
            return [
                RAGResult(
                    id=r.get("id", ""),
                    title=r.get("title", ""),
                    content=r.get("content", ""),
                    distance=r.get("distance", 0.0),
                    metadata=r.get("metadata", {}),
                )
                for r in data.get("results", [])
            ]
        except Exception as e:
            logger.warning("Remote RAG search error (%s): %s", provider.name, e)
            return []

    def _ingest_remote(self, provider: RAGProviderEntry, collection: str,
                       documents: list[dict]) -> int:
        import requests
        url = f"{provider.base_url}/api/rag/ingest"
        try:
            resp = requests.post(url, json={
                "collection": collection, "documents": documents,
            }, headers=self._remote_headers(provider), timeout=30)
            if resp.status_code != 200:
                logger.warning("Remote RAG ingest failed (%s): %d",
                               provider.name, resp.status_code)
                return 0
            return resp.json().get("count", 0)
        except Exception as e:
            logger.warning("Remote RAG ingest error (%s): %s", provider.name, e)
            return 0

    def _create_remote_collection(self, provider: RAGProviderEntry,
                                  name: str, description: str = "") -> RAGCollection:
        import requests
        url = f"{provider.base_url}/api/rag/collection/create"
        try:
            resp = requests.post(url, json={
                "name": name, "description": description,
            }, headers=self._remote_headers(provider), timeout=10)
            if resp.status_code == 200:
                return RAGCollection(id=name, name=name, description=description,
                                     provider_id=provider.id, created_at=time.time())
        except Exception as e:
            logger.warning("Remote create collection failed: %s", e)
        return RAGCollection(id=name, name=name, provider_id=provider.id)

    def _list_remote_collections(self, provider: RAGProviderEntry) -> list[RAGCollection]:
        import requests
        url = f"{provider.base_url}/api/rag/collections"
        try:
            resp = requests.get(url, headers=self._remote_headers(provider), timeout=10)
            if resp.status_code == 200:
                return [
                    RAGCollection(id=c.get("id", ""), name=c.get("name", ""),
                                  provider_id=provider.id,
                                  doc_count=c.get("doc_count", 0))
                    for c in resp.json().get("collections", [])
                ]
        except Exception:
            pass
        return []

    def _delete_remote_collection(self, provider: RAGProviderEntry,
                                  name: str) -> bool:
        import requests
        url = f"{provider.base_url}/api/rag/collection/delete"
        try:
            resp = requests.post(url, json={"name": name},
                                 headers=self._remote_headers(provider), timeout=10)
            return resp.status_code == 200
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_registry: RAGProviderRegistry | None = None


def get_rag_registry() -> RAGProviderRegistry:
    global _registry
    if _registry is None:
        _registry = RAGProviderRegistry()
    return _registry


# ---------------------------------------------------------------------------
# High-level search for agents (routes by agent profile)
# ---------------------------------------------------------------------------

def search_for_agent(agent_profile, query: str, agent_id: str = "",
                     top_k: int = 5) -> list[dict]:
    """Search RAG knowledge base(s) according to agent's rag_mode.

    Args:
        agent_profile: AgentProfile instance (has rag_mode, rag_provider_id, etc.)
        query: Search query
        agent_id: Agent ID (for private collection naming)
        top_k: Max results

    Returns:
        List of result dicts [{id, title, content, distance, metadata}]
    """
    reg = get_rag_registry()
    rag_mode = getattr(agent_profile, "rag_mode", "shared")
    provider_id = getattr(agent_profile, "rag_provider_id", "") or ""
    extra_collections = getattr(agent_profile, "rag_collection_ids", []) or []

    results: list[RAGResult] = []

    if rag_mode == "none":
        return []

    if rag_mode in ("private", "both"):
        # Search domain knowledge bases bound to this agent via rag_collection_ids
        dkb_store = get_domain_kb_store()
        for kb_id in extra_collections:
            kb = dkb_store.get(kb_id)
            if kb:
                # Use the domain KB's own collection and provider
                kb_provider = kb.provider_id or provider_id
                results.extend(reg.search(kb_provider, kb.collection, query, top_k))
            else:
                # Fallback: treat as raw collection name (backward compat)
                results.extend(reg.search(provider_id, kb_id, query, top_k))
        # Legacy: also check advisor_{agent_id} collection if it exists
        if agent_id:
            try:
                legacy_results = reg.search(provider_id, f"advisor_{agent_id}", query, top_k)
                results.extend(legacy_results)
            except Exception:
                pass

    if rag_mode in ("shared", "both"):
        # Search the global shared knowledge collection
        shared_results = reg.search(provider_id, "knowledge", query, top_k)
        results.extend(shared_results)

    # Deduplicate by ID and sort by distance
    seen = set()
    unique = []
    for r in results:
        if r.id not in seen:
            seen.add(r.id)
            unique.append(r)
    unique.sort(key=lambda r: r.distance)

    return [r.to_dict() for r in unique[:top_k]]
