import json
import pathlib

from manifexa.app import App

FIX = pathlib.Path(__file__).parent / "fixtures"


class FakeClient:
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


def test_full_loop_add_around_promote(tmp_path):
    app = App(tmp_path, client=FakeClient())

    res = app.add("W2963403868")
    eid = res["entity"]
    assert eid == "paper/attention-is-all-you-need"

    found = app.around(eid)
    assert "A5019527971" in [r["key"] for r in found]  # Noam surfaced as a candidate

    new_id = app.promote("A5019527971", note="the bridge")
    assert new_id == "person/noam-shazeer"
    assert app.open(new_id).status == "curated"
    assert app.open(new_id).body == "the bridge"

    keys2 = [r["key"] for r in app.around(eid)]
    assert "A5019527971" not in keys2          # remapped to curated id
    assert "person/noam-shazeer" not in keys2  # now curated, no longer surfaced


def test_path_between_seed_and_reference(tmp_path):
    app = App(tmp_path, client=FakeClient())
    app.add("W2963403868")
    chain = app.path("paper/attention-is-all-you-need", "W2949547662")
    assert chain is not None
    assert chain[0]["key"] == "paper/attention-is-all-you-need"
    assert chain[-1]["key"] == "W2949547662"


def test_set_note_edits_entity_file(tmp_path):
    app = App(tmp_path, client=FakeClient())
    app.add("W2963403868")
    app.set_note("paper/attention-is-all-you-need", "my notes\n")
    assert app.open("paper/attention-is-all-you-need").body == "my notes\n"


def test_remove_deletes_entity_and_updates_graph(tmp_path):
    import pytest

    app = App(tmp_path, client=FakeClient())
    app.add("W2963403868")
    assert app.open("paper/attention-is-all-you-need").status == "curated"

    app.remove("paper/attention-is-all-you-need")

    with pytest.raises(FileNotFoundError):
        app.open("paper/attention-is-all-you-need")
    assert not app.graph().has_node("paper/attention-is-all-you-need")


def _neo4j_engine_or_skip():
    import os

    from manifexa.graph.neo4j_engine import Neo4jEngine

    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    auth = (os.environ.get("NEO4J_USER", "neo4j"), os.environ.get("NEO4J_PASSWORD", "manifexa-dev"))
    try:
        eng = Neo4jEngine(uri, auth)
        eng.clear()
        return eng
    except Exception as exc:
        import pytest

        pytest.skip(f"Neo4j not available: {exc}")


def test_full_loop_on_neo4j_backend(tmp_path):
    engine = _neo4j_engine_or_skip()
    app = App(tmp_path, client=FakeClient(), engine=engine)

    res = app.add("W2963403868")
    eid = res["entity"]
    assert "A5019527971" in [r["key"] for r in app.around(eid)]

    assert app.promote("A5019527971") == "person/noam-shazeer"
    assert "person/noam-shazeer" not in [r["key"] for r in app.around(eid)]
    engine.close()


def test_similar_surfaces_by_embedding(tmp_path):
    app = App(tmp_path, client=FakeClient())
    app.add("W2963403868")
    # embeddings keyed by openalex id (as Semantic Scholar enrichment would set them)
    app.cache.set_embedding("W2963403868", [1.0, 0.0])   # the seed
    app.cache.set_embedding("W2949547662", [0.95, 0.05])  # a reference — similar
    app.cache.set_embedding("W3000000001", [0.0, 1.0])    # a citation — dissimilar

    res = app.similar("paper/attention-is-all-you-need")
    assert res[0]["key"] == "W2949547662"
    assert res[0]["score"] > res[-1]["score"]


def test_embed_then_similar(tmp_path):
    class FakeS2:
        def embedding(self, doi):
            return {
                "https://doi.org/10.48550/arxiv.1706.03762": [1.0, 0.0],
                "10.1/ref": [0.95, 0.05],
            }.get(doi)

    app = App(tmp_path, client=FakeClient(), s2_client=FakeS2())
    app.add("W2963403868")
    app.cache.upsert_node("Wref", "paper", "A Ref", {"openalex": "Wref", "doi": "10.1/ref"})

    res = app.embed()
    assert res["embedded"] == 2

    sim = app.similar("paper/attention-is-all-you-need")
    assert sim[0]["key"] == "Wref"


def test_add_falls_back_to_crossref(tmp_path):
    class FailingOpenAlex:
        def get_work(self, seed_id):
            raise RuntimeError("openalex unavailable")

    class FakeCrossref:
        def get_work(self, doi):
            return {"DOI": "10.1/x", "title": ["Fallback Paper"],
                    "author": [{"given": "A", "family": "B"}], "issued": {"date-parts": [[2019]]}}

    app = App(tmp_path, client=FailingOpenAlex(), crossref_client=FakeCrossref())
    res = app.add("10.1/x")
    assert res["source"] == "crossref"
    assert app.open("paper/fallback-paper").title == "Fallback Paper"


def test_create_writes_curated_entity_of_any_type(tmp_path):
    app = App(tmp_path, client=FakeClient())
    eid = app.create("person", "Yoshua Bengio", body="pioneer", affiliations=["[[MILA]]"])
    assert eid == "person/yoshua-bengio"
    e = app.open(eid)
    assert e.type == "person" and e.status == "curated"
    assert e.body == "pioneer"
    assert e.meta["affiliations"] == ["[[MILA]]"]


def test_source_search_maps_results(tmp_path):
    class SearchClient(FakeClient):
        def search_works(self, q, per_page=8):
            return [{"id": "https://openalex.org/W9", "title": "Found Paper", "publication_year": 2021}]

    app = App(tmp_path, client=SearchClient())
    res = app.source_search("transformers")
    assert res[0] == {"key": "W9", "title": "Found Paper", "year": 2021, "type": "paper"}


def test_extract_creates_candidates(tmp_path):
    class FakeExtractor:
        def extract(self, text):
            return {"entities": [{"type": "person", "title": "Jeff Dean"}], "edges": []}

    app = App(tmp_path, client=FakeClient(), extractor=FakeExtractor())
    res = app.extract("Jeff Dean leads Google AI.")
    assert res["entities"] == 1
    assert app.graph().has_node("person/jeff-dean")
    assert app.graph().node("person/jeff-dean")["status"] == "candidate"


def test_export_returns_graph_json(tmp_path):
    app = App(tmp_path, client=FakeClient())
    app.add("W2963403868")
    data = app.export()
    assert "paper/attention-is-all-you-need" in {n["key"] for n in data["nodes"]}
    assert len(data["edges"]) >= 1
