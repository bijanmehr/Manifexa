"""One-file snapshot of the whole database — vault + cache in a single JSON.

``dump()`` captures everything needed to reconstruct the graph offline: curated
entities with their full content, candidate nodes, edges, and embeddings.
``load()`` writes it back into a vault + cache, exactly. Plain JSON, so it's
LLM-readable and human-checkable — a real backup / share format, not a dead dump.
"""
from __future__ import annotations

from .entity import Entity

FORMAT = 1


def dump(vault, cache) -> dict:
    """The entire store as one JSON-serialisable dict."""
    entities = [{"id": e.id, "meta": e.meta, "body": e.body} for e in vault.list()]
    cache_nodes = cache.nodes()
    cache_edges = cache.edges()
    return {
        "manifexa": FORMAT,
        "counts": {
            "entities": len(entities),
            "cache_nodes": len(cache_nodes),
            "cache_edges": len(cache_edges),
        },
        "entities": entities,
        "cache_nodes": cache_nodes,
        "cache_edges": cache_edges,
        "embeddings": cache.embeddings(),
    }


def load(vault, cache, data) -> dict:
    """Restore a snapshot into ``vault`` + ``cache`` (merge/overwrite by id)."""
    if not isinstance(data, dict) or "entities" not in data:
        raise ValueError("not a manifexa snapshot")
    for e in data.get("entities", []):
        vault.write(Entity(id=e["id"], meta=e.get("meta", {}), body=e.get("body", "")))
    for n in data.get("cache_nodes", []):
        cache.upsert_node(n["key"], n.get("type"), n.get("title"),
                          n.get("meta") or {}, n.get("source", "import"))
    for ed in data.get("cache_edges", []):
        cache.upsert_edge(ed["src"], ed["dst"], ed["rel"], ed.get("source", "import"))
    for key, vec in (data.get("embeddings") or {}).items():
        cache.set_embedding(key, vec)
    return {
        "entities": len(data.get("entities", [])),
        "cache_nodes": len(data.get("cache_nodes", [])),
        "cache_edges": len(data.get("cache_edges", [])),
    }
