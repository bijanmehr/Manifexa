"""Discovery — pulled, on demand, over the derived graph.

* ``around(key)`` surfaces *candidate* nodes near a focal entity, each with a
  reason (a direct link, or a shared-neighbour signal like co-citation).
* ``find_path(a, b)`` returns the labelled hop-by-hop chain connecting two nodes.
* ``bridges()`` ranks nodes by betweenness — the people/works that connect
  otherwise-separate parts of your graph.

These run against the GraphEngine interface, so they're identical whether the
backend is NetworkX (now) or Neo4j (later).
"""
from __future__ import annotations

import networkx as nx

_REL_PHRASE = {
    "authored": "authorship link",
    "cites": "citation link",
    "affiliated_with": "shared affiliation",
    "member_of": "membership link",
    "coauthored": "co-authored a paper",
    "same_group": "same research group",
}


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("s" if n != 1 else "")


def _shared_reason(engine, shared) -> str:
    types = [engine.node(s).get("type") for s in shared if engine.node(s)]
    n = len(shared)
    if types and all(t == "paper" for t in types):
        return "co-cited via " + _plural(n, "paper")
    if types and all(t == "person" for t in types):
        return "shares " + _plural(n, "co-author")
    return "shares " + _plural(n, "connection")


def around(engine, key: str, limit: int = 10) -> list[dict]:
    if not engine.has_node(key):
        return []
    focal_nbrs = set(engine.neighbors(key))
    rel_to = dict(engine.neighbors_with_rel(key))

    results: list[dict] = []
    for c in engine.nodes():
        if c == key:
            continue
        node = engine.node(c)
        if not node or node.get("status") != "candidate":
            continue
        direct = c in focal_nbrs
        shared = focal_nbrs & set(engine.neighbors(c))
        if not direct and not shared:
            continue
        score = (2 if direct else 0) + len(shared)
        reason = _REL_PHRASE.get(rel_to.get(c), "directly connected") if direct else _shared_reason(engine, shared)
        results.append({
            "key": c,
            "type": node.get("type"),
            "title": node.get("title"),
            "score": score,
            "reason": reason,
        })

    results.sort(key=lambda r: (-r["score"], r["title"] or r["key"]))
    return results[:limit]


def find_path(engine, a: str, b: str):
    nodes = engine.shortest_path(a, b)
    if not nodes:
        return None
    chain = []
    for i, k in enumerate(nodes):
        node = engine.node(k) or {}
        rel_to_next = None
        if i < len(nodes) - 1:
            rel_to_next = dict(engine.neighbors_with_rel(k)).get(nodes[i + 1])
        chain.append({
            "key": k,
            "type": node.get("type"),
            "title": node.get("title"),
            "rel_to_next": rel_to_next,
        })
    return chain


def bridges(engine, limit: int = 5) -> list[dict]:
    ranked = sorted(engine.betweenness().items(), key=lambda kv: -kv[1])
    out = []
    for key, score in ranked[:limit]:
        if score <= 0:
            continue
        node = engine.node(key) or {}
        out.append({"key": key, "type": node.get("type"), "title": node.get("title"), "score": score})
    return out


def _nx_from_engine(engine):
    """Reconstruct a NetworkX graph from any GraphEngine (for whole-graph algos)."""
    g = nx.Graph()
    for key in engine.nodes():
        g.add_node(key)
    for key in engine.nodes():
        for nbr, _rel in engine.neighbors_with_rel(key):
            g.add_edge(key, nbr)
    return g


def clusters(engine, min_size: int = 2) -> list[dict]:
    """Emerging clusters — communities of densely-connected nodes (Louvain)."""
    g = _nx_from_engine(engine)
    if g.number_of_nodes() == 0:
        return []
    out = []
    for community in nx.community.louvain_communities(g, seed=42):
        if len(community) >= min_size:
            members = sorted(community)
            out.append({"members": members, "size": len(members)})
    out.sort(key=lambda c: -c["size"])
    return out
