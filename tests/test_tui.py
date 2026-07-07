"""The interactive terminal REPL — its pure render/dispatch layer.

``dispatch(app, line)`` runs one command against a real App and returns the text
to print (no colour by default), so the whole command surface is unit-tested
without any I/O. The ``repl()`` input loop is thin glue around this.
"""
from manifexa.app import App
from manifexa.tui import dispatch, hbar, _statusline, THEMES, load_config, save_config, _ph_key, _ring, mobius_frame


def _app(tmp_path):
    app = App(str(tmp_path))
    app.create("person", "Ada Lovelace")
    app.create("paper", "Analytical Engine")
    return app


def test_hbar_is_proportional():
    assert hbar(5, 10, 10) == "█████░░░░░"
    assert hbar(0, 10, 4) == "░░░░"
    assert hbar(10, 10, 4) == "████"


def test_ls_lists_curated(tmp_path):
    out = dispatch(_app(tmp_path), "ls")
    assert "ada-lovelace" in out
    assert "Analytical Engine" in out


def test_open_shows_entity_and_connections(tmp_path):
    out = dispatch(_app(tmp_path), "open person/ada-lovelace")
    assert "Ada Lovelace" in out
    assert "connections" in out


def test_stats_reports_node_count(tmp_path):
    out = dispatch(_app(tmp_path), "stats")
    assert "nodes" in out
    assert "2" in out


def test_graph_renders_focal_even_without_edges(tmp_path):
    out = dispatch(_app(tmp_path), "graph person/ada-lovelace")
    assert "Ada Lovelace" in out


def test_graph_no_arg_maps_the_whole_graph(tmp_path):
    app = App(str(tmp_path))
    p = app.create("paper", "On Heat")
    t = app.create("topic", "Thermodynamics")
    c = app.create("concept", "Entropy")
    app.link(p, t, "about")
    app.link(p, c, "about")
    out = dispatch(app, "graph")                       # no id → the whole-graph map
    for name in ("On Heat", "Thermodynamics", "Entropy"):
        assert name in out                             # every node labelled in the legend
    assert "nodes" in out.lower() and "edges" in out.lower()


def test_map_on_empty_graph_is_friendly(tmp_path):
    assert "empty" in dispatch(App(str(tmp_path)), "map").lower()


def test_help_lists_core_commands(tmp_path):
    out = dispatch(_app(tmp_path), "help")
    for c in ("open", "around", "bridges", "stats", "graph"):
        assert c in out


def test_unknown_command_is_reported(tmp_path):
    out = dispatch(_app(tmp_path), "florp")
    assert "unknown" in out.lower()


def test_slash_prefix_is_accepted(tmp_path):
    app = _app(tmp_path)
    assert dispatch(app, "/ls") == dispatch(app, "ls")


def test_add_type_creates_entity_by_hand(tmp_path):
    app = _app(tmp_path)
    out = dispatch(app, "add topic Dirichlet process (DP-GMM)")   # not a doi → create, don't 404
    assert "created" in out
    assert any(e.type == "topic" for e in app.list())


def test_looks_like_seed_detects_dois_and_ids():
    from manifexa.tui import _looks_like_seed
    for s in ("10.48550/arXiv.2604.03042", "https://doi.org/10.1/x", "doi:10.1/x", "W2741809807"):
        assert _looks_like_seed(s), s
    for s in ("Attention Is All You Need", "Dirichlet process (DP-GMM)", "particle swarm optimization"):
        assert not _looks_like_seed(s), s


def test_add_paper_with_doi_fetches_not_titles_with_the_doi(tmp_path, monkeypatch):
    """`add paper <doi>` must route to web enrichment — not create an entity
    literally titled with the DOI URL (the bug behind the malformed paper)."""
    monkeypatch.setenv("MANIFEXA_ENGINE", "networkx")

    class _RecordFail:
        def __init__(self):
            self.asked = []

        def get_work(self, x):
            self.asked.append(x)
            raise LookupError("offline")

    fake = _RecordFail()
    app = App(str(tmp_path), client=fake, crossref_client=_RecordFail())
    dispatch(app, "add paper https://doi.org/10.48550/arXiv.2604.03042")
    assert any("10.48550" in x for x in fake.asked)          # it tried to FETCH the doi
    assert app.list() == []                                  # …and created no doi-titled paper


