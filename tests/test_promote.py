import pytest

from manifexa.graph.networkx_engine import NetworkXEngine
from manifexa.graph.sync import build_graph
from manifexa.promote import promote
from manifexa.store.cache import Cache
from manifexa.store.entity import Entity
from manifexa.store.vault import Vault


def test_promote_creates_curated_file_from_candidate(tmp_path):
    vault, cache = Vault(tmp_path / "v"), Cache()
    cache.upsert_node("A1", "person", "Noam Shazeer")

    eid = promote(vault, cache, "A1", note="bridge person")

    assert eid == "person/noam-shazeer"
    e = vault.read(eid)
    assert e.status == "curated"
    assert e.meta["openalex"] == "A1"
    assert e.body == "bridge person"


def test_promote_unknown_candidate_raises(tmp_path):
    with pytest.raises(KeyError):
        promote(Vault(tmp_path), Cache(), "nope")


def test_promoted_entity_reconciles_in_graph(tmp_path):
    vault, cache = Vault(tmp_path / "v"), Cache()
    vault.write(Entity(
        id="paper/attention",
        meta={"type": "paper", "title": "Attention", "openalex": "W1", "status": "curated"},
    ))
    cache.upsert_node("A1", "person", "Noam")
    cache.upsert_edge("A1", "W1", "authored")

    promote(vault, cache, "A1")
    g = build_graph(vault, cache, NetworkXEngine())

    assert g.node("person/noam")["status"] == "curated"
    assert "person/noam" in g.neighbors("paper/attention")
    assert not g.has_node("A1")  # candidate remapped to the curated id
