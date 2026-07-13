from manifexa.app import App


class FakePC:
    def get_author(self, aid):
        return {"id": "https://openalex.org/A1", "display_name": "P", "works_count": 1,
                "cited_by_count": 0, "summary_stats": {"h_index": 1}}

    def works_by_author(self, aid, from_date, cap=200):
        return []


def test_add_person_populates_graph(tmp_path):
    app = App(str(tmp_path), clock=lambda: (2026, "2021-07-12"), people_client=FakePC())
    res = app.add_person("A1")
    assert res["person"] == "A1"
    assert app.person_view("A1")["h_index"] == 1
    assert app.engine.has_node("A1")          # projected into the graph by rebuild()


def test_person_view_missing_is_none(tmp_path):
    app = App(str(tmp_path), clock=lambda: (2026, "2021-07-12"), people_client=FakePC())
    assert app.person_view("A404") is None


def test_window_years_default_and_configurable(tmp_path):
    from manifexa import tui
    app = App(str(tmp_path))
    assert app._window_years() == 5                 # default = last 5 years
    tui.save_config(app.home, window=3)
    assert app._window_years() == 3                 # settable (2–5)


class RichPC:
    def get_author(self, aid):
        return {"id": "https://openalex.org/A1", "display_name": "Ada Prorok",
                "orcid": "https://orcid.org/0000-0002-0001", "works_count": 142,
                "cited_by_count": 4100, "summary_stats": {"h_index": 31}}

    def works_by_author(self, aid, from_date, cap=200):
        return [{"id": "https://openalex.org/W1", "title": "P", "doi": None, "publication_year": 2025,
                 "topics": [{"display_name": "Multi-Robot"}],
                 "authorships": [{"author": {"id": "https://openalex.org/A1", "display_name": "Ada Prorok"},
                                  "raw_affiliation_strings": ["University of Cambridge"]},
                                 {"author": {"id": "https://openalex.org/A2", "display_name": "Bo Q"}}]}]


def test_graph_data_segregates_seed_from_coauthor_and_builds_fields(tmp_path):
    app = App(str(tmp_path), clock=lambda: (2026, "2021-07-12"), people_client=RichPC())
    app.add_person("A1")                                  # seed A1 + coauthor stub A2
    d = app.graph_data()
    byk = {n["key"]: n for n in d["nodes"]}
    assert byk["A1"]["role"] == "seed"                    # the person you added
    assert byk["A2"]["role"] == "coauthor"                # a pulled-in stub
    labels = dict(byk["A1"]["fields"])                    # full field list for the inspector
    assert "h-index" in labels and labels["h-index"] == "31"
    assert "ORCID" in labels and "0000-0002-0001" in labels["ORCID"]
    assert byk["A1"]["h"] == 31                           # flat field for the audit table
    assert byk["A2"]["fields"] == [] or "role" in byk["A2"]  # stub has little/no field data
    assert byk["A1"]["cluster"] == byk["A2"]["cluster"] >= 0  # same Louvain community (color-by-cluster)
