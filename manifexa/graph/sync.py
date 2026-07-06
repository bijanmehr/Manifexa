"""Sync — build the derived graph from the vault (truth) + cache (candidates).

Reconciliation: a curated entity may carry an ``openalex`` id, and cached edges
reference that same id. We alias the OpenAlex id to the curated entity's id so
candidate edges attach to the curated node instead of creating a duplicate.

Existence is tracked in a local ``known`` set rather than querying the engine
per item — so loading into a remote engine (Neo4j) stays to writes only.

Idempotent: reads files + cache and produces a fresh graph, so the engine never
needs backing up — rebuild it any time.
"""
from __future__ import annotations


def build_graph(vault, cache, engine):
    alias: dict[str, str] = {}
    known: set[str] = set()

    # 1. Curated entities are the source of truth; remember their openalex alias.
    for entity in vault.list():
        oa = entity.meta.get("openalex")
        if oa:
            alias[oa] = entity.id
        engine.add_node(entity.id, type=entity.type, title=entity.title, status="curated")
        known.add(entity.id)

    # 2. Candidate nodes from the cache (skip any that resolve to a curated id).
    for n in cache.nodes():
        key = alias.get(n["key"], n["key"])
        if key not in known:
            engine.add_node(key, type=n["type"], title=n["title"], status="candidate")
            known.add(key)

    # 3. Edges, with endpoints remapped through the alias.
    for ed in cache.edges():
        src = alias.get(ed["src"], ed["src"])
        dst = alias.get(ed["dst"], ed["dst"])
        if src in known and dst in known:
            engine.add_edge(src, dst, ed["rel"])

    return engine
