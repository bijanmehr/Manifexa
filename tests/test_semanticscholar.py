from manifexa.sources.semanticscholar import (
    normalize_doi,
    s2_embedding,
    enrich_embeddings,
)
from manifexa.store.cache import Cache
from manifexa.store.entity import Entity
from manifexa.store.vault import Vault


def test_normalize_doi_strips_url():
    assert normalize_doi("https://doi.org/10.1/abc") == "10.1/abc"
    assert normalize_doi("10.1/abc") == "10.1/abc"


def test_s2_embedding_extracts_vector():
    assert s2_embedding({"embedding": {"model": "specter_v2", "vector": [0.1, 0.2]}}) == [0.1, 0.2]
    assert s2_embedding({"embedding": None}) is None
    assert s2_embedding({}) is None


class FakeS2:
    """Looks up by the raw DOI string passed in (the real client normalizes)."""

    def __init__(self, by_doi):
        self.by_doi = by_doi

    def embedding(self, doi):
        return self.by_doi.get(doi)


def test_enrich_embeddings_attaches_vectors_by_doi(tmp_path):
    vault, cache = Vault(tmp_path), Cache()
    vault.write(Entity(
        id="paper/x",
        meta={"type": "paper", "title": "X", "openalex": "W1", "doi": "https://doi.org/10.1/x", "status": "curated"},
    ))
    cache.upsert_node("W2", "paper", "Y", {"openalex": "W2", "doi": "10.1/y"})
    cache.upsert_node("A1", "person", "Person", {"openalex": "A1"})  # no DOI → skipped

    client = FakeS2({"https://doi.org/10.1/x": [1.0, 0.0], "10.1/y": [0.0, 1.0]})
    res = enrich_embeddings(client, vault, cache)

    assert res["embedded"] == 2
    assert cache.get_embedding("W1") == [1.0, 0.0]  # seed, under its openalex key
    assert cache.get_embedding("W2") == [0.0, 1.0]
    assert cache.get_embedding("A1") is None
