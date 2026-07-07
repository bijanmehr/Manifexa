"""The split TUI — pure helpers, and that the prompt_toolkit layout constructs.

The full-screen app can't run headless, but its command palette, command
processing, and the live graph sidebar are pure functions, and ``build()`` is
constructable without a terminal — so we verify the wiring even without a tty.
"""
import pytest

from manifexa import tui, tui_app
from manifexa.app import App


def _app(tmp_path):
    a = App(str(tmp_path))
    a.create("person", "Ada Lovelace")
    return a


def _state():
    return {"current": None, "recent": [], "engine": "networkx", "home": "~"}


def test_slash_palette_has_core_commands():
    cmds = [c for c, _ in tui_app.SLASH]
    for x in ("/help", "/graph", "/map", "/bridges", "/stats", "/quit"):
        assert x in cmds


def test_refresh_context_computes_counts_and_caches_layout(tmp_path, monkeypatch):
    monkeypatch.setenv("MANIFEXA_ENGINE", "networkx")
    a = _app(tmp_path)                        # 1 curated (Ada)
    state = {"current": None, "recent": []}
    tui_app._refresh_context(a, state)
    assert state["counts"]["curated"] == 1
    assert "mappos" in state and "mapnodes" in state           # the layout the sidebar animates from


# --- the live graph sidebar (the whole graph, drifting) ---
def _graph_state(tmp_path, monkeypatch):
    monkeypatch.setenv("MANIFEXA_ENGINE", "networkx")
    a = App(str(tmp_path))
    p = a.create("paper", "On Heat")
    t = a.create("topic", "Thermodynamics")
    a.link(p, t, "about")
    state = {"current": None, "recent": [], "vault": "v"}
    tui_app._refresh_context(a, state)
    return state


def test_graph_sidebar_draws_the_graph_with_named_nodes(tmp_path, monkeypatch):
    state = _graph_state(tmp_path, monkeypatch)
    txt = tui_app._graph_sidebar(state, tui.Style(False), width=44, height=24)
    assert "graph" in txt.lower()                              # the header
    assert "On Heat" in txt and "Thermodynamics" in txt        # nodes labelled by NAME, inline
    assert "nodes" in txt.lower() and "edges" in txt.lower()   # the count line


def test_graph_sidebar_is_static(tmp_path, monkeypatch):
    state = _graph_state(tmp_path, monkeypatch)
    st = tui.Style(False)                                      # no time arg → deterministic, no animation
    assert tui_app._graph_sidebar(state, st, 44, 24) == tui_app._graph_sidebar(state, st, 44, 24)


def test_graph_sidebar_empty_prompts_to_add(tmp_path, monkeypatch):
    monkeypatch.setenv("MANIFEXA_ENGINE", "networkx")
    state = {"vault": "v"}
    tui_app._refresh_context(App(str(tmp_path)), state)
    txt = tui_app._graph_sidebar(state, tui.Style(False), width=44, height=24)
    assert "add" in txt.lower()                                # guidance when there's nothing to draw


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


def test_map_command_prints_the_static_whole_graph(tmp_path, monkeypatch):
    monkeypatch.setenv("MANIFEXA_ENGINE", "networkx")
    a = App(str(tmp_path))
    p = a.create("paper", "On Heat")
    t = a.create("topic", "Thermodynamics")
    a.link(p, t, "about")
    transcript = []
    tui_app._process(a, "map", transcript, _state(), tui.Style(False))
    joined = "\n".join(transcript)
    assert "On Heat" in joined and "Thermodynamics" in joined   # the map lands in the transcript


def test_complete_covers_commands_ids_types_colours(tmp_path):
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
