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


# the `/` palette — the clean, people-first surface (command, one-line help)
SLASH = [
    ("/add", "add a person <id·orcid·scholar>"),
    ("/who", "a person's card <id>"),
    ("/expand", "flesh a coauthor stub <id>"),
    ("/near", "who they're connected to <id>"),
    ("/path", "the chain between two <a> <b>"),
    ("/bridges", "the people who connect groups"),
    ("/groups", "research groups, inferred"),
    ("/map", "the whole graph (ascii)"),
    ("/view", "open the graph in a browser"),
    ("/list", "everyone in the graph"),
    ("/save", "back up this folder"),
    ("/load", "restore from a backup <file>"),
    ("/drop", "remove someone <id>"),
    ("/color", "amber green teal cyan …"),
    ("/manual", "what this is + a diagram"),
    ("/help", "all commands"),
    ("/clear", "clear the transcript"),
    ("/quit", "exit"),
]
_COMPLETE_IDS = ("who", "open", "inspect", "near", "around", "graph", "similar", "promote",
                 "remove", "rm", "drop", "note", "path", "expand", "complete", "link", "connect")
_TYPES = tui.TYPES
# every verb that tab-completes — clean verbs first, demoted verbs kept so power
# users who type them still complete (they're just off the palette).
_CMDS = ("add", "who", "expand", "window", "near", "path", "bridges", "groups", "map", "view", "list",
         "save", "load", "drop", "color", "manual", "help", "about", "clear", "quit", "exit",
         "ls", "open", "inspect", "around", "clusters", "similar", "stats", "graph", "search",
         "new", "link", "promote", "remove", "note", "extract", "complete", "ask", "embed",
         "export", "import", "vault", "tree", "summary")


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


def _refresh_context(app, state):
    """Recompute the sidebar's data once per command: vault, counts by type."""
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
    groups: dict = {}
    for e in sorted(ents, key=lambda e: (e.title or e.id).lower()):
        groups.setdefault(e.type or "note", []).append({"id": e.id, "title": e.title or e.id.split("/")[-1]})
    state["files"] = groups


def _suggestions(state):
    """A few situational next commands for the sidebar, keyed off what's in the
    vault and what's open."""
    c = state.get("counts") or {}
    n, e = c.get("curated", 0), c.get("edges", 0)
    if n == 0:
        return ["add <doi>", 'add topic "…"', "extract"]
    if state.get("current"):
        return ["expand <id>", "around <id>", "link <a> <b>", "map"]
    if e == 0:
        return ["link <a> <b>", "add <doi>", "map"]
    return ["map", "bridges", "clusters", "stats"]


def _files_panel(state, st, art, width, height):
    """The right pane: the animated logo, then a file browser of the vault
    (entities grouped by type, open node highlighted), then situational
    suggestions. The graph itself is the `map` command."""
    a, dim = st.a, st.dim
    groups = state.get("files") or {}
    cur = state.get("current")
    L = [a(ln) for ln in art.splitlines()]
    L += ["", a("  M A N I F E X A"), "", a(f"  ▤ {state.get('vault', 'vault')}/")]
    if not groups:
        L += ["", dim("  empty vault —"), dim("  add <doi>"), dim('  add topic "…"')]
    else:
        order = [t for t in tui.TYPES if t in groups] + [t for t in groups if t not in tui.TYPES]
        for t in order:
            items = groups[t]
            L.append(f"  {tui.DOT.get(t, '·')} {a(t)}/ {dim(str(len(items)))}")
            for i, e in enumerate(items[:6]):
                branch = "└" if i == min(len(items), 6) - 1 else "├"
                name = tui._clip(e["title"], max(6, width - 6))
                L.append(f"   {dim(branch)} " + (a(name) if e["id"] == cur else name))
            if len(items) > 6:
                L.append(dim(f"     +{len(items) - 6}"))
    L += ["", dim("  ── suggested ──")]
    for s in _suggestions(state):
        L.append("  " + a("› " + s))
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
    if head in ("open", "cat", "inspect", "around", "graph", "similar") and len(parts) > 1:
        state["current"] = parts[1]
        if parts[1] not in state["recent"]:
            state["recent"].append(parts[1])
    return None


