from manifexa.graph.networkx_engine import NetworkXEngine
from manifexa.graph.sync import build_graph
from manifexa.store.cache import Cache
from manifexa.store.entity import Entity
from manifexa.store.vault import Vault


def _seed(vault):
    vault.write(Entity(
        id="paper/attention",
        meta={"type": "paper", "title": "Attention", "openalex": "W1", "status": "curated"},
    ))


def test_sync_connects_candidate_to_curated_seed_via_openalex_id(tmp_path):
    vault, cache = Vault(tmp_path), Cache()
    _seed(vault)
    cache.upsert_node("A1", "person", "Noam Shazeer")
    cache.upsert_edge("A1", "W1", "authored")  # edge uses the seed's openalex key

    g = build_graph(vault, cache, NetworkXEngine())

    assert g.has_node("paper/attention")
    assert g.has_node("A1")
    assert "A1" in g.neighbors("paper/attention")  # W1 was remapped to the curated id
    assert g.node("paper/attention")["status"] == "curated"
    assert g.node("A1")["status"] == "candidate"


def test_sync_does_not_duplicate_curated_node_as_candidate(tmp_path):
    vault, cache = Vault(tmp_path), Cache()
    _seed(vault)
    cache.upsert_node("W1", "paper", "Attention")  # same entity, by openalex id

    g = build_graph(vault, cache, NetworkXEngine())

    assert not g.has_node("W1")  # remapped, not duplicated
    assert g.has_node("paper/attention")
