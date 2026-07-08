"""LLM-powered graph operations, written once against an injected provider.

* ``expand``   — propose NEW related entities + edges around a focal node (grow).
* ``complete`` — infer LIKELY missing edges among EXISTING nodes (densify).
* ``ask``      — rank existing entities by relevance to a natural-language query.

``expand`` / ``complete`` write **candidates** into the cache tagged
``llm:<provider>`` (never the curated vault). All three take the provider as an
argument, so prompt-building + parsing are unit-tested with a fake.
"""
from __future__ import annotations

import re

from ..store.slug import make_id

_WS = re.compile(r"[^a-z0-9]+")


def _norm(title: str) -> str:
    """A loose title key for de-duplication — case/punctuation/spacing-insensitive."""
    return _WS.sub(" ", (title or "").lower()).strip()

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
_ORGANIZE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "themes": {"type": "array", "items": {"type": "object", "properties": {
            "label": {"type": "string"},
            "keys": {"type": "array", "items": {"type": "string"}}},
            "required": ["label", "keys"], "additionalProperties": False}},
    },
    "required": ["summary", "themes"],
    "additionalProperties": False,
}


def _title(engine, key):
    return (engine.node(key) or {}).get("title") or key


def _write_candidates(cache, result, source, seed=None, existing=None):
    """Write proposed entities/edges as candidates, de-duplicated against nodes
    that already exist (``existing`` maps normalised-title → key). A proposal that
    matches an existing node reuses its key (so edges attach to it) instead of
    minting a twin; only genuinely-new entities are created."""
    key_of = dict(seed or {})
    index = dict(existing or {})                         # normalised title -> key
    written = 0
    for e in result.get("entities", []):
        norm = _norm(e["title"])
        if norm in index:                                # already in the graph → reuse, don't duplicate
            key_of[e["title"]] = index[norm]
            continue
        k = make_id(e["type"], e["title"])
        index[norm] = key_of[e["title"]] = k
        cache.upsert_node(k, e["type"], e["title"], {"source": source}, source=source)
        written += 1
    edges = 0
    for ed in result.get("edges", []):
        s, d = key_of.get(ed.get("source")), key_of.get(ed.get("target"))
        if s and d and s != d:
            cache.upsert_edge(s, d, ed.get("rel", "related"), source=source)
            edges += 1
    return {"entities": written, "edges": edges}


def _existing_index(engine) -> dict:
    """normalised-title → key for every node currently in the graph."""
    idx = {}
    for k in engine.nodes():
        t = _title(engine, k)
        if t:
            idx.setdefault(_norm(t), k)
    return idx


def expand(provider, engine, cache, key) -> dict:
    """Grow the graph around ``key`` along its author / co-authorship network,
    scoped to the paper's field: its authors and their other papers in the same
    field. Verifiable structure (real people + real works), de-duplicated against
    what's already in the graph. Written as candidates tagged ``llm:<provider>``."""
    title = _title(engine, key)
    typ = (engine.node(key) or {}).get("type", "")
    field = ", ".join(
        _title(engine, n) for n, _ in engine.neighbors_with_rel(key)
        if (engine.node(n) or {}).get("type") in ("topic", "concept")) or "its field"
    known = [_title(engine, n) for n, _ in engine.neighbors_with_rel(key)]
    prompt = (
        f"'{title}' is a {typ} in my research knowledge graph (field: {field}). "
        f"Already linked: {', '.join(known) or 'nothing yet'}.\n\n"
        f"Focus ONLY on its author / co-authorship network in the SAME field ({field}):\n"
        f"1. its authors (as person entities);\n"
        f"2. other papers those authors have (co-)authored that belong to this field (as paper entities).\n"
        f"Only real, verifiable people and works — no guesses; omit anything you're unsure of. "
        f"Add edges 'authored' from each author to '{title}' and to each of their papers you list."
    )
    result = provider.generate(prompt, system="You map the author and co-authorship network of a paper, in its field, using only real people and works.", schema=_GRAPH_SCHEMA)
    return _write_candidates(cache, result, f"llm:{provider.name}", seed={title: key}, existing=_existing_index(engine))


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


def organize(provider, engine, keys=None) -> dict:
    """LLM groups the graph's *titled* nodes into labelled themes + a one-line
    summary — a meaningful map instead of a flat edge dump. ``keys`` limits it to
    a neighbourhood; None themes the whole graph. Untitled refs (bare ids with no
    title yet) are bucketed separately, and hallucinated keys are dropped."""
    catalog = [(k, _title(engine, k)) for k in (keys if keys is not None else engine.nodes())]
    titled = [(k, t) for k, t in catalog if t and t != k]
    listing = "\n".join(f"{k} :: {t}" for k, t in titled)
    prompt = (
        f"Entities in a research knowledge graph (key :: title):\n{listing}\n\n"
        f"Group them into a few meaningful themes by subject. Give each theme a short "
        f"label and its list of keys, and a one-sentence summary of the whole set. Use "
        f"only the keys above; put each key in at most one theme."
    )
    result = provider.generate(prompt, system="You organize research entities into clear thematic groups.", schema=_ORGANIZE_SCHEMA)
    valid, seen, themes = {k for k, _ in titled}, set(), []
    for th in result.get("themes", []):
        ks = [k for k in th.get("keys", []) if k in valid and k not in seen]
        seen.update(ks)
        if ks:
            themes.append({"label": (th.get("label") or "misc").strip(), "keys": ks})
    return {
        "summary": (result.get("summary") or "").strip(),
        "themes": themes,
        "other": [k for k, _ in titled if k not in seen],
        "untitled": [k for k, t in catalog if not t or t == k],
    }


def ask(provider, engine, query: str) -> list[str]:
    catalog = "\n".join(f"{n} :: {_title(engine, n)}" for n in engine.nodes())
    prompt = (
        f"Query: {query}\n\nEntities (key :: title):\n{catalog}\n\n"
        f"Return the keys of the entities most relevant to the query, best first."
    )
    result = provider.generate(prompt, system="You select the most relevant knowledge-graph entities for a query.", schema=_SEARCH_SCHEMA)
    valid = set(engine.nodes())
    return [k for k in result.get("keys", []) if k in valid]
