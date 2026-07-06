"""In-process graph engine backed by NetworkX.

Undirected: discovery cares about how things connect (shared neighbours,
shortest paths, bridges), not edge direction. The relationship label is kept as
an edge attribute for display and reasoning.
"""
from __future__ import annotations

import networkx as nx


class NetworkXEngine:
    def __init__(self) -> None:
        self.g = nx.Graph()

    def add_node(self, key: str, **attrs) -> None:
        self.g.add_node(key, **attrs)

    def add_edge(self, src: str, dst: str, rel: str) -> None:
        self.g.add_edge(src, dst, rel=rel)

    def clear(self) -> None:
        self.g.clear()

    def has_node(self, key: str) -> bool:
        return self.g.has_node(key)

    def node(self, key: str):
        if key not in self.g:
            return None
        return {"key": key, **self.g.nodes[key]}

    def nodes(self) -> list[str]:
        return list(self.g.nodes)

    def neighbors(self, key: str) -> list[str]:
        return list(self.g.neighbors(key)) if key in self.g else []

    def neighbors_with_rel(self, key: str) -> list[tuple[str, str]]:
        if key not in self.g:
            return []
        return [(n, self.g.edges[key, n].get("rel", "")) for n in self.g.neighbors(key)]

    def shortest_path(self, src: str, dst: str):
        try:
            return nx.shortest_path(self.g, src, dst)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    def degree(self, key: str) -> int:
        return self.g.degree(key) if key in self.g else 0

    def betweenness(self) -> dict[str, float]:
        return nx.betweenness_centrality(self.g)
