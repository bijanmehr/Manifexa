import pytest

from manifexa.eminexa.scholar import (
    parse_scholar_id, is_scholar_url, parse_profile, _name_match, ScholarProfile,
    resolve_scholar, ScholarUnresolved,
)


class _AnchorPC:
    DB = {
        "paper a": [{"authorships": [
            {"author": {"id": "https://openalex.org/A1", "display_name": "Federico Rossi"}},
            {"author": {"id": "https://openalex.org/A9", "display_name": "Marco Pavone"}}]}],
        "paper b": [{"authorships": [{"author": {"id": "https://openalex.org/A1", "display_name": "Federico Rossi"}}]}],
        "paper c": [{"authorships": [{"author": {"id": "https://openalex.org/A1", "display_name": "F. Rossi"}}]}],
    }

    def search_works(self, query, per_page=1):
        return self.DB.get(query.lower(), [])


def test_resolve_scholar_anchors_by_corroboration():
    prof = ScholarProfile(name="Federico Rossi", titles=["Paper A", "Paper B", "Paper C"])
    r = resolve_scholar(_AnchorPC(), prof, min_corr=2)
    assert r["author_id"] == "A1" and r["corroboration"] == 3


def test_resolve_scholar_unresolved_when_below_threshold():
    prof = ScholarProfile(name="Federico Rossi", titles=["Paper A"])   # 1 corroboration < min 2
    with pytest.raises(ScholarUnresolved):
        resolve_scholar(_AnchorPC(), prof, min_corr=2)


def test_resolve_scholar_unresolved_when_no_name_match():
    prof = ScholarProfile(name="Someone Else", titles=["Paper A", "Paper B"])
    with pytest.raises(ScholarUnresolved):
        resolve_scholar(_AnchorPC(), prof)

# Minimal HTML mirroring a real Google Scholar profile's stable structure.
PROFILE_HTML = """
<div id="gsc_prf_i">
  <div id="gsc_prf_in">Geoffrey Hinton</div>
  <div class="gsc_prf_il">Emeritus Prof. Computer Science, <a class="gsc_prf_ila" href="#">University of Toronto</a></div>
  <div class="gsc_prf_il" id="gsc_prf_ivh">Verified email at cs.toronto.edu - <a href="#">Homepage</a></div>
</div>
<table id="gsc_a_t"><tbody>
  <tr class="gsc_a_tr"><td class="gsc_a_t"><a href="/x" class="gsc_a_at">ImageNet classification with deep convolutional neural networks</a></td></tr>
  <tr class="gsc_a_tr"><td class="gsc_a_t"><a href="/y" class="gsc_a_at">Deep learning &amp; representation</a></td></tr>
</tbody></table>
"""


def test_parse_scholar_id_from_url():
    assert parse_scholar_id("https://scholar.google.com/citations?user=JicYPdAAAAAJ&hl=en") == "JicYPdAAAAAJ"
    assert parse_scholar_id("https://scholar.google.com/citations?hl=en&user=WLN3QrAAAAAJ") == "WLN3QrAAAAAJ"
    assert parse_scholar_id("https://openalex.org/A123") is None


def test_is_scholar_url():
    assert is_scholar_url("https://scholar.google.com/citations?user=x")
    assert is_scholar_url("http://scholar.google.de/citations?user=x")
    assert not is_scholar_url("0000-0002-1243-7707")


PUB_HTML = """
<div id="gsc_prf_in">Federico Rossi</div>
<table id="gsc_a_t"><tbody>
  <tr class="gsc_a_tr"><td class="gsc_a_t">
    <a class="gsc_a_at" href="/x">Model predictive control of AMoD</a>
    <div class="gs_gray">R Zhang, F Rossi, M Pavone</div>
    <div class="gs_gray">ICRA 2016</div></td>
    <td class="gsc_a_c"><a class="gsc_a_ac gs_ibl" href="#">251</a></td>
    <td class="gsc_a_y"><span class="gsc_a_h gsc_a_hc gs_ibl">2016</span></td></tr>
  <tr class="gsc_a_tr"><td class="gsc_a_t">
    <a class="gsc_a_at" href="/y">Routing autonomous vehicles</a>
    <div class="gs_gray">F Rossi, R Zhang, M Pavone</div>
    <div class="gs_gray">Autonomous Robots 2018</div></td>
    <td class="gsc_a_c"><a class="gsc_a_ac gs_ibl" href="#"></a></td>
    <td class="gsc_a_y"><span class="gsc_a_h gsc_a_hc gs_ibl">2018</span></td></tr>
</tbody></table>
"""


def test_parse_publications():
    from manifexa.eminexa.scholar import parse_publications
    pubs = parse_publications(PUB_HTML)
    assert len(pubs) == 2
    p0 = pubs[0]
    assert p0["title"] == "Model predictive control of AMoD"
    assert p0["authors"] == "R Zhang, F Rossi, M Pavone"
    assert p0["venue"] == "ICRA 2016"
    assert p0["year"] == "2016"
    assert p0["cites"] == 251
    assert pubs[1]["cites"] == 0                       # no citation count → 0, not a crash


def test_parse_profile_includes_publications():
    p = parse_profile(PUB_HTML)
    assert len(p.publications) == 2
    assert p.publications[0]["title"] == "Model predictive control of AMoD"


def test_parse_profile_extracts_name_affiliation_email_titles():
    p = parse_profile(PROFILE_HTML)
    assert isinstance(p, ScholarProfile)
    assert p.name == "Geoffrey Hinton"
    assert p.affiliation == "Emeritus Prof. Computer Science, University of Toronto"
    assert p.email_domain == "cs.toronto.edu"
    assert p.titles == ["ImageNet classification with deep convolutional neural networks",
                        "Deep learning & representation"]          # HTML entity decoded


def test_name_match_surname_and_first_initial():
    assert _name_match("Geoffrey Hinton", "Geoffrey E. Hinton")
    assert _name_match("Geoffrey Hinton", "G. Hinton")
    assert _name_match("Amanda Prorok", "A. Prorok")
    assert not _name_match("Geoffrey Hinton", "Yann LeCun")
    assert not _name_match("Geoffrey Hinton", "Michael Hinton")     # different first initial? M != G
    assert not _name_match("", "Geoffrey Hinton")


def test_name_match_handles_nickname_and_accents():
    # a Scholar profile name can carry a parenthetical nickname + a compound surname
    assert _name_match("Felipe Leno da Silva (Leno)", "Felipe Leno da Silva")
    assert _name_match("Lukas Schäfer", "Lukas Schafer")            # accent-insensitive
