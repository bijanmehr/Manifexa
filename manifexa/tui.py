"""Interactive terminal REPL — Manifexa in your actual terminal.

Runs the App in-process (no browser, no server): reads a command line, renders
the result — including ASCII viz (bar charts, an ego-net, a status board) —
straight to stdout with optional ANSI colour. The pure render/``dispatch`` layer
is unit-tested; ``repl()`` is only the input loop around it.
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import sys
import time
from pathlib import Path

DOT = {"person": "●", "paper": "◆", "lab": "▣", "book": "❒",
       "note": "✎", "concept": "✦", "topic": "⬡"}
TYPES = ("person", "paper", "lab", "book", "note", "concept", "topic")
THEMES = {"amber": "214", "green": "78", "teal": "43", "cyan": "51",
          "magenta": "201", "white": "255", "blue": "39"}

TAGLINE = "a personal research knowledge graph — it surfaces the connections you'd never think to search for"
def _ring(rows, cols, inner=0.50, step=0.09, spokes=None, label=None):
    """A generative dotted ring (dailyminimal style): dots plotted around
    concentric spokes with a gently ragged edge, a hollow centre, and an
    optional centred label. Deterministic — same size in, same art out."""
    if spokes is None:
        spokes = int(cols * 1.7)
    g = [[" "] * cols for _ in range(rows)]
    cx, cy = (cols - 1) / 2.0, (rows - 1) / 2.0
    for s in range(spokes):
        ang = 2 * math.pi * s / spokes
        outer = 0.82 + 0.18 * (((s * 13) % 7) / 6.0)
        rad = inner
        while rad <= outer:
            x = cx + math.cos(ang) * rad * (cols / 2 - 1)
            y = cy + math.sin(ang) * rad * (rows / 2 - 1)
            xi, yi = int(round(x)), int(round(y))
            if 0 <= yi < rows and 0 <= xi < cols and g[yi][xi] == " ":
                g[yi][xi] = "•" if rad > 0.74 else "·"
            rad += step
    if label:
        row = rows // 2
        start = max(0, (cols - len(label)) // 2)
        for i, ch in enumerate(label):
            if start + i < cols:
                g[row][start + i] = ch
    return "\n".join("".join(r).rstrip() for r in g)


ART = _ring(11, 26)
BANNER = _ring(15, 42, label="M A N I F E X A")


def mobius_frame(A, B, rows=13, cols=26, chars=" ·•●", rstrip=True):
    """One frame of a rotating 3-D Möbius strip (an infinity band) rendered in
    dots, depth-shaded near→far. Pure + deterministic in (A, B). With
    ``rstrip=False`` every frame is exactly rows×cols — a fixed animation frame
    that never reflows whatever is drawn below it."""
    R, K2 = 2.0, 5.0
    K1 = cols * K2 * 3 / (8 * (R + 1))
    out = [[" "] * cols for _ in range(rows)]
    zb = [[0.0] * cols for _ in range(rows)]
    cA, sA, cB, sB = math.cos(A), math.sin(A), math.cos(B), math.sin(B)
    oozmin, oozmax = 1.0 / (K2 + 3), 1.0 / (K2 - 3)
    u = 0.0
    while u < 2 * math.pi:
        cu, su, c2, s2 = math.cos(u), math.sin(u), math.cos(u / 2), math.sin(u / 2)
        v = -0.9
        while v <= 0.9:
            rr = R + v * c2
            px, py, pz = rr * cu, rr * su, v * s2
            y1, z1 = py * cA - pz * sA, py * sA + pz * cA          # rotate X by A
            x2, z2 = px * cB + z1 * sB, -px * sB + z1 * cB         # rotate Y by B
            ooz = 1.0 / (z2 + K2)
            xp = int(cols / 2 + K1 * ooz * x2)
            yp = int(rows / 2 - (K1 / 2) * ooz * y1)
            if 0 <= xp < cols and 0 <= yp < rows and ooz > zb[yp][xp]:
                zb[yp][xp] = ooz
                lum = (ooz - oozmin) / (oozmax - oozmin)
                out[yp][xp] = chars[max(1, min(len(chars) - 1, int(lum * len(chars))))]
            v += 0.04
        u += 0.03
    return "\n".join(("".join(r).rstrip() if rstrip else "".join(r)) for r in out)


def _spin(rows=15, cols=42, seconds=2.4, fps=14):
    """Play the spinning Möbius in place (skipped when there's no real terminal)."""
    if not sys.stdout.isatty():
        return
    cols = min(cols, shutil.get_terminal_size((80, 24)).columns - 1)
    w = sys.stdout.write
    w("\033[2J\033[?25l")                 # clear + hide cursor
    try:
        for i in range(int(seconds * fps)):
            w("\033[H" + mobius_frame(0.7, i * 0.09, rows, cols, rstrip=False) + "\033[0J")
            sys.stdout.flush()
            time.sleep(1.0 / fps)
    except KeyboardInterrupt:
        pass
    finally:
        w("\033[?25h\033[2J\033[H")       # restore cursor + clear
        sys.stdout.flush()


def _ph_key(s):
    """Resolve a colour name or initial to a THEMES key (falls back to teal)."""
    s = (s or "").lower()
    if s in THEMES:
        return s
    return {"a": "amber", "g": "green", "t": "teal", "c": "cyan",
            "m": "magenta", "w": "white", "b": "blue"}.get(s[:1], "teal")


def _config_path(home):
    return Path(home) / "config.json"


def load_config(home) -> dict:
    try:
        return json.loads(_config_path(home).read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(home, **kw) -> None:
    cfg = load_config(home)
    cfg.update(kw)
    _config_path(home).write_text(json.dumps(cfg, indent=2), encoding="utf-8")


class Style:
    """Tiny ANSI styler. Disabled → returns text unchanged (the default, so the
    render layer is plain-text testable)."""

    def __init__(self, enabled: bool = False, accent: str = "43") -> None:
        self.on = enabled
        self.accent = accent

    def _c(self, s, code):
        return f"\033[38;5;{code}m{s}\033[0m" if self.on else str(s)

    def a(self, s):      # accent (the phosphor colour)
        return self._c(s, self.accent)

    def dim(self, s):
        return self._c(s, "244")

    def bold(self, s):
        return f"\033[1m{s}\033[0m" if self.on else str(s)


def hbar(v, mx, w: int = 20) -> str:
    n = 0 if not mx else max(0, min(w, round(v / mx * w)))
    return "█" * n + "░" * (w - n)


def _pad(s, w: int) -> str:
    s = str(s)
    return s[:w] if len(s) >= w else s + " " * (w - len(s))


def _dotfor(node) -> str:
    if not node:
        return "·"
    if node.get("status") == "candidate":
        return "○"
    return DOT.get(node.get("type"), "●")


# A DOI, DOI/arXiv URL, or OpenAlex work id — something to FETCH from the web,
# not a hand-typed title. Lets `add paper <doi>` enrich instead of titling an
# entity with the DOI.
_SEED_RE = re.compile(r"^(?:https?://\S+|doi:10\.\d+/\S+|10\.\d+/\S+|W\d+|openalex:\S+)$", re.I)


def _looks_like_seed(s: str) -> bool:
    return bool(_SEED_RE.match((s or "").strip()))


def _statusline(app, home, engine, phosphor, width) -> str:
    """The Claude-Code-style separator/status bar shown above the prompt —
    info on the left, navigation hints on the right, ─ filling the gap."""
    left = f"── manifexa · {len(app.list())} curated · {home} · {engine}/{phosphor} "
    right = " help · ls · open · around · graph · quit ──"
    if len(left) + len(right) + 2 > width:      # narrow terminal: drop hints, don't cut mid-word
        return (left + "─" * max(2, width - len(left)))[:width]
    return left + "─" * (width - len(left) - len(right)) + right


HELP = """COMMANDS
  ls                     list your curated entities
  open <id>              inspect an entity: fields + connections (alias: inspect)
  around <id>            surface hidden connections
  path <a> <b>           the chain between two entities
  bridges                connectors, ranked by betweenness
  clusters               emerging communities
  similar <id>           semantic neighbours (needs: embed)
  stats                  system status dashboard
  graph [id]             one node's ego-net · no id → whole map
  search <term>          filter your graph
  map                    whole-graph map — every node + connection
  add <type> <title>     create an entity by hand (same as: new)
  add <doi|openalex>     …or seed a paper + enrich from the web
  new <type> <title>     create an entity by hand
  link <a> <b> [rel]     connect two entities (a —rel→ b)
  promote <id>           candidate -> curated
  remove <id>            delete an entity (alias: rm)
  note <id>              edit notes (multi-line)
  extract                paste text -> Claude pulls entities
  expand <id>            LLM: propose new related entities (candidates)
  complete <id>          LLM: infer likely missing links (candidates)
  ask <question>         LLM: natural-language search of your graph
  embed                  fetch embeddings (Semantic Scholar)
  export [path]          one-file snapshot of the whole database
  import <path>          load a snapshot back in
  vault [path]           show / switch the vault folder
  tree                   list the vault's files
  summary                overview of the whole vault (counts · tree · graph)
  color / phosphor <c>   amber green teal cyan magenta white blue (persists)
  manual                 what this is + a diagram of the system
  spin · about · clear · help · quit / exit"""


_DIAGRAM = (
    "      seed          enrich         surface        promote\n"
    "   ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐\n"
    "   │  vault  │──▶│  cache  │──▶│  graph  │──▶│   you   │\n"
    "   │  ·md    │   │ SQLite  │   │ engine  │   │ insight │\n"
    "   │ =truth  │   │candidate│   │queryable│   │ (pull)  │\n"
    "   └─────────┘   └─────────┘   └─────────┘   └─────────┘\n"
    "     you own      derived       ArcadeDB    around·path…"
)

_MANUAL_SECTIONS = (
    ("capture", (
        ("new <type> <title>", "create an entity by hand"),
        ("add <type> <title>", "create by hand (like new) — or a doi to enrich"),
        ("add <doi|openalex>", "seed a paper + enrich from the web"),
        ("extract", "paste text → Claude pulls entities & links"),
        ("import / export [file]", "load / save the whole database as one file"),
    )),
    ("explore  (pull)", (
        ("ls · open <id>", "list · show an entity + connections"),
        ("around <id>", "hidden connections near an entity"),
        ("path <a> <b>", "the chain linking two entities"),
        ("bridges · clusters", "connectors · emerging communities"),
        ("similar <id>", "semantic neighbours (needs: embed)"),
        ("map · graph <id>", "whole-graph map · one node's ego-net"),
        ("stats · search", "dashboard · filter"),
        ("summary · tree", "overview of everything · file tree"),
    )),
    ("curate", (
        ("link <a> <b> [rel]", "connect two entities by hand (a [[wikilink]] b)"),
        ("promote <id>", "candidate → curated (into your vault)"),
        ("note <id> · remove <id>", "edit notes · delete an entity"),
        ("embed", "fetch embeddings for semantic search"),
    )),
    ("ai · llm (claude or local)", (
        ("expand <id>", "propose new related entities & edges"),
        ("complete <id>", "infer likely missing links"),
        ("ask <question>", "natural-language search of your graph"),
    )),
    ("the terminal", (
        ("vault [path] · tree", "show / switch folder · list its files"),
        ("color <name>", "amber green teal cyan magenta white blue"),
        ("spin · about · manual", "animation · banner · this page"),
        ("clear · help · quit/exit", ""),
    )),
)


def render_manual(st) -> str:
    """The in-app manual page: what the system is, a diagram of the data flow,
    and the commands grouped by purpose."""
    a, dim = st.a, st.dim

    def hdr(t):
        return dim("  ── " + t + " " + "─" * max(2, 52 - len(t)))

    L = [a("  MANIFEXA · manual"),
         dim("  a personal research knowledge graph — you seed it by hand,"),
         dim("  automation grows it, and it surfaces the connections you'd"),
         dim("  never think to search for."), "",
         hdr("how it works")]
    L += [a(ln) for ln in _DIAGRAM.splitlines()]
    L += ["", dim("  your notes are the source of truth (Markdown you own);"),
          dim("  everything else is derived, rebuilt on every change."), ""]
    for title, rows in _MANUAL_SECTIONS:
        L.append(hdr(title))
        for cmd, desc in rows:
            L.append("  " + a(cmd.ljust(28)) + " " + dim(desc))
        L.append("")
    L.append(dim("  data: ~/.manifexa/   ·   engine: arcadedb (embedded · no server)"))
    L.append(dim("  llm:  MANIFEXA_LLM=claude|ollama   ·   its output is always candidates"))
    return "\n".join(L)


def _by_type(ents):
    by = {}
    for e in ents:
        by[e.type or "note"] = by.get(e.type or "note", 0) + 1
    return by


_ORDER = list(TYPES)


def render_vault(app, st) -> str:
    """The `vault` view — a little folder glyph + counts per type as bars."""
    a, dim = st.a, st.dim
    name = app.home.name or "vault"
    path = str(app.home).replace(str(Path.home()), "~")
    ents = app.list()
    by = _by_type(ents)
    mx = max(by.values()) if by else 1
    L = [a("     ______"),
         a("    |      |___"),
         a("    | ▤        |  " + name),
         a("    |__________|"),
         "", dim("  " + path), ""]
    for t in _ORDER + [x for x in by if x not in _ORDER]:
        if by.get(t):
            L.append(f"  {DOT.get(t, '·')} {_pad(t, 8)} {a(hbar(by[t], mx, 14))} {by[t]}")
    if not by:
        L.append(dim("  (empty — create with  new <type> <title>  or  add <doi>)"))
    L.append("")
    L.append(dim(f"  {len(ents)} entities · {len(by)} types · engine {type(app.engine).__name__.replace('Engine','').lower()}"))
    return "\n".join(L)


def render_tree(app, st) -> str:
    """The `tree` view — the vault's files as an ASCII tree, grouped by type."""
    a, dim = st.a, st.dim
    name = app.home.name or "vault"
    groups = {}
    for e in sorted(app.list(), key=lambda e: e.id):
        groups.setdefault(e.type or "note", []).append(e)
    L = [a(f"  ▤ {name}/"), dim("  " + str(app.home).replace(str(Path.home()), "~")), ""]
    for t, items in groups.items():
        L.append(f"  {DOT.get(t, '·')} {a(t)}/")
        for i, e in enumerate(items):
            branch = "└─" if i == len(items) - 1 else "├─"
            L.append(f"     {dim(branch)} {e.title or e.id}  {dim('· ' + e.id.split('/')[-1] + '.md')}")
    if not groups:
        L.append(dim("  (empty)"))
    L.append("")
    L.append(dim(f"  {sum(len(v) for v in groups.values())} files · {len(groups)} types"))
    return "\n".join(L)


def render_summary(app, st) -> str:
    """A one-screen overview of the whole vault: counts per type, the entities as
    a tree, graph size + key connectors, and a confirmation of what's on disk."""
    from pathlib import Path as _P
    a, dim = st.a, st.dim
    name = app.home.name or "vault"
    path = str(app.home).replace(str(_P.home()), "~")
    ents = app.list()
    by = _by_type(ents)
    exp = app.export()
    N, E = len(exp.get("nodes", [])), len(exp.get("edges", []))
    dens = (2 * E / (N * (N - 1))) if N > 1 else 0.0

    L = [a(f"  ▤ {name} — summary"), dim(f"  {path}"),
         dim(f"  {len(ents)} entities · {N} nodes · {E} edges · density {dens:.3f}"), ""]
    if not ents:
        L.append(dim('  empty — try  add topic "…"  ·  add <doi>  ·  extract'))
        return "\n".join(L)

    mx = max(by.values())
    for t in _ORDER + [x for x in by if x not in _ORDER]:
        if by.get(t):
            L.append(f"  {DOT.get(t, '·')} {_pad(t, 8)} {a(hbar(by[t], mx, 12))} {by[t]}")

    groups = {}
    for e in sorted(ents, key=lambda e: e.id):
        groups.setdefault(e.type or "note", []).append(e)
    L += ["", dim("  ── entities ──")]
    for t in [x for x in TYPES if x in groups] + [x for x in groups if x not in TYPES]:
        items = groups[t]
        L.append(f"  {DOT.get(t, '·')} {a(t)}/")
        for i, e in enumerate(items[:12]):
            branch = "└─" if i == min(len(items), 12) - 1 else "├─"
            L.append(f"     {dim(branch)} {e.title or e.id}")
        if len(items) > 12:
            L.append(dim(f"     +{len(items) - 12} more"))

    if E:
        bridges = app.bridges(limit=3)
        if bridges:
            L += ["", dim("  ── key connectors ──")]
            for r in bridges:
                L.append(f"  {DOT.get(r.get('type'), '·')} {a(r.get('title') or r['key'])}"
                         f"  {dim('betweenness ' + format(r.get('score', 0), '.2f'))}")
        clusters = app.clusters()
        if clusters:
            L.append(dim(f"  {len(clusters)} cluster(s): sizes " + ", ".join(str(c['size']) for c in clusters[:8])))

    L += ["", dim(f"  ✓ saved on disk — {len(ents)} Markdown files in  {path}/vault/")]
    return "\n".join(L)


# ---------- pure renderers ----------
def _render_list(app, st):
    ents = sorted(app.list(), key=lambda e: e.id)
    if not ents:
        return st.dim('nothing curated yet — try  new person "Ada Lovelace"  or  add <doi>')
    lines = [st.dim(f"{len(ents)} curated")]
    for e in ents:
        lines.append(f"  {DOT.get(e.type, '·')} {_pad(e.type, 7)} {st.a(_pad(e.id, 32))} {e.title or ''}")
    return "\n".join(lines)


def _render_entity(app, eid, st):
    if not eid:
        return st.dim("usage: open <id>")
    try:
        v = app.inspect(eid)
    except (FileNotFoundError, OSError, KeyError):
        return f"{eid} {st.dim('· not found — check the id with  ls / search')}"
    lines = [f"{st.bold(v.title or v.id)} {st.dim('· ' + v.type + ' · ' + v.status)}"]
    for k, val in v.attributes.items():                              # scalar attributes
        shown = ", ".join(str(x) for x in val) if isinstance(val, list) else str(val)
        lines.append(f"  {st.dim(_pad(k, 11))} {shown}")
    if v.relations:                                                 # relations, grouped by kind
        lines.append(st.dim(f"  connections ({v.degree})"))
        for rel, nodes in v.relations.items():
            names = " · ".join(_dotfor(n) + " " + st.a(n.get("title") or n["key"]) for n in nodes[:6])
            more = st.dim(f" +{len(nodes) - 6}") if len(nodes) > 6 else ""
            lines.append(f"  {st.dim(_pad(rel, 11))} {names}{more}")
    else:
        lines.append(st.dim("  connections (0) — none yet; link it to a topic"))
    lines.append(f"  {st.dim(_pad('notes', 11))} {v.notes or '—'}")
    warns = [i for i in v.issues if i.severity == "warn"]
    if warns:
        lines.append(st.dim("  ⚠ " + " · ".join(i.message for i in warns[:3])))
    lines.append(st.dim(f"  → around {v.id} · graph {v.id} · similar {v.id}"))
    return "\n".join(lines)


def _render_scored(header, rows, st, reason_key=None):
    if not rows:
        return st.dim(f"{header} · nothing found")
    mx = max((r.get("score") or 0) for r in rows) or 1
    lines = [st.dim(header)]
    for r in rows:
        label = st.a(_pad(r.get("title") or r["key"], 30))
        if reason_key:
            lines.append(f"  ▸ {label} {st.dim(_pad(r.get(reason_key) or '', 22))} {hbar(r.get('score') or 0, mx, 8)}")
        else:
            lines.append(f"  {label} {hbar(r.get('score') or 0, mx)}  {(r.get('score') or 0):.3f}")
    return "\n".join(lines)


def _render_clusters(app, st):
    cs = app.clusters()
    if not cs:
        return st.dim("no clusters yet — add more connected seeds")
    mx = max(c["size"] for c in cs) or 1
    lines = [st.dim(f"clusters · {len(cs)} communities")]
    for i, c in enumerate(cs, 1):
        names = " · ".join(st.a(m.get("title") or m["key"]) for m in c["members"][:10])
        lines.append(f"  ▚ {st.dim('cluster ' + str(i) + ' · ' + str(c['size']) + ' nodes')} {hbar(c['size'], mx, 10)}")
        lines.append(f"     {names}" + (st.dim(f"  +{c['size'] - 10} more") if c["size"] > 10 else ""))
    return "\n".join(lines)


def _render_path(app, a, b, st):
    if not a or not b:
        return st.dim("usage: path <a> <b>")
    chain = app.path(a, b)
    if not chain:
        return st.dim(f"no path found between {a} and {b}")
    lines = [st.dim(f"path · {len(chain)} hops")]
    for i, s in enumerate(chain):
        if i:
            lines.append(st.dim(f"     ↓ {chain[i - 1].get('rel_to_next') or ''}"))
        lines.append(f"  {st.a(s.get('title') or s['key'])} {st.dim('· ' + (s.get('type') or ''))}")
    return "\n".join(lines)


def _render_stats(app, st):
    d = app.export()
    nodes, edges = d.get("nodes", []), d.get("edges", [])
    if not nodes:
        return st.dim("empty graph — add or create something first")
    by = {}
    for n in nodes:
        t = n.get("type") or "·"
        by[t] = by.get(t, 0) + 1
    N, E = len(nodes), len(edges)
    dens = (2 * E / (N * (N - 1))) if N > 1 else 0.0
    mx = max(by.values()) or 1
    lines = [st.dim("manifexa · system status"),
             f"  nodes {N}     edges {E}     density {dens:.3f}", ""]
    for t, n in sorted(by.items(), key=lambda kv: -kv[1]):
        lines.append(f"  {DOT.get(t, '·')} {_pad(t, 7)} {st.a(hbar(n, mx, 18))} {n}")
    return "\n".join(lines)


def _boxlines(title, d, W):
    inner = f" {d} {title}"[: W - 2]
    inner += " " * (W - 2 - len(inner))
    return ["┌" + "─" * (W - 2) + "┐", "│" + inner + "│", "└" + "─" * (W - 2) + "┘"]


def _draw_edge(grid, x0, y0, x1, y1):
    """Plot a straight line between two cells with box-drawing chars (won't
    overwrite anything already drawn)."""
    dx, dy = x1 - x0, y1 - y0
    steps = max(abs(dx), abs(dy))
    if not steps:
        return
    ch = "─" if abs(dy) * 2 <= abs(dx) else "│" if abs(dx) * 2 <= abs(dy) else \
        ("╲" if (dx > 0) == (dy > 0) else "╱")
    for s in range(1, steps):
        x, y = int(round(x0 + dx * s / steps)), int(round(y0 + dy * s / steps))
        if 0 <= y < len(grid) and 0 <= x < len(grid[0]) and grid[y][x] == " ":
            grid[y][x] = ch


def _map_positions(nodes, edges) -> dict:
    """Force-directed layout of the whole graph, normalised to the unit square:
    ``{key: (x, y)}`` with x, y in [0, 1]. Deterministic (fixed seed)."""
    import networkx as nx

    g = nx.Graph()
    g.add_nodes_from(n["key"] for n in nodes)
    g.add_edges_from((e["src"], e["dst"]) for e in edges)
    try:
        pos = nx.spring_layout(g, seed=7, k=0.9)
    except Exception:
        pos = nx.circular_layout(g)
    xs = [p[0] for p in pos.values()] or [0.0]
    ys = [p[1] for p in pos.values()] or [0.0]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    return {k: ((p[0] - minx) / ((maxx - minx) or 1),
                (p[1] - miny) / ((maxy - miny) or 1)) for k, p in pos.items()}


def _map_name(n) -> str:
    name = (n.get("title") or n.get("key") or "").split("/")[-1]
    return name if len(name) <= 18 else name[:17] + "…"


def _map_draw(nodes, edges, npos, st, width, height) -> str:
    """Draw the graph from normalised positions ``npos`` onto a width×height
    canvas — edges as lines, each node labelled inline with its glyph + name
    (not a code). Shared by the ``map`` command and the sidebar."""
    a = st.a

    def cell(k):
        x01, y01 = npos.get(k, (0.5, 0.5))
        x = 2 + int(max(0.0, min(1.0, x01)) * (width - 6))
        y = 1 + int(max(0.0, min(1.0, y01)) * (height - 2))
        return max(0, min(width - 3, x)), max(0, min(height - 1, y))

    cells, taken = {}, set()
    for n in nodes:
        x, y = cell(n["key"])
        while (x, y) in taken and x < width - 5:          # nudge off exact collisions
            x += 1
        taken.add((x, y))
        cells[n["key"]] = (x, y)

    grid = [[" "] * width for _ in range(height)]
    for e in edges:
        if e["src"] in cells and e["dst"] in cells:
            (x0, y0), (x1, y1) = cells[e["src"]], cells[e["dst"]]
            _draw_edge(grid, x0, y0, x1, y1)
    for n in nodes:                                        # glyph + name, over the edges
        x, y = cells[n["key"]]
        icon, name = _dotfor(n), _map_name(n)
        if x > width * 0.55:                               # right half → grow the label leftward
            label = name + " " + icon
            start = max(0, x - len(label) + 1)
        else:                                              # left half → grow it rightward
            label, start = icon + " " + name, x
        for j, ch in enumerate(label):
            if 0 <= start + j < width and 0 <= y < height:
                grid[y][start + j] = ch
    return "\n".join(a("".join(r).rstrip()) for r in grid)


def _render_map(app, st, width=84, height=22):
    """The whole graph as one ASCII node-link map: every node placed by a
    force-directed layout, labelled with its name, edges between them."""
    d = app.export()
    nodes, edges = d.get("nodes", []), d.get("edges", [])
    if not nodes:
        return st.dim("empty graph — add or create something first")
    if len(nodes) > 60:
        return st.dim(f"{len(nodes)} nodes is too many to draw clearly — narrow it with  "
                      f"search <term>  or focus one with  graph <id>")
    body = _map_draw(nodes, edges, _map_positions(nodes, edges), st, width, height)
    return body + "\n" + st.dim(f"  {len(nodes)} nodes · {len(edges)} edges")


def _render_graph(app, eid, st):
    if not eid:
        return st.dim("usage: graph <id>")
    g = app.graph()
    if not g.has_node(eid):
        return st.dim(f"no such node: {eid}")
    focal = g.node(eid) or {}
    ftitle = focal.get("title") or eid
    all_neigh = list(g.neighbors(eid))
    neigh = all_neigh[:3]
    if not neigh:
        return "\n".join(_boxlines(ftitle, _dotfor(focal), 26)) + "\n" + \
            st.dim("(no connections yet — enrich with  add  or  extract)")
    NB, G, FB = 18, 3, 26
    n = len(neigh)
    rowW = n * NB + (n - 1) * G
    W = max(rowW, FB)
    grid = [[" "] * W for _ in range(9)]

    def stamp(r, c, s):
        for i, ch in enumerate(s):
            if 0 <= c + i < W:
                grid[r][c + i] = ch

    fLeft = max(0, round((rowW - FB) / 2))
    for i, l in enumerate(_boxlines(ftitle, _dotfor(focal), FB)):
        stamp(i, fLeft, l)
    fC = fLeft + FB // 2
    centers = []
    for i, k in enumerate(neigh):
        left = i * (NB + G)
        node = g.node(k) or {}
        for j, l in enumerate(_boxlines(node.get("title") or k, _dotfor(node), NB)):
            stamp(6 + j, left, l)
        centers.append(left + NB // 2)
    stamp(3, fC, "│")
    for x in range(min(centers), max(centers) + 1):
        grid[4][x] = "─"
    for i, c in enumerate(centers):
        grid[4][c] = "┌" if i == 0 else ("┐" if i == len(centers) - 1 else "┬")
    grid[4][fC] = "┼" if fC in centers else "┴"
    for c in centers:
        grid[5][c] = "│"
    body = "\n".join("".join(r).rstrip() for r in grid)
    more = len(all_neigh) - len(neigh)
    legend = st.dim("● curated  ○ candidate") + (st.dim(f"   +{more} more") if more > 0 else "")
    return body + "\n\n" + legend


def dispatch(app, line, st=None):
    """Run one command; return the text to print. No I/O, no colour by default."""
    st = st or Style(False)
    if line.startswith("/"):          # accept Claude-style /commands
        line = line[1:]
    parts = line.split()
    if not parts:
        return ""
    c, a = parts[0].lower(), parts[1:]

    if c in ("help", "?"):
        return HELP
    if c == "about":
        return st.a(BANNER) + "\n\n" + st.dim(TAGLINE) + "\n" + \
            st.dim(f"{len(app.list())} curated · your data is Markdown you own")
    if c in ("manual", "man", "guide"):
        return render_manual(st)
    if c in ("ls", "list"):
        return _render_list(app, st)
    if c in ("open", "cat", "inspect"):
        return _render_entity(app, a[0] if a else "", st)
    if c == "around":
        if not a:
            return st.dim("usage: around <id>")
        rs = app.around(a[0])
        return _render_scored(f"around {a[0]} · {len(rs)} found", rs, st, reason_key="reason")
    if c == "similar":
        if not a:
            return st.dim("usage: similar <id>")
        rs = app.similar(a[0])
        return _render_scored(f"similar · {len(rs)}", rs, st)
    if c == "bridges":
        rs = app.bridges()
        return _render_scored(f"bridges · top {len(rs)} by betweenness", rs, st)
    if c == "clusters":
        return _render_clusters(app, st)
    if c == "path":
        return _render_path(app, a[0] if a else "", a[1] if len(a) > 1 else "", st)
    if c == "stats":
        return _render_stats(app, st)
    if c in ("graph", "map", "network"):
        if a and a[0] not in ("all", "*"):
            return _render_graph(app, a[0], st)
        w = shutil.get_terminal_size((100, 30)).columns
        return _render_map(app, st, width=max(44, min(int(w * 0.58), 82)))
    if c == "search":
        term = " ".join(a).lower()
        ents = [e for e in app.list() if term in (e.title or "").lower() or term in e.id.lower()]
        if not ents:
            return st.dim(f'no matches for "{term}"')
        return "\n".join([st.dim(f"search · {len(ents)}")] +
                         [f"  {_pad(e.type, 7)} {st.a(_pad(e.id, 30))} {e.title or ''}" for e in ents])
    if c == "add":
        if not a:
            return st.dim("usage:  add <type> <title>  (create by hand)  ·  add <doi|openalex id>  (enrich from the web)")
        seed = " ".join(a)
        if a[0].lower() in TYPES and len(a) >= 2:                       # add <type> <rest>
            rest = " ".join(a[1:]).strip(chr(34) + chr(39))
            if _looks_like_seed(rest):                                 # add paper <doi> → fetch it, don't title with the doi
                seed = rest
            else:                                                      # add <type> <title> → create by hand
                return f"created → {st.a(app.create(a[0].lower(), rest))}"
        try:
            r = app.add(seed)
        except Exception:
            return st.dim("couldn't find \"" + seed + "\" online — for a paper use a DOI / OpenAlex id; "
                          "to create an entity by hand use  add <type> <title>  (e.g.  add topic \"Dirichlet process\")")
        return f"+ {st.a(r['entity'])} {st.dim('· ' + str(r.get('nodes', 0)) + ' nodes, ' + str(r.get('edges', 0)) + ' edges cached')}"
    if c == "new":
        if len(a) < 2:
            return st.dim('usage: new <type> <title>')
        try:
            return f"created → {st.a(app.create(a[0], ' '.join(a[1:]).strip(chr(34) + chr(39))))}"
        except Exception as e:
            return st.dim(f"can't create: {e}  (types: {', '.join(TYPES)})")
    if c in ("link", "connect"):
        if len(a) < 2:
            return st.dim('usage: link <from-id> <to-id> [relation]   e.g.  link paper/on-heat topic/thermodynamics about')
        src, dst, rel = a[0], a[1], " ".join(a[2:]) or "related"
        if not app.vault.exists(src):
            return st.dim(f"{src} isn't one of your entities — create it first  (new <type> \"…\")")
        if not app.graph().has_node(dst):
            return st.dim(f"{dst} doesn't exist yet — create it first, then link")
        try:
            app.link(src, dst, rel)
        except Exception as e:
            return st.dim(f"can't link: {e}")
        return f"linked  {st.a(src)}  {st.dim('—' + rel + '→')}  {st.a(dst)}"
    if c == "promote":
        return f"promoted → {st.a(app.promote(a[0]))}" if a else st.dim("usage: promote <id>")
    if c in ("remove", "rm", "delete", "del"):
        if not a:
            return st.dim("usage: remove <id>")
        app.remove(a[0])
        return st.dim(f"removed {a[0]}")
    if c == "embed":
        return st.dim(f"embedded {app.embed().get('embedded', 0)} papers — try  similar <id>")
    if c == "expand":
        if not a:
            return st.dim("usage: expand <id>")
        try:
            r = app.expand(a[0])
        except Exception as e:
            return st.dim(f"expand failed: {e}")
        return st.dim(f"expanded {a[0]} — {r['entities']} entities · {r['edges']} edges proposed (candidates; try  around {a[0]})")
    if c == "complete":
        if not a:
            return st.dim("usage: complete <id>")
        try:
            r = app.complete(a[0])
        except Exception as e:
            return st.dim(f"complete failed: {e}")
        return st.dim(f"inferred {r['edges']} likely links for {a[0]} (candidates)")
    if c in ("ask", "find"):
        q = " ".join(a)
        if not q:
            return st.dim("usage: ask <question>")
        try:
            keys = app.ask(q)
        except Exception as e:
            return st.dim(f"ask failed: {e}")
        if not keys:
            return st.dim(f'nothing matched "{q}"')
        g = app.graph()
        lines = [st.dim(f"ask · {len(keys)} matches")]
        for k in keys:
            n = g.node(k) or {}
            lines.append("  ▸ " + st.a(_pad(n.get("title") or k, 34)) + " " + st.dim(n.get("type") or ""))
        return "\n".join(lines)
    if c == "vault":
        if not a:
            return render_vault(app, st)
        target = a[1] if a[0] == "new" and len(a) > 1 else a[0]
        try:
            app.reopen(target)
        except Exception as e:
            return st.dim(f"vault switch failed: {e}")
        return render_vault(app, st)
    if c in ("tree", "files"):
        return render_tree(app, st)
    if c in ("summary", "overview"):
        return render_summary(app, st)
    if c == "export":
        import json
        from pathlib import Path
        d = app.snapshot()
        path = a[0] if a else "manifexa-export.json"
        Path(path).write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
        n = d["counts"]
        return st.dim(f"exported {n['entities']} entities · {n['cache_nodes']} candidates · {n['cache_edges']} edges → {path}")
    if c == "import":
        import json
        from pathlib import Path
        if not a:
            return st.dim("usage: import <path>")
        p = Path(a[0])
        if not p.exists():
            return st.dim(f"no such file: {a[0]}")
        try:
            s = app.restore(json.loads(p.read_text(encoding="utf-8")))
        except Exception as e:
            return st.dim(f"import failed: {e}")
        return st.dim(f"imported {s['entities']} entities · {s['cache_nodes']} candidates · {s['cache_edges']} edges")
    return st.dim(f"unknown command: {c} — type help")


# ---------- the interactive loop (thin glue over dispatch) ----------
def _supports_color() -> bool:
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None and os.environ.get("TERM") != "dumb"


def _read_block(prompt) -> str:
    print(prompt)
    lines = []
    while True:
        try:
            l = input()
        except EOFError:
            break
        if l.strip() == ".":
            break
        lines.append(l)
    return "\n".join(lines)


def repl(app) -> None:
    st = Style(_supports_color(), accent=THEMES.get(load_config(app.home).get("phosphor", ""), THEMES["teal"]))
    try:
        import readline  # noqa: F401 — gives line editing, history, arrow keys
    except Exception:
        pass
    home = str(app.home).replace(str(Path.home()), "~")
    engine = type(app.engine).__name__.replace("Engine", "").lower()
    _spin()                               # 3-D intro (skipped if not a real terminal)
    print(st.a(BANNER))
    print(st.dim(TAGLINE))
    print(st.dim("type ") + "help" + st.dim(" for commands · Ctrl-D to quit"))
    if not app.list():
        print(st.dim("empty graph — begin with  ") + 'new person "Ada Lovelace"' + st.dim("  or  ") + "add <doi>")
    while True:
        width = shutil.get_terminal_size((100, 24)).columns
        phosphor = {v: k for k, v in THEMES.items()}.get(st.accent, "teal")
        print()
        print(st.dim(_statusline(app, home, engine, phosphor, width)))
        try:
            line = input(st.a("›") + " ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line.startswith("/"):          # /commands work in the plain shell too
            line = line[1:].strip()
            if not line:
                continue
        c = line.split()[0].lower()
        rest = line[len(line.split()[0]):].strip()
        if c in ("quit", "exit", "q"):
            break
        if c == "clear":
            os.system("cls" if os.name == "nt" else "clear")
            continue
        if c == "spin":
            _spin(seconds=4.5)
            continue
        if c in ("phosphor", "color", "colour"):
            key = _ph_key(rest)
            st.accent = THEMES[key]
            save_config(app.home, phosphor=key)
            print(st.dim("phosphor → " + key + " (saved)"))
            continue
        if c == "note":
            if not rest:
                print(st.dim("usage: note <id>")); continue
            try:
                app.open(rest)
            except (FileNotFoundError, OSError):
                print(st.dim("no such entity: " + rest)); continue
            app.set_note(rest, _read_block(st.dim(f"note · {rest} — type notes, end with '.' on its own line:")))
            print(st.dim("notes saved → file"))
            continue
        if c == "extract":
            text = _read_block(st.dim("extract · paste text, end with '.' on its own line:"))
            if not text.strip():
                print(st.dim("nothing to extract")); continue
            print(st.dim("extracting with Claude…"))
            try:
                r = app.extract(text)
                print(st.dim(f"extracted {r.get('entities', 0)} entities · {r.get('edges', 0)} links"))
            except Exception as e:
                print(st.dim(f"extract failed: {e}"))
            continue
        try:
            print(dispatch(app, line, st))
        except Exception as e:
            print(st.dim(f"error: {e}"))
    print(st.dim("bye."))
