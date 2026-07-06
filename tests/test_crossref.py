from manifexa.sources.crossref import crossref_work_to_entity


def test_crossref_work_to_entity():
    work = {
        "DOI": "10.1/x",
        "title": ["A Paper"],
        "author": [{"given": "Jane", "family": "Doe"}, {"given": "", "family": "Smith"}],
        "issued": {"date-parts": [[2020, 5]]},
    }
    e = crossref_work_to_entity(work)
    assert e.type == "paper"
    assert e.title == "A Paper"
    assert e.id == "paper/a-paper"
    assert e.meta["year"] == 2020
    assert e.meta["doi"] == "https://doi.org/10.1/x"
    assert "[[Jane Doe]]" in e.meta["authors"]
