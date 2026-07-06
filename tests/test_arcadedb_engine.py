"""ArcadeDB engine — tested against a REAL embedded ArcadeDB, in-process.

Runs only where ``arcadedb-embedded`` is installed: it boots an in-process
database in a temp folder and drives the full engine, so the actual Cypher is
proven end-to-end — not a mock. (Costs one JVM warm-up per test session.)
"""
import pytest

pytest.importorskip("arcadedb_embedded")

from manifexa.graph.arcadedb_engine import ArcadeDBEngine


@pytest.fixture
def engine(tmp_path):
    e = ArcadeDBEngine.open(str(tmp_path / "g.arcadedb"))
    try:
        yield e
    finally:
        e.close()


def test_add_and_read_nodes(engine):
    engine.add_node("person/ada", type="person", title="Ada", status="curated")
    assert engine.has_node("person/ada")
    assert not engine.has_node("nope")
    assert engine.node("person/ada") == {"key": "person/ada", "type": "person",
                                         "title": "Ada", "status": "curated"}
    assert engine.nodes() == ["person/ada"]


def test_edges_are_undirected(engine):
    engine.add_node("a", type="person", title="A", status="curated")
    engine.add_node("b", type="paper", title="B", status="curated")
    engine.add_edge("a", "b", "authored")
    assert engine.neighbors("a") == ["b"]
    assert engine.neighbors_with_rel("a") == [("b", "authored")]
    assert engine.neighbors_with_rel("b") == [("a", "authored")]   # queried undirected


def test_clear_wipes_everything(engine):
    engine.add_node("x", type="person", title="X", status="curated")
    engine.clear()
    assert engine.nodes() == []


def test_merge_is_idempotent(engine):
    engine.add_node("a", type="person", title="Ada", status="curated")
    engine.add_node("a", type="person", title="Ada Lovelace", status="curated")   # re-add updates
    assert engine.nodes() == ["a"]
    assert engine.node("a")["title"] == "Ada Lovelace"


def test_shortest_path_and_betweenness(engine):
    for k in ("a", "b", "c"):
        engine.add_node(k, type="person", title=k, status="curated")
    engine.add_edge("a", "b", "x")
    engine.add_edge("b", "c", "x")
    assert engine.shortest_path("a", "c") == ["a", "b", "c"]
    assert engine.shortest_path("a", "a") == ["a"]
    assert engine.shortest_path("a", "zzz") is None
    bc = engine.betweenness()
    assert bc["b"] > bc["a"]                                        # the middle node bridges
