from manifexa.graph.networkx_engine import NetworkXEngine
from manifexa.discovery import core


def test_clusters_group_coauthors():
    g = NetworkXEngine()
    for k in ["A", "B", "C"]:
        g.add_node(k, type="person", title=k, status="candidate")
    g.add_edge("A", "B", "coauthored")
    g.add_edge("B", "C", "coauthored")
    cl = core.clusters(g, min_size=2)
    assert cl and cl[0]["size"] == 3          # one inferred group (same_group)


def test_coauthored_phrase_present():
    assert core._REL_PHRASE["coauthored"] == "co-authored a paper"
    assert core._REL_PHRASE["same_group"] == "same research group"


def test_around_labels_coauthor_reason():
    g = NetworkXEngine()
    for k in ["A", "B"]:
        g.add_node(k, type="person", title=k, status="candidate")
    g.add_edge("A", "B", "coauthored")
    rs = core.around(g, "A")
    assert rs and rs[0]["key"] == "B"
    assert rs[0]["reason"] == "co-authored a paper"
