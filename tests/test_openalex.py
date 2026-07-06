import json
import pathlib

from manifexa.sources.openalex import (
    normalize_openalex_id,
    work_to_entity,
    extract_neighbors,
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
