"""Neo4j graph engine — the persistent backend, same interface as NetworkX.

Nodes are ``(:Entity {key, type, title, status})``; relationships are
``[:LINK {rel}]`` and queried undirected (``-[:LINK]-``), matching the
NetworkX engine's semantics so discovery is identical on either backend.

Betweenness is computed in-process over the fetched edges, so this works on a
stock Neo4j without the GDS plugin (GDS can replace it later for scale).
``clear`` only touches ``:Entity`` nodes, so Manifexa can share an instance.
"""
from __future__ import annotations

import networkx as nx
from neo4j import GraphDatabase


class Neo4jEngine:
    def __init__(self, uri, auth, database: str = "neo4j") -> None:
        self._driver = GraphDatabase.driver(uri, auth=tuple(auth))
        self._database = database
        self._driver.verify_connectivity()

    def _run(self, cypher: str, **params):
        with self._driver.session(database=self._database) as session:
            return list(session.run(cypher, **params))

    # --- writes ---
    def add_node(self, key: str, **attrs) -> None:
        clean = {k: v for k, v in attrs.items() if v is not None}
        self._run("MERGE (n:Entity {key:$key}) SET n += $attrs", key=key, attrs=clean)

    def add_edge(self, src: str, dst: str, rel: str) -> None:
        self._run(
            "MATCH (a:Entity {key:$src}), (b:Entity {key:$dst}) "
            "MERGE (a)-[r:LINK {rel:$rel}]->(b)",
            src=src, dst=dst, rel=rel,
        )

    def clear(self) -> None:
        self._run("MATCH (n:Entity) DETACH DELETE n")

    # --- reads ---
    def has_node(self, key: str) -> bool:
        return self._run("MATCH (n:Entity {key:$key}) RETURN count(n) AS c", key=key)[0]["c"] > 0

    def node(self, key: str):
        rows = self._run("MATCH (n:Entity {key:$key}) RETURN n", key=key)
        return dict(rows[0]["n"]) if rows else None

    def nodes(self) -> list[str]:
        return [r["k"] for r in self._run("MATCH (n:Entity) RETURN n.key AS k")]

    def neighbors(self, key: str) -> list[str]:
        return [r["k"] for r in self._run(
            "MATCH (:Entity {key:$key})-[:LINK]-(m:Entity) RETURN DISTINCT m.key AS k", key=key)]

    def neighbors_with_rel(self, key: str) -> list[tuple[str, str]]:
        return [(r["k"], r["rel"]) for r in self._run(
            "MATCH (:Entity {key:$key})-[r:LINK]-(m:Entity) RETURN m.key AS k, r.rel AS rel", key=key)]

    def shortest_path(self, src: str, dst: str):
        if src == dst:
            return [src] if self.has_node(src) else None
        rows = self._run(
            "MATCH (a:Entity {key:$src}), (b:Entity {key:$dst}) "
            "MATCH p = shortestPath((a)-[:LINK*]-(b)) "
            "RETURN [n IN nodes(p) | n.key] AS keys",
            src=src, dst=dst,
        )
        return rows[0]["keys"] if rows else None

    def betweenness(self) -> dict[str, float]:
        g = nx.Graph()
        for r in self._run("MATCH (n:Entity) RETURN n.key AS k"):
            g.add_node(r["k"])
        for r in self._run("MATCH (a:Entity)-[:LINK]->(b:Entity) RETURN a.key AS a, b.key AS b"):
            g.add_edge(r["a"], r["b"])
        return nx.betweenness_centrality(g)

    def close(self) -> None:
        self._driver.close()
