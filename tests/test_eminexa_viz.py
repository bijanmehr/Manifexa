import re

from manifexa.viz import graph_to_html


DATA = {
    "nodes": [
        {"key": "A1", "type": "person", "title": "Ada P", "status": "candidate",
         "topics": ["Swarms"], "aff": "Cambridge", "h": 31},
        {"key": "A2", "type": "person", "title": "Bo Q", "status": "candidate"},
    ],
    "edges": [{"src": "A1", "dst": "A2", "rel": "coauthored"}],
}


def test_graph_to_html_is_a_full_selfcontained_document():
    html = graph_to_html(DATA, title="Eminexa test")
    assert html.lstrip().lower().startswith("<!doctype html")
    assert "Eminexa test" in html
    assert "http" not in html.split("<script")[0] or "://" not in html  # no external stylesheet/script host
    assert "cdn" not in html.lower() and "d3js.org" not in html         # self-contained, no CDN


def test_graph_to_html_embeds_nodes_and_edges():
    html = graph_to_html(DATA)
    assert "Ada P" in html and "Bo Q" in html            # names embedded
    assert "coauthored" in html                          # edge rel embedded
    assert "Swarms" in html and "Cambridge" in html      # enriched tooltip fields


def test_graph_to_html_escapes_script_break_out():
    evil = {"nodes": [{"key": "X", "type": "person", "title": "a</script><b>", "status": "candidate"}], "edges": []}
    html = graph_to_html(evil)
    assert "</script><b>" not in html                    # the data cannot close the script tag
    assert "<\\/script>" in html or "<\\u002fscript>" in html.lower() or "u002f" in html.lower()


def test_graph_to_html_empty_is_friendly():
    html = graph_to_html({"nodes": [], "edges": []})
    assert html.lstrip().lower().startswith("<!doctype html")
    assert "empty" in html.lower() or "no nodes" in html.lower() or "nobody" in html.lower()


def test_html_has_control_panel_and_audit_table():
    html = graph_to_html(DATA)
    assert 'id="ctrl"' in html                       # a control panel
    assert "coauthor" in html.lower()                # segregation vocabulary
    assert 'id="table"' in html or "audit" in html.lower()   # an audit table


def test_inspector_renders_all_node_fields():
    data = {"nodes": [{"key": "A1", "type": "person", "title": "Ada", "status": "candidate", "role": "seed",
                       "fields": [["ORCID", "0000-0002-0001"], ["h-index", "31"], ["now", "Cambridge"]]}],
            "edges": []}
    html = graph_to_html(data)
    for tok in ("ORCID", "0000-0002-0001", "h-index", "31", "Cambridge"):
        assert tok in html                            # every field travels into the page

def test_seed_and_coauthor_have_distinct_fill_colors():
    html = graph_to_html(DATA)
    seed = re.search(r"--seed:\s*([^;]+)", html).group(1).strip()
    co = re.search(r"--co:\s*([^;]+)", html).group(1).strip()
    assert seed != co                                    # different hues, not just filled vs hollow
    # coauthor circles are FILLED with the coauthor colour (visible), not dark/hollow
    assert re.search(r"\.node\.role-coauthor circle\s*\{[^}]*fill:\s*var\(--co\)", html)
    assert re.search(r"\.node\.role-seed circle\s*\{[^}]*fill:\s*var\(--seed\)", html)


def test_role_travels_into_embedded_data():
    data = {"nodes": [{"key": "A1", "title": "Seed", "role": "seed", "type": "person", "status": "candidate"},
                      {"key": "A2", "title": "Co", "role": "coauthor", "type": "person", "status": "candidate"}],
            "edges": [{"src": "A1", "dst": "A2", "rel": "coauthored"}]}
    html = graph_to_html(data)
    assert '"role"' in html and "coauthor" in html    # role drives the visual segregation
