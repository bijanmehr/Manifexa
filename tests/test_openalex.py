import json
import pathlib

from manifexa.sources.openalex import (
    normalize_openalex_id,
    work_to_entity,
    extract_neighbors,
    reconstruct_abstract,
)

FIX = pathlib.Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIX / name).read_text())


def test_normalize_openalex_id_strips_url_prefix():
    assert normalize_openalex_id("https://openalex.org/W2963403868") == "W2963403868"
    assert normalize_openalex_id("W2963403868") == "W2963403868"


def test_work_to_entity():
    e = work_to_entity(load("work_attention.json"))
    assert e.id == "paper/attention-is-all-you-need"
    assert e.type == "paper"
    assert e.title == "Attention Is All You Need"
    assert e.status == "curated"
    assert e.meta["year"] == 2017
    assert e.meta["openalex"] == "W2963403868"
    assert e.meta["authors"] == ["[[Ashish Vaswani]]", "[[Noam Shazeer]]"]


def test_reconstruct_abstract_from_inverted_index():
    assert reconstruct_abstract({"Attention": [0], "is": [1], "all": [2]}) == "Attention is all"
    assert reconstruct_abstract(None) == "" and reconstruct_abstract({}) == ""


def test_work_to_entity_pulls_venue_topics_and_abstract():
    work = {
        "id": "https://openalex.org/W1", "title": "T", "publication_year": 2020,
        "doi": "https://doi.org/10.1/x",
        "authorships": [{"author": {"display_name": "Ada"}}],
        "primary_location": {"source": {"display_name": "Neural Computation"}},
        "topics": [{"display_name": "Neural Networks"}, {"display_name": "Deep Learning"}],
        "abstract_inverted_index": {"An": [0], "abstract.": [1]},
    }
    e = work_to_entity(work)
    assert e.meta["venue"] == "Neural Computation"
    assert e.meta["topics"] == ["[[topic/neural-networks]]", "[[topic/deep-learning]]"]
    assert "An abstract." in e.body                       # abstract lands in the note body


def test_extract_neighbors_nodes():
    nodes, _edges = extract_neighbors(load("work_attention.json"))
    by_key = {n["key"]: n for n in nodes}
    assert by_key["A5019527971"]["type"] == "person"
    assert by_key["A5019527971"]["title"] == "Noam Shazeer"
    assert by_key["I1291425158"]["type"] == "lab"
    assert by_key["W2949547662"]["type"] == "paper"


def test_extract_neighbors_edges():
    _nodes, edges = extract_neighbors(load("work_attention.json"))
    triples = {(e["src"], e["dst"], e["rel"]) for e in edges}
    assert ("A5019527971", "W2963403868", "authored") in triples
    assert ("A5019527971", "I1291425158", "affiliated_with") in triples
    assert ("W2963403868", "W2949547662", "cites") in triples
