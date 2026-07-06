"""The split TUI — pure helpers, and that the prompt_toolkit layout constructs.

The full-screen app can't run headless, but its command palette, suggestion
logic, and sidebar are pure functions, and ``build()`` is constructable without
a terminal — so we verify the layout wires up even though we can't drive it.
"""
import pytest

from manifexa import tui, tui_app
from manifexa.app import App


def _app(tmp_path):
    a = App(str(tmp_path))
    a.create("person", "Ada Lovelace")
    return a


def test_slash_palette_has_core_commands():
    cmds = [c for c, _ in tui_app.SLASH]
    for x in ("/help", "/graph", "/bridges", "/stats", "/quit"):
        assert x in cmds


def test_suggestions_for_empty_graph(tmp_path):
    s = tui_app.suggestions(App(str(tmp_path)), None)
    assert any("add" in cmd for cmd, _ in s)


def test_suggestions_key_off_current_entity(tmp_path):
    s = tui_app.suggestions(_app(tmp_path), "person/ada-lovelace")
    joined = " ".join(cmd for cmd, _ in s)
    assert "around person/ada-lovelace" in joined
    assert "graph person/ada-lovelace" in joined


def test_sidebar_shows_info_and_suggestions(tmp_path):
    txt = tui_app._sidebar_text(
        _app(tmp_path),
        {"current": "person/ada-lovelace", "recent": [], "engine": "networkx"},
        tui.ART, tui.Style(False),
    )
    assert "vault" in txt.lower()             # the vault browser section
    assert "do next" in txt.lower()           # suggestions
    assert "/help" in txt and "/color" in txt


def test_refresh_context_computes_counts(tmp_path):
    a = _app(tmp_path)                        # 1 curated (Ada)
    state = {"current": None, "recent": []}
    tui_app._refresh_context(a, state)
    assert state["counts"]["curated"] == 1
    assert "around" in state


def test_quit_aliases_all_signal_exit(tmp_path):
    app = _app(tmp_path)
    st = tui.Style(False)
    for word in ("exit", "quit", "q", "EXIT", "  exit  "):
        assert tui_app._process(app, word, [], {}, st) == "EXIT"


def test_color_is_an_alias_for_phosphor(tmp_path):
    app = _app(tmp_path)
    st = tui.Style(False)
    tui_app._process(app, "color green", [], {}, st)
    assert st.accent == tui.THEMES["green"]


def _state():
    return {"current": None, "recent": [], "engine": "networkx", "home": "~"}


def test_process_runs_a_command_and_mutates_the_vault(tmp_path):
    a = _app(tmp_path)
    tui_app._process(a, "new person Bob", [], _state(), tui.Style(False))
    assert any(e.id == "person/bob" for e in a.list())


def test_process_tracks_current_and_recent(tmp_path):
    state = _state()
    tui_app._process(_app(tmp_path), "open person/ada-lovelace", [], state, tui.Style(False))
    assert state["current"] == "person/ada-lovelace"
    assert "person/ada-lovelace" in state["recent"]


def test_process_slash_is_stripped_and_quit_exits(tmp_path):
    transcript = []
    r = tui_app._process(_app(tmp_path), "/quit", transcript, _state(), tui.Style(False))
    assert r == "EXIT"


def test_process_echoes_and_captures_output(tmp_path):
    transcript = []
    tui_app._process(_app(tmp_path), "/ls", transcript, _state(), tui.Style(False))
    joined = "\n".join(transcript)
    assert "› /ls" in joined          # the command is echoed
    assert "Ada Lovelace" in joined    # and its output captured


def test_complete_covers_commands_ids_types_colours(tmp_path):
    from manifexa.app import App

    app = App(str(tmp_path))
    app.create("person", "Ada Lovelace")

    def C(t):
        return [x[0] for x in tui_app._complete(app, t)]

    assert "vault" in C("va")                          # command names
    assert "person/ada-lovelace" in C("open ")         # all entity ids after a command
    assert "person/ada-lovelace" in C("around ada")    # ids match on slug / title substring
    assert "person" in C("new p") and "paper" in C("new p")   # entity types
    assert C("color gr") == ["green"]                  # colours
    assert "/graph" in C("/gr")                        # slash palette


def test_build_constructs_the_application(tmp_path):
    if not tui_app.available():
        pytest.skip("prompt_toolkit not installed")
    application = tui_app.build(_app(tmp_path))
    assert application is not None
    assert application.layout is not None


# --- the sidebar graph view (ego-net of the focused node) ---
def _ego():
    return {
        "focal": {"key": "paper/on-heat", "title": "On Heat", "type": "paper", "status": "curated"},
        "edges": [
            {"rel": "about", "node": {"key": "topic/thermodynamics", "title": "Thermodynamics", "type": "topic", "status": "curated"}},
            {"rel": "cites", "node": {"key": "paper/carnot", "title": "Carnot 1824", "type": "paper", "status": "candidate"}},
        ],
        "degree": 2, "auto": False,
    }


def test_ego_lines_shows_focal_and_its_edges():
    txt = "\n".join(tui_app._ego_lines(_ego(), tui.Style(False)))
    assert "On Heat" in txt                                   # the focal node
    assert "Thermodynamics" in txt and "about" in txt         # a neighbour + its relation
    assert "Carnot 1824" in txt and "cites" in txt


def test_ego_lines_empty_prompts_to_link():
    lines = tui_app._ego_lines(None, tui.Style(False))
    assert any("link" in ln.lower() for ln in lines)


def test_refresh_context_builds_ego_from_focus(tmp_path, monkeypatch):
    monkeypatch.setenv("MANIFEXA_ENGINE", "networkx")
    a = App(str(tmp_path))
    p = a.create("paper", "On Heat")
    t = a.create("topic", "Thermodynamics")
    a.link(p, t, "about")
    state = {"current": p, "recent": []}
    tui_app._refresh_context(a, state)
    ego = state["ego"]
    assert ego["focal"]["key"] == p
    assert any(e["node"]["key"] == t and e["rel"] == "about" for e in ego["edges"])


def test_refresh_context_ego_defaults_to_busiest_node(tmp_path, monkeypatch):
    monkeypatch.setenv("MANIFEXA_ENGINE", "networkx")
    a = App(str(tmp_path))
    p = a.create("paper", "Hub")
    t = a.create("topic", "T")
    c = a.create("concept", "C")
    a.link(p, t)
    a.link(p, c)                                              # Hub has 2 edges, the others 1
    state = {"current": None, "recent": []}
    tui_app._refresh_context(a, state)
    assert state["ego"]["focal"]["key"] == p                 # busiest node chosen automatically
    assert state["ego"]["auto"] is True


def test_sidebar_renders_the_graph_view(tmp_path, monkeypatch):
    monkeypatch.setenv("MANIFEXA_ENGINE", "networkx")
    a = App(str(tmp_path))
    p = a.create("paper", "On Heat")
    t = a.create("topic", "Thermodynamics")
    a.link(p, t, "about")
    state = {"current": p, "recent": [], "engine": "networkx", "home": "~"}
    tui_app._refresh_context(a, state)
    txt = tui_app._sidebar_text(a, state, tui.ART, tui.Style(False))
    assert "connections" in txt.lower()                      # the graph-view section header
    assert "Thermodynamics" in txt                           # the connected node shows in it
