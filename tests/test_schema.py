"""The enforced per-type node schema — validation on write.

Each type declares typed attributes (some required/recommended) and relation
kinds with allowed target types. ``validate`` returns errors + warnings;
``relation_ok`` checks an edge's endpoints.
"""
from manifexa.store import schema
from manifexa.store.entity import Entity


def _paper(**meta):
    m = {"type": "paper", "title": "On Heat", "status": "curated"}
    m.update(meta)
    return Entity(id="paper/on-heat", meta=m)


def test_valid_paper_has_no_errors():
    assert schema.errors(schema.validate(_paper(doi="10.1/x", year=2020))) == []


def test_missing_required_title_is_an_error():
    e = Entity(id="paper/x", meta={"type": "paper", "status": "curated"})
    assert any(i.field == "title" for i in schema.errors(schema.validate(e)))


def test_missing_recommended_field_is_a_warning_not_error():
    issues = schema.validate(_paper())                       # no doi / year
    warns = {i.field for i in issues if i.severity == "warn"}
    assert "doi" in warns and "year" in warns
    assert schema.errors(schema.validate(_paper())) == []    # but still allowed


def test_wrong_typed_value_is_an_error():
    assert any(i.field == "year" for i in schema.errors(schema.validate(_paper(year="soon"))))


def test_unknown_field_is_a_warning():
    issues = schema.validate(_paper(titel="typo"))           # misspelled 'title'
    assert any(i.severity == "warn" and i.field == "titel" for i in issues)


def test_unknown_type_is_an_error():
    e = Entity(id="widget/x", meta={"type": "widget", "title": "X", "status": "curated"})
    assert any(i.field == "type" for i in schema.errors(schema.validate(e)))


def test_universal_fields_are_allowed():
    assert schema.errors(schema.validate(_paper(openalex="W123", tags=["ml"]))) == []


def test_openalex_enriched_paper_validates_clean():
    e = _paper(year=2026, doi="10.48550/x", openalex="W9",
               authors=["[[Karl Friston]]"])
    assert schema.errors(schema.validate(e)) == []           # real enrichment output is valid


def test_relation_ok_accepts_allowed_target():
    assert schema.relation_ok("paper", "about", "topic") is None
    assert schema.relation_ok("paper", "authored", "person") is None


def test_relation_ok_rejects_disallowed_target():
    i = schema.relation_ok("paper", "about", "lab")          # about → topic/concept
    assert i is not None and i.severity == "error"


def test_unknown_relation_name_warns_but_allows():
    i = schema.relation_ok("paper", "frobnicates", "topic")
    assert i is None or i.severity == "warn"


def test_related_is_generic_and_joins_any_types():
    # the default `link` relation must connect anything — concept↔paper included
    assert schema.relation_ok("concept", "related", "paper") is None
    assert schema.relation_ok("topic", "related", "person") is None
    assert schema.relation_ok("paper", "related", "lab") is None


def test_wrong_specific_relation_error_suggests_a_valid_one():
    i = schema.relation_ok("concept", "about", "person")     # concept 'about' → paper/book only
    assert i is not None and i.severity == "error"
    assert "related" in i.message                            # points at a relation that would work
