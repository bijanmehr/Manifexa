"""Full-screen split TUI (prompt_toolkit) — the tmux-style layout.

    ┌───────────────────────────────┬───────────────────┐
    │ transcript (scrolls)          │  manifexa         │
    │                               │  ── suggestions ──│
    │                               │  › around <id>    │
    │── status ────────────────────│  ── /commands ── │
    │ ›  input                      │  /help /graph …   │
    └───────────────────────────────┴───────────────────┘

Left pane: scrolling transcript + status bar + input, in an unequal (≈70/30)
vertical split with a live info/suggestions sidebar on the right. Typing ``/``
opens a command palette. Everything reuses ``tui.dispatch`` + its renderers, so
the command surface is identical to the plain shell. If prompt_toolkit isn't
installed (or there's no real terminal), ``run()`` falls back to ``tui.repl``.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from . import tui


def available() -> bool:
    try:
        import prompt_toolkit  # noqa: F401
        return True
    except Exception:
        return False


# the `/` palette — (command, one-line help)
SLASH = [
    ("/help", "all commands"),
    ("/about", "what is this"),
    ("/manual", "the manual page + diagram"),
    ("/vault", "show / switch vault folder"),
    ("/tree", "list the vault files"),
    ("/summary", "overview of the whole vault"),
    ("/ask", "LLM natural-language search"),
    ("/spin", "toggle 3D animation"),
    ("/ls", "list curated entities"),
    ("/around", "hidden connections <id>"),
    ("/graph", "ascii ego-net <id>"),
    ("/bridges", "connectors by betweenness"),
    ("/clusters", "emerging communities"),
    ("/similar", "semantic neighbours <id>"),
    ("/stats", "system status"),
    ("/add", "seed + enrich <doi>"),
    ("/new", "create <type> <title>"),
    ("/link", "connect two entities <a> <b>"),
    ("/embed", "fetch embeddings"),
    ("/export", "one-file db snapshot"),
    ("/import", "load a snapshot"),
    ("/color", "amber green teal cyan …"),
    ("/clear", "clear the transcript"),
    ("/quit", "exit"),
]
_COMPLETE_IDS = ("open", "around", "graph", "similar", "promote", "rm", "note", "path",
                 "expand", "complete", "link", "connect")
_TYPES = tui.TYPES
_CMDS = ("help", "manual", "ls", "open", "around", "path", "bridges", "clusters",
         "similar", "stats", "graph", "search", "add", "new", "link", "promote", "rm",
         "note", "extract", "expand", "complete", "ask", "embed", "export",
         "import", "vault", "tree", "summary", "color", "spin", "about", "clear", "quit", "exit")


def _complete(app, text):
    """Completion candidates for a partial line — commands, entity ids, entity
    types, colours — as (text, start_position, meta) tuples. Pure of
    prompt_toolkit, so it's unit-tested; the live UI adds filesystem paths."""
    if text.startswith("/"):
        return [(c, -len(text), d) for c, d in SLASH if c.startswith(text)]
    words = text.split()
    trailing = text.endswith(" ")
    argn = len(words) if trailing else max(0, len(words) - 1)
    frag = "" if (trailing or not words) else words[-1]
    if argn == 0:
        return [(c, -len(frag), "") for c in _CMDS if c.startswith(frag)]
    cmd = words[0].lower()
    if cmd in ("new", "add") and argn == 1:
        return [(t, -len(frag), "type") for t in _TYPES if t.startswith(frag)]
    if cmd in ("color", "phosphor") and argn == 1:
        return [(c, -len(frag), "colour") for c in tui.THEMES if c.startswith(frag)]
    if cmd in _COMPLETE_IDS:
        fl = frag.lower()
        return [(e.id, -len(frag), e.title or "") for e in app.list()
                if fl in e.id.lower() or fl in (e.title or "").lower()]
    return []


def suggestions(app, current):
    """A few context-aware next steps for the sidebar."""
    if not app.list():
        return [('new person "…"', "add your first entity"),
                ("add <doi>", "seed a paper from the web"),
                ("extract", "paste text → Claude")]
    out = []
    if current:
        out += [(f"around {current}", "hidden connections"),
                (f"graph {current}", "see its ego-net"),
                (f"expand {current}", "grow it with an LLM"),
                (f"similar {current}", "semantic neighbours")]
    out += [("bridges", "who connects your graph"),
            ("clusters", "emerging communities"),
            ("stats", "the big picture")]
    return out[:6]


