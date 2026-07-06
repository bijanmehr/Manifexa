from manifexa.discovery.core import around, find_path, bridges, clusters
from manifexa.graph.networkx_engine import NetworkXEngine


def _candidate(g, key, type="paper"):
    g.add_node(key, type=type, title=key, status="candidate")


# ---------- around ----------

def test_around_surfaces_direct_and_co_cited_candidates():
    g = NetworkXEngine()
    g.add_node("S", type="paper", title="Seed", status="curated")
    _candidate(g, "A1", "person")
    _candidate(g, "A2", "person")
    _candidate(g, "C1", "paper")
    _candidate(g, "P2", "paper")
    g.add_edge("A1", "S", "authored")
    g.add_edge("A2", "S", "authored")
    g.add_edge("C1", "S", "cites")
    g.add_edge("C1", "P2", "cites")  # C1 cites both S and P2 -> P2 co-cited with S

    res = around(g, "S")
    keys = [r["key"] for r in res]
    assert set(keys) == {"A1", "A2", "C1", "P2"}

    p2 = next(r for r in res if r["key"] == "P2")
    assert "co-cited" in p2["reason"]
    # direct connections rank above the 2-hop co-citation
    assert keys.index("A1") < keys.index("P2")


def test_around_excludes_curated_and_self():
    g = NetworkXEngine()
    g.add_node("S", type="paper", title="Seed", status="curated")
    g.add_node("K", type="person", title="Known", status="curated")
    g.add_edge("K", "S", "authored")
    assert around(g, "S") == []


def test_around_unknown_node_returns_empty():
    assert around(NetworkXEngine(), "nope") == []


# ---------- path ----------

def test_find_path_returns_labeled_chain():
    g = NetworkXEngine()
    g.add_node("lab", type="lab", title="Your Lab", status="curated")
    g.add_node("p", type="person", title="Noam", status="candidate")
    g.add_node("w", type="paper", title="Paper", status="candidate")
    g.add_edge("lab", "p", "member_of")
    g.add_edge("p", "w", "authored")

    chain = find_path(g, "lab", "w")
    assert [s["key"] for s in chain] == ["lab", "p", "w"]
    assert chain[0]["rel_to_next"] == "member_of"
    assert chain[1]["rel_to_next"] == "authored"
    assert chain[2]["rel_to_next"] is None


def test_find_path_none_when_disconnected():
    g = NetworkXEngine()
    g.add_node("a"); g.add_node("z")
    assert find_path(g, "a", "z") is None


# ---------- bridges ----------

def test_bridges_ranks_the_connector_first():
    g = NetworkXEngine()
    for k in "abcde":
        g.add_node(k, type="person", title=k, status="candidate")
    for a, b in [("a", "b"), ("b", "c"), ("c", "d"), ("d", "e")]:
        g.add_edge(a, b, "x")
    top = bridges(g)
    assert top[0]["key"] == "c"


# ---------- clusters ----------

def test_clusters_finds_two_communities():
    g = NetworkXEngine()
    for k in ["a1", "a2", "a3", "b1", "b2", "b3"]:
        g.add_node(k, type="paper", title=k, status="candidate")
    # two triangles joined by a single bridge edge a1-b1
    for x, y in [("a1", "a2"), ("a2", "a3"), ("a1", "a3"),
                 ("b1", "b2"), ("b2", "b3"), ("b1", "b3"), ("a1", "b1")]:
        g.add_edge(x, y, "cites")
    cs = clusters(g)
    assert len(cs) == 2
    assert all(c["size"] == 3 for c in cs)


def test_clusters_skips_singletons():
    g = NetworkXEngine()
    for k in ["x", "y", "a1", "a2"]:
        g.add_node(k, type="paper", title=k, status="candidate")
    g.add_edge("a1", "a2", "cites")  # x and y stay singletons
    cs = clusters(g, min_size=2)
    assert len(cs) == 1
    assert set(cs[0]["members"]) == {"a1", "a2"}
