import json
import pathlib

from manifexa.sources.enrich import enrich_seed
from manifexa.store.cache import Cache
from manifexa.store.vault import Vault

FIX = pathlib.Path(__file__).parent / "fixtures"


class FakeClient:
    """Returns recorded shapes so enrichment is verified without the network."""

    def __init__(self):
        self.work = json.loads((FIX / "work_attention.json").read_text())

    def get_work(self, seed_id):
        return self.work

    def works_by_ids(self, ids):
        return [
            {"id": "https://openalex.org/W2949547662", "title": "Neural Machine Translation"},
            {"id": "https://openalex.org/W2950527759", "title": "Sequence to Sequence Learning"},
        ]

    def cited_by(self, seed_id, per_page=25):
        return [{"id": "https://openalex.org/W3000000001", "title": "BERT"}]


def test_enrich_writes_curated_seed(tmp_path):
    vault, cache = Vault(tmp_path), Cache()
    enrich_seed(FakeClient(), vault, cache, "W2963403868")
    seed = vault.read("paper/attention-is-all-you-need")
    assert seed.status == "curated"
    assert seed.meta["openalex"] == "W2963403868"


def test_enrich_caches_people_labs_and_titled_papers(tmp_path):
    vault, cache = Vault(tmp_path), Cache()
    enrich_seed(FakeClient(), vault, cache, "W2963403868")
    by_key = {n["key"]: n for n in cache.nodes()}
    assert by_key["A5019527971"]["type"] == "person"
    assert by_key["I1291425158"]["type"] == "lab"
    assert by_key["W2949547662"]["type"] == "paper"
    assert by_key["W2949547662"]["title"] == "Neural Machine Translation"  # reference titled
    assert by_key["W3000000001"]["title"] == "BERT"  # citation pulled in


def test_enrich_caches_edges_including_citation(tmp_path):
    vault, cache = Vault(tmp_path), Cache()
    enrich_seed(FakeClient(), vault, cache, "W2963403868")
    triples = {(e["src"], e["dst"], e["rel"]) for e in cache.edges()}
    assert ("A5019527971", "W2963403868", "authored") in triples
    assert ("W2963403868", "W2949547662", "cites") in triples
    assert ("W3000000001", "W2963403868", "cites") in triples
