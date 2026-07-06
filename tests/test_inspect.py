"""App.inspect + schema enforcement on write, and the richer `open` render."""
import pytest

from manifexa.app import App
from manifexa.store.schema import SchemaError
from manifexa.tui import dispatch


def _app(tmp_path, monkeypatch):
    monkeypatch.setenv("MANIFEXA_ENGINE", "networkx")
    return App(str(tmp_path))


def test_inspect_assembles_attributes_and_relations(tmp_path, monkeypatch):
    a = _app(tmp_path, monkeypatch)
    p = a.create("paper", "On Heat", doi="10.1/x", year=1850)
    t = a.create("topic", "Thermodynamics")
    a.link(p, t, "about")
    v = a.inspect(p)
    assert v.attributes["doi"] == "10.1/x" and v.attributes["year"] == 1850
    assert any(n["key"] == t for n in v.relations["about"])


def test_create_rejects_unknown_type(tmp_path, monkeypatch):
    a = _app(tmp_path, monkeypatch)
    with pytest.raises(SchemaError):
        a.create("widget", "X")


def test_create_accepts_known_typed_fields(tmp_path, monkeypatch):
    a = _app(tmp_path, monkeypatch)
    p = a.create("paper", "P", year=2020, doi="10.1/x")     # recommended present → no warning-block
    assert a.open(p).meta["year"] == 2020


def test_create_rejects_bad_typed_value(tmp_path, monkeypatch):
    a = _app(tmp_path, monkeypatch)
    with pytest.raises(SchemaError):
        a.create("paper", "P", year="someday")              # year must be a number


def test_link_rejects_disallowed_target_type(tmp_path, monkeypatch):
    a = _app(tmp_path, monkeypatch)
    p = a.create("paper", "P")
    lab = a.create("lab", "MIT")
    with pytest.raises(SchemaError):
        a.link(p, lab, "about")                             # about → topic/concept, not lab


def test_link_allows_a_valid_relation(tmp_path, monkeypatch):
    a = _app(tmp_path, monkeypatch)
    p = a.create("paper", "P")
    person = a.create("person", "Ada")
    a.link(p, person, "authored")
    assert person in a.graph().neighbors(p)


def test_open_render_shows_attributes_and_grouped_relations(tmp_path, monkeypatch):
    a = _app(tmp_path, monkeypatch)
    p = a.create("paper", "On Heat", doi="10.1/x", year=1850)
    t = a.create("topic", "Thermodynamics")
    a.link(p, t, "about")
    out = dispatch(a, f"open {p}")
    assert "10.1/x" in out and "1850" in out                # attributes surfaced
    assert "Thermodynamics" in out and "about" in out       # relation, grouped by kind


def test_dispatch_link_bad_target_is_friendly(tmp_path, monkeypatch):
    a = _app(tmp_path, monkeypatch)
    a.create("paper", "P")
    a.create("lab", "MIT")
    out = dispatch(a, "link paper/p lab/mit about")
    assert "traceback" not in out.lower()
    assert "topic" in out.lower() or "expect" in out.lower()
