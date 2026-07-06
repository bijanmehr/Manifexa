"""One-file database snapshot — dump the whole store, load it back exactly.

The snapshot must be a *complete, restorable* picture: curated entities with
full content, candidate nodes, edges, and embeddings — so it round-trips into a
fresh vault + cache with nothing lost.
"""
import pytest

from manifexa.store import snapshot
from manifexa.store.cache import Cache
from manifexa.store.entity import Entity
from manifexa.store.vault import Vault


def test_dump_captures_entities_cache_edges_and_embeddings(tmp_path):
    vault, cache = Vault(tmp_path / "vault"), Cache(":memory:")
    vault.write(Entity(id="person/ada", meta={"type": "person", "title": "Ada", "status": "curated"},
                       body="hello [[person/bob]]"))
    cache.upsert_node("W1", "paper", "A Paper", {"year": 2020})
    cache.upsert_edge("person/ada", "W1", "authored")
    cache.set_embedding("W1", [0.1, 0.2])

    d = snapshot.dump(vault, cache)

    assert d["counts"]["entities"] == 1
    assert d["entities"][0]["id"] == "person/ada"
    assert d["entities"][0]["body"] == "hello [[person/bob]]"
    assert any(n["key"] == "W1" for n in d["cache_nodes"])
    assert d["cache_edges"][0]["rel"] == "authored"
    assert d["embeddings"]["W1"] == [0.1, 0.2]


def test_load_restores_into_fresh_stores(tmp_path):
    v1, c1 = Vault(tmp_path / "a" / "vault"), Cache(":memory:")
    v1.write(Entity(id="lab/x", meta={"type": "lab", "title": "X Lab", "status": "curated"}, body="notes"))
    c1.upsert_node("W2", "paper", "P", {})
    c1.upsert_edge("lab/x", "W2", "affiliated_with")
    data = snapshot.dump(v1, c1)

    v2, c2 = Vault(tmp_path / "b" / "vault"), Cache(":memory:")
    stats = snapshot.load(v2, c2, data)

    assert stats["entities"] == 1
    e = v2.read("lab/x")
    assert e.title == "X Lab"
    assert e.body == "notes"
    assert any(n["key"] == "W2" for n in c2.nodes())
    assert c2.edges()[0]["rel"] == "affiliated_with"


def test_load_rejects_a_non_snapshot(tmp_path):
    with pytest.raises(ValueError):
        snapshot.load(Vault(tmp_path / "v"), Cache(":memory:"), {"nope": 1})
