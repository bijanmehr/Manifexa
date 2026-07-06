from manifexa.sources.extract import extract_into_cache
from manifexa.store.cache import Cache


class FakeExtractor:
    def extract(self, text):
        return {
            "entities": [
                {"type": "person", "title": "Noam Shazeer"},
                {"type": "lab", "title": "Google Brain"},
            ],
            "edges": [
                {"source": "Noam Shazeer", "target": "Google Brain", "rel": "member_of"},
                {"source": "Noam Shazeer", "target": "Unknown Thing", "rel": "x"},  # dangling → dropped
            ],
        }


def test_extract_into_cache_stores_entities_and_edges():
    cache = Cache()
    res = extract_into_cache(FakeExtractor(), cache, "Noam Shazeer works at Google Brain.")
    assert res["entities"] == 2
    assert res["edges"] == 1  # the dangling edge is dropped

    keys = {n["key"] for n in cache.nodes()}
    assert {"person/noam-shazeer", "lab/google-brain"} <= keys

    triples = {(e["src"], e["dst"], e["rel"]) for e in cache.edges()}
    assert ("person/noam-shazeer", "lab/google-brain", "member_of") in triples
