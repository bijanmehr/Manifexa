"""Offline end-to-end: the whole people flow through the interactive shell,
driven by a fake OpenAlex client — no network."""
from manifexa import tui
from manifexa.app import App


class FakePC:
    def get_author(self, aid):
        return {"id": f"https://openalex.org/{aid}", "display_name": aid,
                "works_count": 4, "cited_by_count": 7, "summary_stats": {"h_index": 3}}

    def works_by_author(self, aid, from_date, cap=200):
        return [{"id": "https://openalex.org/W1", "title": "Shared", "doi": None, "publication_year": 2025,
                 "topics": [{"display_name": "Multi-Robot"}],
                 "authorships": [{"author": {"id": "https://openalex.org/A1", "display_name": "A1"}},
                                 {"author": {"id": "https://openalex.org/A2", "display_name": "A2"}}]}]


def test_end_to_end_people_flow(tmp_path):
    app = App(str(tmp_path), clock=lambda: (2026, "2021-01-01"), people_client=FakePC())
    assert "A1" in tui.dispatch(app, "add A1")
    assert "Multi-Robot" in tui.dispatch(app, "who A1")
    near = tui.dispatch(app, "near A1")
    assert "A2" in near                                  # the coauthor is surfaced
    assert "co-authored a paper" in near                 # people-graph phrase (Task 7)


def test_expand_fleshes_a_coauthor_stub(tmp_path):
    app = App(str(tmp_path), clock=lambda: (2026, "2021-01-01"), people_client=FakePC())
    tui.dispatch(app, "add A1")
    assert app.cache.get_node("A2")["meta"]["stub"] is True     # A2 arrived as a stub
    tui.dispatch(app, "expand A2")                              # flesh it
    a2 = app.cache.get_node("A2")
    assert a2["meta"].get("h_index") == 3 and "stub" not in a2["meta"]   # now a full node
