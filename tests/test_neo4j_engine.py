"""Integration tests for the Neo4j backend.

Run against a live Neo4j (defaults to bolt://localhost:7687). When none is
reachable they skip, so the suite stays green anywhere. The point: discovery
runs *identically* on Neo4j and NetworkX, because both honour GraphEngine.
"""
import os

import pytest

from manifexa.discovery.core import around, find_path
from manifexa.graph.neo4j_engine import Neo4jEngine

URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
AUTH = (os.environ.get("NEO4J_USER", "neo4j"), os.environ.get("NEO4J_PASSWORD", "manifexa-dev"))


@pytest.fixture
def engine():
    try:
        eng = Neo4jEngine(URI, AUTH)
        eng.clear()
    except Exception as exc:  # no server -> skip, don't fail
        pytest.skip(f"Neo4j not available: {exc}")
    yield eng
    eng.clear()
    eng.close()


def test_add_nodes_edges_and_neighbors(engine):
    engine.add_node("a", type="person", title="A", status="curated")
    engine.add_node("b", type="paper", title="B", status="candidate")
    engine.add_edge("a", "b", "authored")
    assert engine.has_node("a")
    assert engine.node("a")["type"] == "person"
    assert set(engine.neighbors("a")) == {"b"}
    assert engine.neighbors_with_rel("a") == [("b", "authored")]


def test_shortest_path(engine):
    for k in "abc":
        engine.add_node(k, type="x", title=k, status="candidate")
    engine.add_edge("a", "b", "x")
    engine.add_edge("b", "c", "y")
    assert engine.shortest_path("a", "c") == ["a", "b", "c"]
    assert engine.shortest_path("a", "z") is None


def test_clear_only_removes_entities(engine):
    engine.add_node("a", type="x", title="A", status="curated")
    engine.clear()
    assert engine.nodes() == []


def test_betweenness_identifies_bridge(engine):
    for k in "abcde":
        engine.add_node(k, type="x", title=k, status="candidate")
    for a, b in [("a", "b"), ("b", "c"), ("c", "d"), ("d", "e")]:
        engine.add_edge(a, b, "x")
    bc = engine.betweenness()
    assert bc["c"] == max(bc.values())


def test_discovery_runs_identically_on_neo4j(engine):
    engine.add_node("S", type="paper", title="Seed", status="curated")
    engine.add_node("A1", type="person", title="Noam", status="candidate")
    engine.add_node("C1", type="paper", title="C1", status="candidate")
    engine.add_node("P2", type="paper", title="P2", status="candidate")
    engine.add_edge("A1", "S", "authored")
    engine.add_edge("C1", "S", "cites")
    engine.add_edge("C1", "P2", "cites")  # P2 co-cited with S via C1

    keys = [r["key"] for r in around(engine, "S")]
    assert "A1" in keys
    assert "P2" in keys
    assert find_path(engine, "S", "P2")[-1]["key"] == "P2"