def _clip(s, n):
    s = str(s)
    return s if len(s) <= n else s[: max(1, n - 1)] + "…"


def _ego_lines(ego, st, width=28):
    """Render the focal node + its direct edges as a compact connection tree —
    the sidebar's live 'what connects to what' graph view. Type-coloured node
    glyphs, dimmed relation labels, focal node in the accent colour. The graph is
    undirected: an edge shows whether the focal node is its source or target."""
    a, dim = st.a, st.dim
    if not ego or not ego.get("focal"):
        return ["  " + dim("no edges yet —"), "  " + dim("link two entities")]
    focal = ego["focal"]
    ftitle = (focal.get("title") or focal.get("key") or "").split("/")[-1]
    deg = ego.get("degree", len(ego.get("edges", [])))
    out = ["  " + tui._dotfor(focal) + " " + a(_clip(ftitle, width - 6)) + " " + dim("·" + str(deg))]
    edges = ego.get("edges", [])
    if not edges:
        out.append("     " + dim("(no direct links)"))
        return out
    shown = edges[:6]
    for i, ed in enumerate(shown):
        last = i == len(shown) - 1 and len(edges) <= 6
        node = ed.get("node") or {}
        ntitle = (node.get("title") or node.get("key") or "").split("/")[-1]
        rel = ed.get("rel") or ""
        out.append("   " + dim("└─" if last else "├─") + " " + tui._dotfor(node) + " "
                   + _clip(ntitle, width - 12) + " " + dim(_clip(rel, 6)))
    if len(edges) > 6:
        out.append("   " + dim(f"   +{len(edges) - 6} more"))
    return out


def _refresh_context(app, state):
    """Recompute the sidebar's live data — graph counts + the focused entity's
    hidden connections. Called once per command, never in the per-frame animation
    path, so the spinning art stays cheap."""
    d = app.export()
    nodes, edges = d.get("nodes", []), d.get("edges", [])
    ents = app.list()
    curated = len(ents)
    state["counts"] = {"curated": curated, "cand": max(0, len(nodes) - curated), "edges": len(edges)}
    state["vault"] = app.home.name or "vault"
    state["home"] = str(app.home).replace(str(Path.home()), "~")
    state["engine"] = type(app.engine).__name__.replace("Engine", "").lower()
    by = {}
    for e in ents:
        by[e.type or "note"] = by.get(e.type or "note", 0) + 1
    state["by_type"] = by
    focus = state.get("current")
    try:
        state["around"] = app.around(focus)[:4] if focus else []
    except Exception:
        state["around"] = []

    # ego-net for the sidebar graph view — the focal node's direct edges, built
    # from the export we already fetched (no extra engine calls in the render
    # path). No focus → default to the busiest node so there's always a picture.
    node_by = {n["key"]: n for n in nodes}
    deg: dict = {}
    for e in edges:
        deg[e["src"]] = deg.get(e["src"], 0) + 1
        deg[e["dst"]] = deg.get(e["dst"], 0) + 1
    focal_key = focus if (focus and focus in node_by) else (max(deg, key=deg.get) if deg else None)
    ego = None
    if focal_key and focal_key in node_by:
        nbrs = []
        for e in edges:
            other = e["dst"] if e["src"] == focal_key else (e["src"] if e["dst"] == focal_key else None)
            if other is not None:
                nbrs.append({"rel": e.get("rel", ""), "node": node_by.get(other, {"key": other})})
        ego = {"focal": node_by[focal_key], "edges": nbrs,
               "degree": deg.get(focal_key, 0), "auto": not (focus and focus in node_by)}
    state["ego"] = ego


