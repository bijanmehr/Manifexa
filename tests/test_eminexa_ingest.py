from manifexa.store.cache import Cache
from manifexa.eminexa.ingest import ingest_person


class FakePC:
    def get_author(self, aid):
        return {"id": "https://openalex.org/A1", "display_name": "Seed Person",
                "works_count": 5, "cited_by_count": 9, "summary_stats": {"h_index": 2}}

    def works_by_author(self, aid, from_date, cap=200):
        return [{"id": "https://openalex.org/W1", "title": "P", "doi": None, "publication_year": 2025,
                 "topics": [], "authorships": [
                    {"author": {"id": "https://openalex.org/A1", "display_name": "Seed Person"}},
                    {"author": {"id": "https://openalex.org/A2", "display_name": "Co Author"}}]}]


def test_ingest_writes_person_stub_and_edge():
    cache = Cache(":memory:")
    res = ingest_person(cache, FakePC(), "A1", today_year=2026, from_date="2021-01-01")
    assert res == {"person": "A1", "name": "Seed Person", "coauthors": 1, "edges": 1}
    person = cache.get_node("A1")
    assert person["type"] == "person" and person["meta"]["h_index"] == 2
    assert person["source"] == "eminexa"
    assert cache.get_node("A2")["meta"]["stub"] is True
    edges = cache.edges()
    assert any(e["src"] == "A1" and e["dst"] == "A2" and e["rel"] == "coauthored" and e["source"] == "eminexa"
               for e in edges)


SCHOLAR_HTML = """
<div id="gsc_prf_in">Federico Rossi</div>
<div class="gsc_prf_il">Robotics Technologist, Jet Propulsion Laboratory</div>
<div class="gsc_prf_il" id="gsc_prf_ivh">Verified email at stanford.edu</div>
<table id="gsc_a_t"><tbody>
  <tr class="gsc_a_tr"><td class="gsc_a_t"><a class="gsc_a_at">Model predictive control of mobility-on-demand</a>
    <div class="gs_gray">R Zhang, F Rossi</div><div class="gs_gray">ICRA 2016</div></td>
    <td class="gsc_a_c"><a class="gsc_a_ac gs_ibl">251</a></td>
    <td class="gsc_a_y"><span class="gsc_a_h gs_ibl">2016</span></td></tr>
  <tr class="gsc_a_tr"><td class="gsc_a_t"><a class="gsc_a_at">Routing autonomous vehicles in congested networks</a>
    <div class="gs_gray">F Rossi, M Pavone</div><div class="gs_gray">Auton. Robots 2018</div></td>
    <td class="gsc_a_c"><a class="gsc_a_ac gs_ibl">243</a></td>
    <td class="gsc_a_y"><span class="gsc_a_h gs_ibl">2018</span></td></tr>
</tbody></table>
"""


class ScholarPC:
    def search_works(self, q, per_page=1):
        return [{"authorships": [{"author": {"id": "https://openalex.org/A1", "display_name": "Federico Rossi"}}]}]

    def get_author(self, aid):
        return {"id": "https://openalex.org/A1", "display_name": "Federico Rossi",
                "works_count": 66, "cited_by_count": 855, "summary_stats": {"h_index": 13}}

    def works_by_author(self, aid, from_date, cap=200):
        return [{"id": "https://openalex.org/W1", "title": "P", "doi": None, "publication_year": 2025, "topics": [],
                 "authorships": [{"author": {"id": "https://openalex.org/A1", "display_name": "Federico Rossi"}},
                                 {"author": {"id": "https://openalex.org/A2", "display_name": "Marco Pavone"}}]}]


def test_ingest_scholar_url_resolves_and_attaches_current_snapshot():
    cache = Cache(":memory:")
    res = ingest_person(cache, ScholarPC(), "https://scholar.google.com/citations?user=acon_1UAAAAJ",
                        today_year=2026, from_date="2021-01-01", fetch=lambda url: SCHOLAR_HTML)
    assert res["person"] == "A1"
    assert res["scholar"]["name"] == "Federico Rossi"
    assert res["scholar"]["corroboration"] == 2            # both titles corroborate A1
    m = cache.get_node("A1")["meta"]
    assert "Jet Propulsion Laboratory" in m["current_affiliation"]   # leading-edge, from Scholar
    assert m["email_domain"] == "stanford.edu"
    assert m["scholar_url"].endswith("acon_1UAAAAJ")
    assert len(m["publications"]) == 2                               # captured from the profile
    assert m["publications"][0]["cites"] == 251


def test_ingest_does_not_clobber_existing_full_node_with_stub():
    cache = Cache(":memory:")
    # A2 already ingested as a full person...
    cache.upsert_node("A2", "person", "Co Author", {"h_index": 7, "stub": False}, source="eminexa")
    ingest_person(cache, FakePC(), "A1", today_year=2026, from_date="2021-01-01")
    a2 = cache.get_node("A2")
    assert a2["meta"].get("stub") is False and a2["meta"]["h_index"] == 7   # full node preserved