# commands that hit the network / LLM — run these off the event loop with a
# spinner so a multi-second fetch never freezes the shell.
_SLOW = {"add", "expand", "embed", "ask", "find", "complete", "similar", "import", "load"}


def _stage(body: str) -> str:
    """A short label for what a slow command is doing (shown beside the spinner)."""
    b = body.lower()
    if "scholar.google" in b:
        return "resolving Google Scholar → OpenAlex…"
    if b.startswith(("add", "expand")):
        return "fetching from OpenAlex…"
    if b.startswith(("ask", "find", "complete")):
        return "thinking…"
    if b.startswith("embed"):
        return "fetching embeddings…"
    if b.startswith(("import", "load")):
        return "loading…"
    return "working…"


async def _run_slow(app, text, transcript, state, st):
    """Run a slow command off the event loop with a live spinner. The dispatch
    runs in a worker thread; meanwhile we animate a braille spinner and keep the
    UI responsive — so the shell no longer freezes during a Scholar fetch."""
    import asyncio
    from prompt_toolkit.application import get_app

    ptapp = get_app()
    body = text[1:].strip() if text.startswith("/") else text
    transcript.append("")
    transcript.append(st.a("› ") + text)
    idx = len(transcript)
    frames = "⣾⣽⣻⢿⡿⣟⣯⣷"
    transcript.append(st.a(frames[0]) + st.dim(" " + _stage(body)))
    result: dict = {}

    def work():
        try:
            result["out"] = tui.dispatch(app, body, st)
        except Exception as e:                       # surface any failure as a line
            result["out"] = st.dim(f"error: {e}")

    fut = asyncio.get_event_loop().run_in_executor(None, work)
    i = 1
    while not fut.done():
        transcript[idx] = st.a(frames[i % len(frames)]) + st.dim(" " + _stage(body))
        ptapp.invalidate()
        i += 1
        await asyncio.sleep(0.09)
    await fut
    transcript[idx] = result.get("out", "") or ""
    _refresh_context(app, state)
    ptapp.invalidate()


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
        "counts": {},
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
        text = buff.text
        body = (text[1:] if text.startswith("/") else text).strip()
        head = body.split()[0].lower() if body.split() else ""
        if head in _SLOW:                              # off-thread + spinner, non-blocking
            try:
                get_app().create_background_task(_run_slow(app, text, transcript, state, st))
            except Exception:
                run_line(text)                         # fallback: synchronous
        else:
            run_line(text)
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
        # animated Möbius logo + a file browser of the vault (the graph is `map`).
        # Fixed tilt + a slow rock in B keeps it reading as a strip (a full spin
        # tumbles it edge-on into a blob), so the twist shows without a jump.
        size = get_app().output.get_size()
        w = max(18, int(size.columns * 0.22) - 2)
        art = tui.mobius_frame(0.7, 0.5, 11, min(w, 22), rstrip=False, roll=time.monotonic() * 0.7)
        return ANSI(_files_panel(state, st, art, w, max(10, size.rows - 1)))

    input_window = Window(BufferControl(buffer=input_buffer), height=1)
    left = HSplit([
        Window(FormattedTextControl(get_output), wrap_lines=True),
        Window(FormattedTextControl(get_status), height=1),
        VSplit([Window(FormattedTextControl(lambda: ANSI(st.a("› "))), width=2), input_window]),
    ], width=D(weight=4))
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
                       refresh_interval=0.08)                 # ~12 fps → the logo animates (graph stays static)


def run(app) -> None:
    """Launch the split TUI, or fall back to the plain REPL when it can't run."""
    if not available() or not sys.stdout.isatty():
        return tui.repl(app)
    try:
        build(app).run()
    except Exception as e:  # never crash the user out — degrade to the plain shell
        print(f"(split TUI unavailable: {e} — falling back to the plain shell)")
        tui.repl(app)
