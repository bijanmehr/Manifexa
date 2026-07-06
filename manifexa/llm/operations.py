"""LLM-powered graph operations, written once against an injected provider.

* ``expand``   — propose NEW related entities + edges around a focal node (grow).
* ``complete`` — infer LIKELY missing edges among EXISTING nodes (densify).
* ``ask``      — rank existing entities by relevance to a natural-language query.

``expand`` / ``complete`` write **candidates** into the cache tagged
``llm:<provider>`` (never the curated vault). All three take the provider as an
argument, so prompt-building + parsing are unit-tested with a fake.
"""
from __future__ import annotations

from ..store.slug import make_id

# entities + edges — same shape as the extract schema, so candidates flow through the vault as usual
_GRAPH_SCHEMA = {
    "type": "object",
    "properties": {
        "entities": {"type": "array", "items": {"type": "object", "properties": {
            "type": {"type": "string", "enum": ["person", "paper", "lab", "book", "note", "concept", "topic"]},
            "title": {"type": "string"}}, "required": ["type", "title"], "additionalProperties": False}},
        "edges": {"type": "array", "items": {"type": "object", "properties": {
            "source": {"type": "string"}, "target": {"type": "string"}, "rel": {"type": "string"}},
            "required": ["source", "target", "rel"], "additionalProperties": False}},
    },
    "required": ["entities", "edges"],
    "additionalProperties": False,
}
_SEARCH_SCHEMA = {
    "type": "object",
    "properties": {"keys": {"type": "array", "items": {"type": "string"}}},
    "required": ["keys"],
    "additionalProperties": False,
}


def _title(engine, key):
    return (engine.node(key) or {}).get("title") or key


def _write_candidates(cache, result, source, seed=None):
    key_of = dict(seed or {})
    written = 0
    for e in result.get("entities", []):
        k = make_id(e["type"], e["title"])
        key_of[e["title"]] = k
        cache.upsert_node(k, e["type"], e["title"], {"source": source}, source=source)
        written += 1
    edges = 0
    for ed in result.get("edges", []):
        s, d = key_of.get(ed.get("source")), key_of.get(ed.get("target"))
        if s and d and s != d:
            cache.upsert_edge(s, d, ed.get("rel", "related"), source=source)
            edges += 1
    return {"entities": written, "edges": edges}


def expand(provider, engine, cache, key) -> dict:
    title = _title(engine, key)
    typ = (engine.node(key) or {}).get("type", "")
    nbrs = [_title(engine, n) for n, _ in engine.neighbors_with_rel(key)]
    prompt = (
        f"'{title}' ({typ}) is a node in my research knowledge graph. It already "
        f"links to: {', '.join(nbrs) or 'nothing yet'}.\n\n"
        f"Propose NEW, real, closely-related entities (people, papers, labs, books, "
        f"concepts) and the edges connecting them to '{title}' or to each other. Only "
        f"well-established, verifiable items — no guesses. Every edge source/target "
        f"must exactly match an entity title (you may use '{title}')."
    )
    result = provider.generate(prompt, system="You expand research knowledge graphs with real, verifiable entities.", schema=_GRAPH_SCHEMA)
    return _write_candidates(cache, result, f"llm:{provider.name}", seed={title: key})


def complete(provider, engine, cache, key) -> dict:
    title = _title(engine, key)
    nbrs = {_title(engine, n) for n, _ in engine.neighbors_with_rel(key)}
    by_title = {_title(engine, n): n for n in engine.nodes()}
    others = [t for t in by_title if t != title and t not in nbrs][:80]
    prompt = (
        f"In my knowledge graph, '{title}' already links to: {', '.join(nbrs) or 'nothing'}.\n\n"
        f"Other entities that already exist: {', '.join(others) or 'none'}.\n\n"
        f"Infer LIKELY missing relationships between '{title}' and these existing entities, "
        f"or among them. Only plausible, well-grounded links. Use the existing titles exactly; "
        f"do not invent new entities."
    )
    result = provider.generate(prompt, system="You infer missing edges between existing knowledge-graph entities.", schema=_GRAPH_SCHEMA)
    source = f"llm:{provider.name}"
    edges = 0
    for ed in result.get("edges", []):
        s, d = by_title.get(ed.get("source")), by_title.get(ed.get("target"))
        if s and d and s != d:
            cache.upsert_edge(s, d, ed.get("rel", "related"), source=source)
            edges += 1
    return {"edges": edges}


def ask(provider, engine, query: str) -> list[str]:
    catalog = "\n".join(f"{n} :: {_title(engine, n)}" for n in engine.nodes())
    prompt = (
        f"Query: {query}\n\nEntities (key :: title):\n{catalog}\n\n"
        f"Return the keys of the entities most relevant to the query, best first."
    )
    result = provider.generate(prompt, system="You select the most relevant knowledge-graph entities for a query.", schema=_SEARCH_SCHEMA)
    valid = set(engine.nodes())
    return [k for k in result.get("keys", []) if k in valid]