def _sidebar_text(app, state, art, st) -> str:
    """The right pane: a live context + discovery surface. Compact art header,
    then the current focus + graph size, the focused entity's hidden connections
    (surfaced automatically), what to do next, then recent — reference last."""
    a, dim = st.a, st.dim
    focus = state.get("current")
    counts = state.get("counts") or {}
    short = (focus.split("/")[-1] if focus else "")

    L = [a(ln) for ln in art.splitlines()]
    L += ["", a("  M A N I F E X A"), ""]

    L.append(dim(f"  ▤ vault · {state.get('vault', '')}"))
    L.append(dim("  " + state.get("home", "")))
    by = state.get("by_type") or {}
    mx = max(by.values()) if by else 1
    for t in [x for x in tui.TYPES if by.get(x)] + [x for x in by if x not in tui.TYPES]:
        L.append("  " + tui.DOT.get(t, "·") + " " + tui._pad(t, 7) + " " + a(tui.hbar(by[t], mx, 8)) + " " + str(by[t]))
    L.append("  " + dim(f"{counts.get('curated', 0)} curated · {counts.get('edges', 0)} edges · {state.get('engine', '')}"))

    # graph view — direct connections of the focus (or the busiest node)
    ego = state.get("ego")
    L.append("")
    if ego and ego.get("auto"):
        L.append(dim("  ── connections · busiest ──"))
    else:
        L.append(dim(f"  ── connections · {short} ──" if short else "  ── connections ──"))
    L += _ego_lines(ego, st)

    # hidden links — one hop further out (shared neighbours, not yet connected)
    L.append("")
    L.append(dim(f"  ── hidden · {short} ──" if focus else "  ── hidden links ──"))
    around = state.get("around") or []
    if not focus:
        L += ["  " + dim("open an entity to see"), "  " + dim("what it sits near")]
    elif not around:
        L += ["  " + dim("none yet — enrich or"), "  " + dim("expand this node")]
    else:
        for r in around[:3]:
            title = (r.get("title") or r["key"]).split("/")[-1][:13]
            L.append("  ▸ " + a(title) + " " + dim((r.get("reason") or "")[:8]))

    L.append("")
    L.append(dim("  ── do next ──"))
    for cmd, _desc in suggestions(app, focus)[:4]:
        L.append("  " + a("› " + cmd))

    if state.get("recent"):
        L.append("")
        L.append(dim("  ── recent ──"))
        L.append("  " + dim(" · ".join(r.split("/")[-1] for r in state["recent"][-3:])))

    L += ["", dim("  /help · /manual · /color · /spin")]
    return "\n".join(L)


def _process(app, text, transcript, state, st):
    """Handle one input line: append output to ``transcript``, update ``state``.
    Pure of the event loop (returns ``"EXIT"`` for quit), so it's unit-testable."""
    text = text.strip()
    if not text:
        return None
    transcript.append("")
    transcript.append(st.a("› ") + text)
    body = text[1:].strip() if text.startswith("/") else text
    parts = body.split()
    head = parts[0].lower() if parts else ""
    if head in ("quit", "exit", "q"):
        return "EXIT"
    if head == "clear":
        transcript.clear()
        return None
    if head in ("spin", "still", "animate"):
        state["animate"] = head != "still"
        transcript.append(st.dim("animation " + ("on — Möbius spinning →" if state["animate"] else "off")))
        return None
    if head in ("phosphor", "color", "colour"):
        key = tui._ph_key(parts[1] if len(parts) > 1 else "")
        st.accent = tui.THEMES[key]
        tui.save_config(app.home, phosphor=key)
        transcript.append(st.dim("phosphor → " + key + " (saved)"))
        return None
    if head == "note":
        if len(parts) >= 3:
            try:
                app.set_note(parts[1], " ".join(parts[2:]))
                transcript.append(st.dim("notes saved → file"))
            except Exception as e:
                transcript.append(st.dim(f"error: {e}"))
        else:
            transcript.append(st.dim("split view: note <id> <text…>  ·  multi-line lives in  manifexa shell --plain"))
        return None
    if head == "extract":
        transcript.append(st.dim("multi-line extract lives in the plain shell:  manifexa shell --plain"))
        return None
    try:
        transcript.append(tui.dispatch(app, body, st))
    except Exception as e:
        transcript.append(st.dim(f"error: {e}"))
    if head in ("open", "cat", "around", "graph", "similar") and len(parts) > 1:
        state["current"] = parts[1]
        if parts[1] not in state["recent"]:
            state["recent"].append(parts[1])
    return None


