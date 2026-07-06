"""NodeView — the structured record for a node: attributes + relations + notes.

``build_view(entity, engine)`` reads the entity's frontmatter for scalar
attributes and the graph for its typed relations (grouped by kind), so inspecting
a paper yields its doi/year plus its authors/topics/citations as first-class
groups — the substrate for exploration.
"""
from manifexa.store.entity import Entity
from manifexa.store.node import build_view


class _FakeEngine:
    def __init__(self, edges, nodes):
        self._edges = edges          # {key: [(neighbour, rel), …]}
        self._nodes = nodes          # {key: {key,type,title,status}}

    def has_node(self, k):
        return k in self._nodes

    def node(self, k):
        return self._nodes.get(k)

    def neighbors_with_rel(self, k):
        return self._edges.get(k, [])


def test_build_view_splits_attributes_from_relations():
    e = Entity(id="paper/on-heat", body="the note",
               meta={"type": "paper", "title": "On Heat", "status": "curated",
                     "doi": "10.1/x", "year": 1850})
    eng = _FakeEngine(
        {"paper/on-heat": [("topic/thermo", "about"), ("person/clausius", "authored")]},
        {"paper/on-heat": {"key": "paper/on-heat", "type": "paper", "title": "On Heat", "status": "curated"},
         "topic/thermo": {"key": "topic/thermo", "type": "topic", "title": "Thermodynamics", "status": "curated"},
         "person/clausius": {"key": "person/clausius", "type": "person", "title": "Clausius", "status": "candidate"}})
    v = build_view(e, eng)
    assert v.type == "paper" and v.title == "On Heat"
    assert v.attributes["doi"] == "10.1/x" and v.attributes["year"] == 1850
    assert [n["title"] for n in v.relations["about"]] == ["Thermodynamics"]
    assert [n["title"] for n in v.relations["authored"]] == ["Clausius"]
    assert v.notes == "the note"


def test_build_view_folds_authors_meta_into_the_authored_relation():
    e = Entity(id="paper/p", meta={"type": "paper", "title": "P", "status": "curated",
                                   "authors": ["[[Ada Lovelace]]", "[[Charles Babbage]]"]})
    v = build_view(e, _FakeEngine({}, {"paper/p": {"key": "paper/p", "type": "paper", "title": "P", "status": "curated"}}))
    names = [n["title"] for n in v.relations.get("authored", [])]
    assert "Ada Lovelace" in names and "Charles Babbage" in names
    assert "authors" not in v.attributes            # shown as a relation, not a scalar blob


def test_build_view_carries_schema_warnings():
    e = Entity(id="paper/p", meta={"type": "paper", "title": "P", "status": "curated"})   # no doi/year
    v = build_view(e, _FakeEngine({}, {"paper/p": {"key": "paper/p", "type": "paper", "title": "P", "status": "curated"}}))
    assert any(i.severity == "warn" and i.field in ("doi", "year") for i in v.issues)