def test_add_paper_with_real_title_still_creates_by_hand(tmp_path):
    app = App(str(tmp_path))
    out = dispatch(app, "add paper Attention Is All You Need")
    assert "created" in out
    assert "Attention Is All You Need" in [e.title for e in app.list()]


def test_remove_deletes_entity_and_rm_is_an_alias(tmp_path):
    app = _app(tmp_path)                       # person/ada-lovelace + paper/analytical-engine
    out = dispatch(app, "remove person/ada-lovelace")
    assert "person/ada-lovelace" not in {e.id for e in app.list()}
    assert "remov" in out.lower() or "delet" in out.lower()
    dispatch(app, "rm paper/analytical-engine")   # rm still works
    assert app.list() == []


def test_export_then_import_roundtrips(tmp_path):
    app = _app(tmp_path)                      # person/ada-lovelace + paper/analytical-engine
    dump = tmp_path / "dump.json"
    assert "exported" in dispatch(app, f"export {dump}")
    assert dump.exists()

    fresh = App(str(tmp_path / "fresh"))
    assert "imported" in dispatch(fresh, f"import {dump}")
    assert "person/ada-lovelace" in {e.id for e in fresh.list()}


def test_phosphor_config_roundtrips(tmp_path):
    save_config(tmp_path, phosphor="green")
    assert load_config(tmp_path)["phosphor"] == "green"


def test_ph_key_accepts_names_and_initials():
    assert _ph_key("green") == "green"
    assert _ph_key("g") == "green"
    assert _ph_key("cyan") == "cyan"
    assert _ph_key("nonsense") == "teal"


def test_themes_have_named_colours():
    for n in ("amber", "green", "teal", "cyan", "magenta", "white"):
        assert n in THEMES


def test_about_shows_banner_and_tagline(tmp_path):
    out = dispatch(_app(tmp_path), "about")
    assert "M A N I F E X A" in out
    assert "knowledge graph" in out.lower()


def test_manual_explains_system_with_diagram(tmp_path):
    out = dispatch(_app(tmp_path), "manual")
    assert "how it works" in out.lower()
    assert "vault" in out and "graph" in out            # the diagram is present
    for section in ("capture", "explore", "curate"):
        assert section in out.lower()
    assert dispatch(_app(tmp_path), "man") == out         # alias works


def test_ring_art_is_hollow_and_deterministic():
    art = _ring(11, 26)
    assert "·" in art and "•" in art                 # dotted
    lines = art.splitlines()
    assert "   " in lines[len(lines) // 2]           # hollow centre
    assert _ring(11, 26) == art                       # deterministic

    labelled = _ring(15, 42, label="M A N I F E X A")
    assert "M A N I F E X A" in labelled              # label nests inside


def test_mobius_frame_is_3d_fixed_size_and_deterministic():
    f = mobius_frame(0.7, 0.5, 13, 26)
    assert "●" in f or "•" in f                         # depth-shaded dots
    assert mobius_frame(0.7, 0.5, 13, 26) == f          # deterministic per angle
    assert mobius_frame(0.7, 1.6, 13, 26) != f          # rotation changes the frame
    fixed = mobius_frame(0.7, 0.5, 13, 26, rstrip=False)
    lines = fixed.splitlines()
    assert len(lines) == 13                             # fixed height → below lines never move
    assert all(len(ln) == 26 for ln in lines)          # fixed width


def test_statusline_shows_info_within_width(tmp_path):
    line = _statusline(_app(tmp_path), "~/.manifexa", "networkx", "teal", 100)
    assert "manifexa" in line
    assert "2 curated" in line
    assert "help" in line
    assert len(line) <= 100
