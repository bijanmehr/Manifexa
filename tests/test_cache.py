import threading

from manifexa.store.cache import Cache


def test_upsert_and_get_node():
    c = Cache()
    c.upsert_node("W123", "paper", "Attention", {"year": 2017})
    n = c.get_node("W123")
    assert n["key"] == "W123"
    assert n["type"] == "paper"
    assert n["title"] == "Attention"
    assert n["meta"] == {"year": 2017}
    assert n["source"] == "openalex"


def test_get_missing_node_returns_none():
    assert Cache().get_node("nope") is None


def test_upsert_node_is_idempotent_on_key():
    c = Cache()
    c.upsert_node("W123", "paper", "Old title")
    c.upsert_node("W123", "paper", "New title")
    assert c.get_node("W123")["title"] == "New title"
    assert len(c.nodes()) == 1


def test_upsert_and_list_edges_dedup():
    c = Cache()
    c.upsert_edge("A1", "W1", "authored")
    c.upsert_edge("A1", "W1", "authored")  # duplicate, same (src,dst,rel)
    c.upsert_edge("W1", "W2", "cites")
    edges = c.edges()
    assert len(edges) == 2
    assert {"src": "A1", "dst": "W1", "rel": "authored", "source": "openalex"} in edges


def test_nodes_lists_all():
    c = Cache()
    c.upsert_node("W1", "paper", "P1")
    c.upsert_node("A1", "person", "Person 1")
    assert {n["key"] for n in c.nodes()} == {"W1", "A1"}


def test_persists_to_file(tmp_path):
    path = tmp_path / "cache.db"
    c = Cache(path)
    c.upsert_node("W1", "paper", "P1")
    c.close()
    c2 = Cache(path)
    assert c2.get_node("W1")["title"] == "P1"


def test_usable_from_another_thread():
    # the threaded web server touches the cache from request threads
    c = Cache()
    c.upsert_node("W1", "paper", "P1")
    result = {}

    def worker():
        result["node"] = c.get_node("W1")
        c.upsert_node("W2", "paper", "P2")

    t = threading.Thread(target=worker)
    t.start()
    t.join()

    assert result["node"]["title"] == "P1"
    assert c.get_node("W2")["title"] == "P2"


def test_set_and_get_embedding():
    c = Cache()
    c.set_embedding("W1", [0.1, 0.2, 0.3])
    assert c.get_embedding("W1") == [0.1, 0.2, 0.3]
    assert c.get_embedding("missing") is None


def test_embeddings_returns_all():
    c = Cache()
    c.set_embedding("W1", [1.0, 0.0])
    c.set_embedding("W2", [0.0, 1.0])
    assert c.embeddings() == {"W1": [1.0, 0.0], "W2": [0.0, 1.0]}
