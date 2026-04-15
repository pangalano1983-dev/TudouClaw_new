"""
TudouClaw ChromaDB MCP Server — Vector semantic search via ChromaDB + Sentence Transformers.

Runs as a stdio-based MCP server (JSON-RPC 2.0 over stdin/stdout).
Provides vector_search, vector_store, vector_delete, collection_list, collection_stats tools.

Usage:
    python -m app.tudou_chromadb_mcp

Environment variables:
    CHROMA_PERSIST_DIR       — ChromaDB persistence directory (default: ~/.tudou_claw/chromadb)
    CHROMA_EMBEDDING_MODEL   — Sentence-transformer model name (default: all-MiniLM-L6-v2)
    CHROMA_COLLECTION_PREFIX — Collection name prefix (default: tudou_)
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

from ...defaults import DEFAULT_EMBEDDING_MODEL

logger = logging.getLogger("tudou.chromadb_mcp")

# ---------------------------------------------------------------------------
# ChromaDB wrapper with lazy initialization
# ---------------------------------------------------------------------------

_chroma_client = None
_embed_fn = None


def _get_persist_dir() -> str:
    return os.environ.get("CHROMA_PERSIST_DIR",
                          str(Path.home() / ".tudou_claw" / "chromadb"))


def _get_model_name() -> str:
    return os.environ.get("CHROMA_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)


def _get_prefix() -> str:
    return os.environ.get("CHROMA_COLLECTION_PREFIX", "tudou_")


def _init_chroma():
    """Lazily initialize ChromaDB client and embedding function."""
    global _chroma_client, _embed_fn
    if _chroma_client is not None:
        return

    import chromadb
    from chromadb.utils import embedding_functions

    persist_dir = _get_persist_dir()
    os.makedirs(persist_dir, exist_ok=True)

    _chroma_client = chromadb.PersistentClient(path=persist_dir)

    model_name = _get_model_name()
    _embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=model_name
    )
    logger.info(f"ChromaDB initialized: persist={persist_dir}, model={model_name}")


def _get_collection(name: str):
    """Get or create a ChromaDB collection with the embedding function."""
    _init_chroma()
    full_name = _get_prefix() + name
    return _chroma_client.get_or_create_collection(
        name=full_name,
        embedding_function=_embed_fn,
        metadata={"hnsw:space": "cosine"},
    )


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def tool_vector_store(collection: str, documents: list[dict]) -> dict:
    """Store documents with vector embeddings.

    Args:
        collection: Collection name (without prefix)
        documents: List of {id, content, metadata?} dicts
    Returns:
        {stored: int, collection: str}
    """
    coll = _get_collection(collection)
    ids = []
    contents = []
    metadatas = []
    for doc in documents:
        doc_id = doc.get("id", f"doc_{int(time.time()*1000)}_{len(ids)}")
        ids.append(str(doc_id))
        contents.append(doc["content"])
        meta = doc.get("metadata", {})
        # ChromaDB metadata values must be str, int, float, or bool
        clean_meta = {}
        for k, v in meta.items():
            if isinstance(v, (str, int, float, bool)):
                clean_meta[k] = v
            else:
                clean_meta[k] = str(v)
        metadatas.append(clean_meta)

    coll.upsert(ids=ids, documents=contents, metadatas=metadatas)
    return {"stored": len(ids), "collection": collection}


def tool_vector_search(collection: str, query: str, top_k: int = 5,
                       where: dict | None = None) -> dict:
    """Semantic search using vector embeddings.

    Args:
        collection: Collection name (without prefix)
        query: Natural language search query
        top_k: Number of results to return
        where: Optional ChromaDB where filter (e.g. {"agent_id": "xxx"})
    Returns:
        {results: [{id, content, metadata, distance}], total: int}
    """
    coll = _get_collection(collection)
    kwargs: dict[str, Any] = {
        "query_texts": [query],
        "n_results": min(top_k, 50),
    }
    if where:
        kwargs["where"] = where

    try:
        results = coll.query(**kwargs)
    except Exception as e:
        # Collection might be empty
        if "no documents" in str(e).lower() or "empty" in str(e).lower():
            return {"results": [], "total": 0}
        raise

    items = []
    if results and results.get("ids") and results["ids"][0]:
        for i, doc_id in enumerate(results["ids"][0]):
            item = {
                "id": doc_id,
                "content": results["documents"][0][i] if results.get("documents") else "",
                "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
                "distance": results["distances"][0][i] if results.get("distances") else 0,
            }
            items.append(item)
    return {"results": items, "total": len(items)}


def tool_vector_delete(collection: str, ids: list[str]) -> dict:
    """Delete documents from collection by ID.

    Args:
        collection: Collection name
        ids: List of document IDs to delete
    Returns:
        {deleted: int}
    """
    coll = _get_collection(collection)
    coll.delete(ids=ids)
    return {"deleted": len(ids)}


def tool_collection_list() -> dict:
    """List all collections.

    Returns:
        {collections: [{name, count}]}
    """
    _init_chroma()
    prefix = _get_prefix()
    collections = _chroma_client.list_collections()
    result = []
    for c in collections:
        name = c.name
        display_name = name[len(prefix):] if name.startswith(prefix) else name
        result.append({
            "name": display_name,
            "full_name": name,
            "count": c.count(),
        })
    return {"collections": result}


def tool_collection_stats(collection: str) -> dict:
    """Get statistics for a collection.

    Args:
        collection: Collection name
    Returns:
        {name, count, metadata}
    """
    coll = _get_collection(collection)
    return {
        "name": collection,
        "count": coll.count(),
        "metadata": coll.metadata or {},
    }


# ---------------------------------------------------------------------------
# MCP JSON-RPC server (stdio)
# ---------------------------------------------------------------------------

TOOLS_SCHEMA = [
    {
        "name": "vector_search",
        "description": "语义向量搜索。输入自然语言 query，返回语义相关的文档。"
                       "Semantic vector search. Returns documents semantically similar to the query.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "collection": {
                    "type": "string",
                    "description": "Collection name (e.g. 'memory_facts', 'memory_episodes')"
                },
                "query": {
                    "type": "string",
                    "description": "Natural language search query"
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results (default 5)",
                    "default": 5,
                },
                "where": {
                    "type": "object",
                    "description": "Optional metadata filter (e.g. {\"agent_id\": \"xxx\"})",
                },
            },
            "required": ["collection", "query"],
        },
    },
    {
        "name": "vector_store",
        "description": "存储文档到向量数据库。Store documents with vector embeddings for later semantic search.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "collection": {
                    "type": "string",
                    "description": "Collection name"
                },
                "documents": {
                    "type": "array",
                    "description": "List of documents: [{id, content, metadata?}]",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "content": {"type": "string"},
                            "metadata": {"type": "object"},
                        },
                        "required": ["content"],
                    },
                },
            },
            "required": ["collection", "documents"],
        },
    },
    {
        "name": "vector_delete",
        "description": "从向量数据库删除文档。Delete documents from vector DB by IDs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "collection": {"type": "string"},
                "ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of document IDs to delete"
                },
            },
            "required": ["collection", "ids"],
        },
    },
    {
        "name": "collection_list",
        "description": "列出所有向量集合。List all vector collections and their document counts.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "collection_stats",
        "description": "获取向量集合统计。Get stats (count, metadata) for a collection.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "collection": {"type": "string", "description": "Collection name"},
            },
            "required": ["collection"],
        },
    },
]

SERVER_INFO = {
    "name": "tudou-chromadb",
    "version": "1.0.0",
    "description": "TudouClaw ChromaDB Vector Search MCP Server",
}


def _handle_request(req: dict) -> dict:
    """Handle a single JSON-RPC 2.0 request."""
    method = req.get("method", "")
    params = req.get("params", {})
    req_id = req.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            },
        }

    elif method == "notifications/initialized":
        # No response needed for notifications
        return None

    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": TOOLS_SCHEMA},
        }

    elif method == "tools/call":
        tool_name = params.get("name", "")
        args = params.get("arguments", {})
        try:
            if tool_name == "vector_search":
                result = tool_vector_search(
                    collection=args["collection"],
                    query=args["query"],
                    top_k=args.get("top_k", 5),
                    where=args.get("where"),
                )
            elif tool_name == "vector_store":
                result = tool_vector_store(
                    collection=args["collection"],
                    documents=args["documents"],
                )
            elif tool_name == "vector_delete":
                result = tool_vector_delete(
                    collection=args["collection"],
                    ids=args["ids"],
                )
            elif tool_name == "collection_list":
                result = tool_collection_list()
            elif tool_name == "collection_stats":
                result = tool_collection_stats(
                    collection=args["collection"],
                )
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
                }

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                },
            }
        except Exception as e:
            logger.exception(f"Tool {tool_name} failed")
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps({"error": str(e)})}],
                    "isError": True,
                },
            }

    elif method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    else:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Unknown method: {method}"},
        }


def main():
    """Run MCP server on stdin/stdout."""
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)-5s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,  # Log to stderr, keep stdout clean for JSON-RPC
    )
    logger.info("TudouClaw ChromaDB MCP Server starting...")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            resp = {"jsonrpc": "2.0", "id": None,
                    "error": {"code": -32700, "message": "Parse error"}}
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
            continue

        resp = _handle_request(req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