def build(app):
    """Construct (but don't run) the prompt_toolkit Application. Importable and
    unit-constructable so the layout is verified even without a live terminal."""
    from prompt_toolkit.application import Application, get_app
    from prompt_toolkit.buffer import Buffer
    from prompt_toolkit.completion import Completer, Completion, PathCompleter
    from prompt_toolkit.document import Document
    from prompt_toolkit.formatted_text import ANSI
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout.containers import Float, FloatContainer, HSplit, VSplit, Window
    from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
    from prompt_toolkit.layout.dimension import Dimension as D
    from prompt_toolkit.layout.layout import Layout
    from prompt_toolkit.layout.menus import CompletionsMenu

    cfg = tui.load_config(app.home)
    st = tui.Style(enabled=True, accent=tui.THEMES.get(cfg.get("phosphor", ""), tui.THEMES["teal"]))
    state = {
        "current": None,
        "recent": [],
        "animate": True,
        "counts": {},
        "around": [],
        "engine": type(app.engine).__name__.replace("Engine", "").lower(),
        "home": str(app.home).replace(str(Path.home()), "~"),
    }
    _refresh_context(app, state)
    transcript: list[str] = [
        st.dim("type a command, or  /  for the palette · Ctrl-D to quit   info → "),
        st.dim(f"{len(app.list())} curated") if app.list()
        else st.dim('empty — try  new person "Ada Lovelace"'),
    ]

    def run_line(text):
        if _process(app, text, transcript, state, st) == "EXIT":
            get_app().exit()
        else:
            _refresh_context(app, state)   # refresh live context once per command

    def on_accept(buff):
        run_line(buff.text)
        return False  # clear the input

    _dirs = PathCompleter(only_directories=True, expanduser=True)   # for `vault <path>`
    _paths = PathCompleter(expanduser=True)                          # for import / export

    class Palette(Completer):
        def get_completions(self, document, complete_event):
            text = document.text_before_cursor
            words = text.split()
            cmd = words[0].lower() if words else ""
            trailing = text.endswith(" ")
            argn = len(words) if trailing else max(0, len(words) - 1)
            if cmd in ("vault", "import", "export") and argn >= 1:      # filesystem paths
                arg = text[len(words[0]):].lstrip()
                fs = _dirs if cmd == "vault" else _paths
                yield from fs.get_completions(Document(arg, len(arg)), complete_event)
                return
            for txt, start, meta in _complete(app, text):
                yield Completion(txt, start_position=start, display=txt, display_meta=meta)

    input_buffer = Buffer(completer=Palette(), complete_while_typing=True,
                          multiline=False, accept_handler=on_accept)

    def get_output():
        rows = get_app().output.get_size().rows
        avail = max(1, rows - 3)
        return ANSI("\n".join(transcript[-avail:]))

    def get_status():
        phos = {v: k for k, v in tui.THEMES.items()}.get(st.accent, "teal")
        return ANSI(st.dim(f"── manifexa · {len(app.list())} curated · {state['home']} · {state['engine']}/{phos} " + "─" * 400))

    def get_sidebar():
        # compact fixed 9x26 header (rstrip=False) → the block never changes size,
        # so the live context/discovery below it stays put while the art spins.
        B = time.monotonic() * 0.8 if state.get("animate") else 1.2
        art = tui.mobius_frame(0.7, B, 9, 26, rstrip=False)
        return ANSI(_sidebar_text(app, state, art, st))

    input_window = Window(BufferControl(buffer=input_buffer), height=1)
    left = HSplit([
        Window(FormattedTextControl(get_output), wrap_lines=True),
        Window(FormattedTextControl(get_status), height=1),
        VSplit([Window(FormattedTextControl(lambda: ANSI(st.a("› "))), width=2), input_window]),
    ], width=D(weight=2))
    right = Window(FormattedTextControl(get_sidebar), wrap_lines=False, width=D(weight=1))
    body = VSplit([left, Window(width=1, char="│"), right])
    root = FloatContainer(content=body,
                          floats=[Float(xcursor=True, ycursor=True,
                                        content=CompletionsMenu(max_height=10, scroll_offset=1))])

    kb = KeyBindings()

    @kb.add("c-d")
    @kb.add("c-c")
    def _(event):
        event.app.exit()

    return Application(layout=Layout(root, focused_element=input_window),
                       key_bindings=kb, full_screen=True, mouse_support=False,
                       refresh_interval=0.12)                 # ~8 fps → the sidebar torus animates


def run(app) -> None:
    """Launch the split TUI, or fall back to the plain REPL when it can't run."""
    if not available() or not sys.stdout.isatty():
        return tui.repl(app)
    try:
        build(app).run()
    except Exception as e:  # never crash the user out — degrade to the plain shell
        print(f"(split TUI unavailable: {e} — falling back to the plain shell)")
        tui.repl(app)
