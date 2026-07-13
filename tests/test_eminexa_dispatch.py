from manifexa import tui
from manifexa.app import App


class FakePC:
    def author_by_orcid(self, orcid):
        return {"id": "https://openalex.org/A1"}

    def get_author(self, aid):
        return {"id": "https://openalex.org/A1", "display_name": "Ada P", "works_count": 3,
                "cited_by_count": 5, "summary_stats": {"h_index": 2}}

    def works_by_author(self, aid, from_date, cap=200):
        return [{"id": "https://openalex.org/W1", "title": "P", "doi": None, "publication_year": 2025,
                 "topics": [{"display_name": "Swarms"}],
                 "authorships": [{"author": {"id": "https://openalex.org/A1", "display_name": "Ada P"}},
                                 {"author": {"id": "https://openalex.org/A2", "display_name": "Bo Q"}}]}]


def test_person_seed_matcher():
    assert tui._person_seed("A5081322765")
    assert tui._person_seed("0000-0002-1243-7707")
    assert tui._person_seed("https://scholar.google.com/citations?user=abc")
    assert not tui._person_seed("10.1145/12345")          # DOI is a paper, not a person
    assert not tui._person_seed("topic")


def test_add_routes_person_seed_and_who_renders(tmp_path):
    app = App(str(tmp_path), clock=lambda: (2026, "2021-07-12"), people_client=FakePC())
    out = tui.dispatch(app, "add 0000-0002-1243-7707")
    assert "Ada P" in out                       # the person's NAME, not just the id
    assert "A1" in out and "coauthor" in out.lower()
    who = tui.dispatch(app, "who A1")
    assert "Ada P" in who and "Swarms" in who and "Bo Q" in who


def test_groups_renders_member_names(tmp_path):
    # `groups` (clusters) must render member NAMES, not crash on the member keys
    app = App(str(tmp_path), clock=lambda: (2026, "2021-07-12"), people_client=FakePC())
    tui.dispatch(app, "add 0000-0002-1243-7707")     # A1 (Ada P) + A2 (Bo Q) stub, coauthored
    out = tui.dispatch(app, "groups")
    assert "Ada P" in out and "unknown command" not in out


def test_list_shows_people_in_graph(tmp_path):
    # people live in the cache as candidates — `list` ("everyone in the graph")
    # must still show them, not only curated vault entities
    app = App(str(tmp_path), clock=lambda: (2026, "2021-07-12"), people_client=FakePC())
    tui.dispatch(app, "add 0000-0002-1243-7707")
    out = tui.dispatch(app, "list")
    assert "Ada P" in out and "A1" in out and "A2" in out


def test_view_writes_selfcontained_html(tmp_path):
    app = App(str(tmp_path), clock=lambda: (2026, "2021-07-12"), people_client=FakePC())
    tui.dispatch(app, "add 0000-0002-1243-7707")
    out = tui.dispatch(app, f"view {tmp_path}/g.html")
    f = tmp_path / "g.html"
    assert f.exists()
    html = f.read_text()
    assert html.lower().lstrip().startswith("<!doctype html")
    assert "Ada P" in html and "Swarms" in html          # node + enriched topic embedded
    assert "g.html" in out                                # path reported


def test_window_command_sets_and_reports(tmp_path):
    app = App(str(tmp_path))
    out = tui.dispatch(app, "window 3")
    assert "3" in out and app._window_years() == 3
    assert "3" in tui.dispatch(app, "window")       # bare command reports the current window


def test_who_unknown_is_friendly(tmp_path):
    app = App(str(tmp_path), people_client=FakePC())
    assert "people graph" in tui.dispatch(app, "who A404")


SCHOLAR_HTML = """<div id="gsc_prf_in">Federico Rossi</div>
<div class="gsc_prf_il">Robotics Technologist, Jet Propulsion Laboratory</div>
<div class="gsc_prf_il" id="gsc_prf_ivh">Verified email at stanford.edu</div>
<a class="gsc_a_at">Model predictive control of mobility on demand</a>
<a class="gsc_a_at">Routing autonomous vehicles in congested networks</a>"""


class ScholarFakePC:
    def search_works(self, q, per_page=1):
        return [{"authorships": [{"author": {"id": "https://openalex.org/A1", "display_name": "Federico Rossi"}}]}]

    def get_author(self, aid):
        return {"id": "https://openalex.org/A1", "display_name": "Federico Rossi",
                "works_count": 66, "cited_by_count": 855, "summary_stats": {"h_index": 13}}

    def works_by_author(self, aid, from_date, cap=200):
        return [{"id": "https://openalex.org/W1", "title": "P", "doi": None, "publication_year": 2025,
                 "topics": [{"display_name": "Mobility on Demand"}],
                 "authorships": [{"author": {"id": "https://openalex.org/A1", "display_name": "Federico Rossi"}},
                                 {"author": {"id": "https://openalex.org/A2", "display_name": "Marco Pavone"}}]}]


def test_add_scholar_url_resolves_and_who_shows_current_affiliation(tmp_path):
    app = App(str(tmp_path), clock=lambda: (2026, "2021-01-01"),
              people_client=ScholarFakePC(), scholar_fetch=lambda url: SCHOLAR_HTML)
    out = tui.dispatch(app, "add https://scholar.google.com/citations?user=acon_1UAAAAJ")
    assert "A1" in out and "Federico Rossi" in out                 # the resolution is shown
    who = tui.dispatch(app, "who A1")
    assert "Jet Propulsion Laboratory" in who                      # current affiliation, from Scholar


def test_add_paper_seed_still_falls_through(tmp_path):
    # a DOI must NOT be treated as a person — the existing paper path handles it.
    app = App(str(tmp_path), people_client=FakePC())
    out = tui.dispatch(app, "add 10.1/nonexistent")
    assert "couldn't add person" not in out          # did not route to add_person
