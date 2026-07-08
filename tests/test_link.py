"""Manually connecting entities — the `link` command + curated wikilink edges.

A hand-made entity is an isolated node until you connect it. `link` writes a
`[[wikilink]]` into the source's frontmatter (files-as-truth, Obsidian-visible)
and `build_graph` materialises it as a real graph edge — so you can say "this
paper is about that topic" and have it show up in the graph.
"""
from manifexa.app import App
from manifexa.store.entity import Entity
from manifexa.tui import dispatch


def test_entity_relations_parse_rel_and_bare_wikilinks():
    e = Entity(id="paper/x", meta={"type": "paper", "title": "X", "links": [
        "about :: [[topic/thermodynamics]]",     # labelled relation
        "[[person/ada-lovelace]]",               # bare wikilink → default 'related'
    ]})
    assert e.relations == [("about", "topic/thermodynamics"),
                           ("related", "person/ada-lovelace")]


def _pair(tmp_path, monkeypatch):
    monkeypatch.setenv("MANIFEXA_ENGINE", "networkx")
    a = App(str(tmp_path))
    p = a.create("paper", "On Heat")
    t = a.create("topic", "Thermodynamics")
    return a, p, t


def test_link_creates_a_graph_edge_both_ways(tmp_path, monkeypatch):
    a, p, t = _pair(tmp_path, monkeypatch)
    a.link(p, t, "about")
    assert t in [n for n, _ in a.graph().neighbors_with_rel(p)]   # paper → topic
    assert p in [n for n, _ in a.graph().neighbors_with_rel(t)]   # …and topic → paper (undirected)


def test_link_persists_files_as_truth(tmp_path, monkeypatch):
    a, p, t = _pair(tmp_path, monkeypatch)
    a.link(p, t, "about")
    # stored as a wikilink in the source's frontmatter — survives a full rebuild
    assert a.open(p).meta["links"] == ["about :: [[topic/thermodynamics]]"]
    a.rebuild()
    assert t in a.graph().neighbors(p)


def test_link_is_idempotent(tmp_path, monkeypatch):
    a, p, t = _pair(tmp_path, monkeypatch)
    a.link(p, t)
    a.link(p, t, "about")                         # same target again → no duplicate
    assert a.open(p).meta["links"] == ["related :: [[topic/thermodynamics]]"]


def test_link_command_connects_and_shows_in_open(tmp_path, monkeypatch):
    a, p, t = _pair(tmp_path, monkeypatch)
    out = dispatch(a, f"link {p} {t} about")
    assert "linked" in out.lower()
    assert "thermodynamics" in dispatch(a, f"open {p}").lower()   # connection now visible


def test_link_command_rejects_unknown_target(tmp_path, monkeypatch):
    a, p, t = _pair(tmp_path, monkeypatch)
    out = dispatch(a, f"link {p} topic/nope")
    assert "nope" in out and ("doesn't exist" in out.lower() or "no such" in out.lower())
    assert a.open(p).meta.get("links") in (None, [])              # nothing written on a bad link


def test_link_many_connects_source_to_all_targets(tmp_path, monkeypatch):
    monkeypatch.setenv("MANIFEXA_ENGINE", "networkx")
    a = App(str(tmp_path))
    p = a.create("paper", "P")
    t1, t2, pe = a.create("topic", "A"), a.create("concept", "B"), a.create("person", "C")
    linked, skipped = a.link_many(p, [t1, t2, pe], "related")
    assert set(linked) == {t1, t2, pe} and skipped == []
    assert {t1, t2, pe} <= {n for n, _ in a.graph().neighbors_with_rel(p)}


def test_link_many_skips_bad_targets_without_aborting(tmp_path, monkeypatch):
    monkeypatch.setenv("MANIFEXA_ENGINE", "networkx")
    a = App(str(tmp_path))
    p, lab, t = a.create("paper", "P"), a.create("lab", "MIT"), a.create("topic", "T")
    linked, skipped = a.link_many(p, [t, lab], "about")          # about → topic ok, lab not
    assert t in linked and any(dst == lab for dst, _ in skipped)


def test_link_command_takes_multiple_targets(tmp_path, monkeypatch):
    monkeypatch.setenv("MANIFEXA_ENGINE", "networkx")
    a = App(str(tmp_path))
    p = a.create("paper", "On Heat")
    t1, t2 = a.create("topic", "Thermo"), a.create("concept", "Entropy")
    out = dispatch(a, f"link {p} {t1} {t2} about")               # two targets + a relation
    assert "linked" in out.lower()
    nbrs = {n for n, _ in a.graph().neighbors_with_rel(p)}
    assert t1 in nbrs and t2 in nbrs
