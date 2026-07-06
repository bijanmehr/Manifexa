from manifexa.graph.networkx_engine import NetworkXEngine


def test_add_nodes_edges_and_neighbors():
    g = NetworkXEngine()
    g.add_node("a", type="person", title="A")
    g.add_node("b", type="paper", title="B")
    g.add_edge("a", "b", "authored")
    assert g.has_node("a")
    assert set(g.neighbors("a")) == {"b"}
    assert g.node("a")["type"] == "person"


def test_neighbors_with_rel():
    g = NetworkXEngine()
    g.add_node("a"); g.add_node("b")
    g.add_edge("a", "b", "authored")
    assert g.neighbors_with_rel("a") == [("b", "authored")]


def test_shortest_path():
    g = NetworkXEngine()
    for k in "abc":
        g.add_node(k)
    g.add_edge("a", "b", "x")
    g.add_edge("b", "c", "y")
    assert g.shortest_path("a", "c") == ["a", "b", "c"]


def test_shortest_path_none_when_disconnected():
    g = NetworkXEngine()
    g.add_node("a"); g.add_node("z")
    assert g.shortest_path("a", "z") is None


def test_betweenness_identifies_bridge():
    g = NetworkXEngine()
    for k in "abcde":
        g.add_node(k)
    for a, b in [("a", "b"), ("b", "c"), ("c", "d"), ("d", "e")]:
        g.add_edge(a, b, "x")
    bc = g.betweenness()
    assert bc["c"] == max(bc.values())


def test_clear_empties_the_graph():
    g = NetworkXEngine()
    g.add_node("a"); g.add_node("b"); g.add_edge("a", "b", "x")
    g.clear()
    assert g.nodes() == []
    assert not g.has_node("a")
